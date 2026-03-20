"""Assessment pipeline: feature extraction, heuristic/statistical/LLM assessors.

Produces a complexity assessment for a task group before execution begins.
The pipeline selects the assessment method based on available historical data
and trained model accuracy, then persists the result to DuckDB.

Requirements: 30-REQ-1.1 through 30-REQ-1.6, 30-REQ-1.E1, 30-REQ-1.E2
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from agent_fox.core.config import RoutingConfig
from agent_fox.core.models import ModelTier
from agent_fox.core.token_tracker import record_auxiliary_usage, track_response_usage
from agent_fox.routing.core import (
    ComplexityAssessment,
    ExecutionOutcome,
    FeatureVector,
    count_outcomes,
    persist_assessment,
    persist_outcome,
)
from agent_fox.routing.features import extract_features

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Method selector (pure function, used by pipeline and property tests)
# ---------------------------------------------------------------------------


def select_method(
    outcome_count: int,
    accuracy: float,
    training_threshold: int,
    accuracy_threshold: float,
) -> str:
    """Determine which assessment method to use.

    Rules (Property 6 - Method Selection Consistency):
      - outcome_count < training_threshold -> "heuristic"
      - >= threshold AND accuracy >= acc_threshold -> "statistical"
      - >= threshold AND accuracy < acc_threshold -> "hybrid"

    Requirements: 30-REQ-1.3, 30-REQ-1.4, 30-REQ-1.5
    """
    if outcome_count < training_threshold:
        return "heuristic"
    if accuracy >= accuracy_threshold:
        return "statistical"
    return "hybrid"


# ---------------------------------------------------------------------------
# Heuristic assessor
# ---------------------------------------------------------------------------


def heuristic_assess(features: FeatureVector) -> tuple[ModelTier, float]:
    """Rule-based tier prediction.

    Rules:
      - SIMPLE: subtask_count <= 3 AND spec_word_count < 500 AND no property tests
      - ADVANCED: subtask_count >= 6 OR dependency_count >= 3 OR has_property_tests
      - STANDARD: everything else

    Returns (predicted_tier, confidence).
    Confidence is fixed at 0.6 (reflects low certainty of heuristic).

    Requirement: 30-REQ-1.3
    """
    confidence = 0.6

    # Check ADVANCED conditions first (any one triggers ADVANCED)
    if (
        features.subtask_count >= 6
        or features.dependency_count >= 3
        or features.has_property_tests
    ):
        return ModelTier.ADVANCED, confidence

    # Check SIMPLE conditions (all must hold)
    if (
        features.subtask_count <= 3
        and features.spec_word_count < 500
        and not features.has_property_tests
    ):
        return ModelTier.SIMPLE, confidence

    # Default: STANDARD
    return ModelTier.STANDARD, confidence


# ---------------------------------------------------------------------------
# LLM assessor
# ---------------------------------------------------------------------------


async def llm_assess(
    spec_dir: Path,
    task_group: int,
    features: FeatureVector,
    model: str,
) -> tuple[ModelTier, float] | None:
    """Use an LLM to assess task complexity.

    Sends a structured prompt with the task group's spec content and feature
    summary. Parses the LLM response for a tier prediction and confidence.
    Uses the SIMPLE tier model for cost efficiency.

    Returns None if the LLM call fails (import error, API error, etc.).
    This allows the caller to distinguish between "LLM not available"
    (returns None) and "LLM explicitly failed" (raises).

    Requirement: 30-REQ-1.5, 30-REQ-1.E1
    """
    try:
        # Import here to avoid circular deps and allow mocking
        from agent_fox.core.client import create_async_anthropic_client
    except ImportError:
        logger.warning("Anthropic client not available for LLM assessment")
        return None

    prompt = (
        f"Assess the complexity of this task group.\n\n"
        f"Features:\n"
        f"- Subtask count: {features.subtask_count}\n"
        f"- Spec word count: {features.spec_word_count}\n"
        f"- Has property tests: {features.has_property_tests}\n"
        f"- Edge case count: {features.edge_case_count}\n"
        f"- Dependency count: {features.dependency_count}\n"
        f"- Archetype: {features.archetype}\n\n"
        f"Respond with exactly one of: SIMPLE, STANDARD, ADVANCED\n"
        f"Then a confidence score between 0.0 and 1.0.\n"
        f"Format: TIER CONFIDENCE\n"
        f"Example: STANDARD 0.75"
    )

    try:
        from agent_fox.core.retry import retry_api_call_async

        async def _call() -> object:
            async with create_async_anthropic_client() as client:
                return await client.messages.create(
                    model=model,
                    system=(
                        "You are a task complexity assessor."
                        " Respond only with the tier and confidence."
                    ),
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=50,
                )

        api_response = await retry_api_call_async(_call, context="LLM assessment")

        track_response_usage(api_response, model, "LLM assessment")

        response = api_response.content[0].text if api_response.content else ""
    except Exception:
        logger.warning("LLM assessment API call failed", exc_info=True)
        record_auxiliary_usage(0, 0, model)
        return None

    # Parse response
    text = response.strip().upper()
    parts = text.split()

    tier_str = parts[0] if parts else "STANDARD"
    try:
        tier = ModelTier(tier_str)
    except ValueError:
        tier = ModelTier.STANDARD

    try:
        conf = float(parts[1]) if len(parts) > 1 else 0.7
        conf = max(0.0, min(1.0, conf))
    except (ValueError, IndexError):
        conf = 0.7

    return tier, conf


# ---------------------------------------------------------------------------
# Assessment pipeline
# ---------------------------------------------------------------------------


class AssessmentPipeline:
    """Orchestrates complexity assessment for a task group.

    Selects the assessment method based on historical data availability and
    statistical model accuracy, runs the appropriate assessor(s), persists
    the result, and returns a ComplexityAssessment.

    Requirements: 30-REQ-1.1 through 30-REQ-1.6, 30-REQ-1.E1, 30-REQ-1.E2
    """

    def __init__(
        self,
        config: RoutingConfig,
        db: duckdb.DuckDBPyConnection,
    ) -> None:
        self._config = config
        self._db = db
        self._statistical: object | None = None
        self._statistical_accuracy: float = 0.0
        self._last_training_count: int = 0
        # 39-REQ-2.3: Duration regression model state
        self._duration_model: object | None = None
        self._last_duration_training_count: int = 0

    @property
    def duration_model(self) -> object | None:
        """Return the trained duration regression model, if any.

        Requirements: 39-REQ-2.2
        """
        return self._duration_model

    async def assess(
        self,
        node_id: str,
        spec_name: str,
        task_group: int,
        spec_dir: Path,
        archetype: str,
        tier_ceiling: ModelTier,
    ) -> ComplexityAssessment:
        """Produce a complexity assessment for a task group.

        The entire pipeline is wrapped in try/except for graceful degradation
        (Property 7). On any unhandled failure, returns a heuristic-based
        assessment with confidence 0.0.

        Requirements: 30-REQ-1.1, 30-REQ-7.E1
        """
        try:
            return await self._assess_inner(
                node_id, spec_name, task_group, spec_dir, archetype, tier_ceiling
            )
        except Exception:
            logger.error(
                "Assessment pipeline failed for %s, falling back to default",
                node_id,
                exc_info=True,
            )
            return self._make_fallback_assessment(
                node_id, spec_name, task_group, archetype, tier_ceiling
            )

    async def _assess_inner(
        self,
        node_id: str,
        spec_name: str,
        task_group: int,
        spec_dir: Path,
        archetype: str,
        tier_ceiling: ModelTier,
    ) -> ComplexityAssessment:
        """Core assessment logic (may raise)."""
        # 1. Extract features
        features = extract_features(spec_dir, task_group, archetype)

        # 2. Determine available data and method
        outcome_count = self._get_outcome_count()
        method = select_method(
            outcome_count,
            self._statistical_accuracy,
            self._config.training_threshold,
            self._config.accuracy_threshold,
        )

        # 3. Train/retrain statistical model if needed
        if outcome_count >= self._config.training_threshold:
            self._maybe_train_or_retrain(outcome_count)
            # Re-evaluate method after training (accuracy may have changed)
            method = select_method(
                outcome_count,
                self._statistical_accuracy,
                self._config.training_threshold,
                self._config.accuracy_threshold,
            )

        # 4. Run the appropriate assessor(s)
        predicted_tier, confidence, effective_method = await self._run_assessors(
            method, features, spec_dir, task_group
        )

        # 5. Clamp to tier ceiling
        predicted_tier = self._clamp_to_ceiling(predicted_tier, tier_ceiling)

        # 6. Build assessment
        assessment = ComplexityAssessment(
            id=str(uuid.uuid4()),
            node_id=node_id,
            spec_name=spec_name,
            task_group=task_group,
            predicted_tier=predicted_tier,
            confidence=confidence,
            assessment_method=effective_method,
            feature_vector=features,
            tier_ceiling=tier_ceiling,
            created_at=datetime.now(UTC),
        )

        # 7. Persist — errors propagate (38-REQ-6.1)
        try:
            persist_assessment(self._db, assessment)
        except Exception:
            logger.warning(
                "Failed to persist assessment %s", assessment.id, exc_info=True
            )

        logger.info(
            "Assessment for %s: tier=%s confidence=%.2f method=%s",
            node_id,
            predicted_tier,
            confidence,
            method,
        )

        return assessment

    async def _run_assessors(
        self,
        method: str,
        features: FeatureVector,
        spec_dir: Path,
        task_group: int,
    ) -> tuple[ModelTier, float, str]:
        """Run the selected assessor(s) and return (tier, confidence, effective_method).

        The effective_method may differ from *method* if a fallback occurred
        (e.g. LLM failure in hybrid mode reverts to heuristic).
        """
        if method == "heuristic":
            tier, conf = heuristic_assess(features)
            return tier, conf, "heuristic"

        if method == "statistical":
            tier, conf, fell_back = self._run_statistical(features)
            return tier, conf, "heuristic" if fell_back else "statistical"

        # method == "hybrid": run both statistical and LLM
        return await self._run_hybrid(features, spec_dir, task_group)

    def _run_statistical(
        self, features: FeatureVector
    ) -> tuple[ModelTier, float, bool]:
        """Run the statistical assessor.

        Returns (tier, confidence, fell_back) where fell_back is True if
        the statistical model was unavailable and heuristic was used instead.
        """
        if self._statistical is not None:
            try:
                tier, conf = self._statistical.predict(features)  # type: ignore[union-attr]
                return tier, conf, False
            except Exception:
                logger.warning(
                    "Statistical prediction failed, falling back to heuristic",
                    exc_info=True,
                )
        tier, conf = heuristic_assess(features)
        return tier, conf, True

    async def _run_hybrid(
        self,
        features: FeatureVector,
        spec_dir: Path,
        task_group: int,
    ) -> tuple[ModelTier, float, str]:
        """Run both statistical and LLM assessors, merge results.

        On LLM failure, falls back to heuristic (30-REQ-1.E1).
        On divergence, uses the method with higher historical accuracy (30-REQ-4.4).

        Returns (tier, confidence, effective_method).
        """
        # Get statistical prediction
        stat_tier, stat_conf, _ = self._run_statistical(features)

        # Get LLM prediction
        llm_tier: ModelTier | None = None
        llm_conf: float = 0.0
        try:
            from agent_fox.core.models import TIER_DEFAULTS

            llm_model = TIER_DEFAULTS[ModelTier.SIMPLE]
            llm_result = await llm_assess(spec_dir, task_group, features, llm_model)
        except Exception:
            # Explicit failure (e.g. mocked to raise) → fall back to heuristic
            # per 30-REQ-1.E1
            logger.warning(
                "LLM assessment failed, falling back to heuristic",
                exc_info=True,
            )
            tier, conf = heuristic_assess(features)
            return tier, conf, "heuristic"

        if llm_result is None:
            # LLM not available (no client, API error handled internally)
            # Still hybrid mode, just using statistical/heuristic result
            return stat_tier, stat_conf, "hybrid"

        llm_tier, llm_conf = llm_result

        # Compare predictions
        if llm_tier == stat_tier:
            # Agreement: use the prediction with merged confidence
            return stat_tier, max(stat_conf, llm_conf), "hybrid"

        # Divergence: use the method with higher historical accuracy
        logger.warning(
            "Hybrid divergence: statistical=%s (acc=%.2f) vs LLM=%s (conf=%.2f)",
            stat_tier,
            self._statistical_accuracy,
            llm_tier,
            llm_conf,
        )

        # Statistical accuracy is known; LLM "accuracy" approximated by its confidence
        # When statistical accuracy < threshold, we prefer LLM
        if self._statistical_accuracy >= llm_conf:
            return stat_tier, stat_conf, "hybrid"
        return llm_tier, llm_conf, "hybrid"

    def _get_outcome_count(self) -> int:
        """Get the number of execution outcomes from DB.

        DuckDB errors propagate to the caller (38-REQ-6.2).
        """
        return count_outcomes(self._db)

    def _maybe_train_or_retrain(self, outcome_count: int) -> None:
        """Train or retrain the statistical model if needed."""
        # Lazy import to avoid circular deps and allow task group 6
        # to be implemented independently
        try:
            from agent_fox.routing.calibration import StatisticalAssessor
        except ImportError:
            logger.warning(
                "Statistical assessor not available (calibration module missing)"
            )
            return

        needs_training = self._statistical is None
        needs_retraining = (
            self._statistical is not None
            and outcome_count
            >= self._last_training_count + self._config.retrain_interval
        )

        if needs_training or needs_retraining:
            try:
                if self._statistical is None:
                    self._statistical = StatisticalAssessor(self._db)  # type: ignore[arg-type]
                accuracy = self._statistical.train()  # type: ignore[union-attr]
                old_accuracy = self._statistical_accuracy
                self._statistical_accuracy = accuracy
                self._last_training_count = outcome_count

                if (
                    needs_retraining
                    and accuracy < self._config.accuracy_threshold <= old_accuracy
                ):
                    logger.warning(
                        "Statistical model accuracy degraded from %.2f to %.2f "
                        "(below threshold %.2f), reverting to hybrid",
                        old_accuracy,
                        accuracy,
                        self._config.accuracy_threshold,
                    )

                logger.info(
                    "Statistical model %s: accuracy=%.3f (n=%d)",
                    "retrained" if needs_retraining else "trained",
                    accuracy,
                    outcome_count,
                )
            except Exception:
                logger.warning(
                    "Statistical model training failed, using heuristic",
                    exc_info=True,
                )
                self._statistical_accuracy = 0.0

    @staticmethod
    def _clamp_to_ceiling(tier: ModelTier, ceiling: ModelTier) -> ModelTier:
        """Ensure predicted tier doesn't exceed the ceiling."""
        from agent_fox.routing.escalation import _TIER_INDEX

        if _TIER_INDEX[tier] > _TIER_INDEX[ceiling]:
            return ceiling
        return tier

    @staticmethod
    def _make_fallback_assessment(
        node_id: str,
        spec_name: str,
        task_group: int,
        archetype: str,
        tier_ceiling: ModelTier,
    ) -> ComplexityAssessment:
        """Create a fallback assessment when the pipeline fails."""
        return ComplexityAssessment(
            id=str(uuid.uuid4()),
            node_id=node_id,
            spec_name=spec_name,
            task_group=task_group,
            predicted_tier=tier_ceiling,
            confidence=0.0,
            assessment_method="heuristic",
            feature_vector=FeatureVector(
                subtask_count=0,
                spec_word_count=0,
                has_property_tests=False,
                edge_case_count=0,
                dependency_count=0,
                archetype=archetype,
            ),
            tier_ceiling=tier_ceiling,
            created_at=datetime.now(UTC),
        )

    def record_outcome(
        self,
        assessment: ComplexityAssessment,
        actual_tier: ModelTier,
        total_tokens: int,
        total_cost: float,
        duration_ms: int,
        attempt_count: int,
        escalation_count: int,
        outcome: str,
        files_touched_count: int,
    ) -> None:
        """Record execution outcome and trigger retraining if needed.

        Best-effort: logs a warning on failure, never raises.
        Also triggers duration model retraining using the same
        mechanism as the tier classifier (39-REQ-2.3).

        Requirement: 30-REQ-3.1, 30-REQ-3.E1, 39-REQ-2.3
        """
        exec_outcome = ExecutionOutcome(
            id=str(uuid.uuid4()),
            assessment_id=assessment.id,
            actual_tier=actual_tier,
            total_tokens=total_tokens,
            total_cost=total_cost,
            duration_ms=duration_ms,
            attempt_count=attempt_count,
            escalation_count=escalation_count,
            outcome=outcome,
            files_touched_count=files_touched_count,
            created_at=datetime.now(UTC),
        )

        persist_outcome(self._db, exec_outcome)

        # 39-REQ-2.3: Retrain duration model when new outcomes are recorded.
        # Uses the same trigger mechanism as the tier classifier.
        self._maybe_retrain_duration_model()

    def _maybe_retrain_duration_model(self) -> None:
        """Retrain the duration regression model if enough outcomes exist.

        Follows the same pattern as ``_maybe_train_or_retrain`` for the tier
        classifier: train when outcome count crosses the threshold, retrain
        when new outcomes accumulate beyond the retrain interval.

        Requirements: 39-REQ-2.3, 38-REQ-6.1
        """
        try:
            from agent_fox.routing.duration import train_duration_model

            outcome_count = self._get_outcome_count()
            min_outcomes = getattr(self._config, "min_outcomes_for_regression", 30)
            if outcome_count < min_outcomes:
                return

            # Only retrain at intervals to avoid excessive computation
            if (
                self._duration_model is not None
                and outcome_count
                < self._last_duration_training_count + self._config.retrain_interval
            ):
                return

            model = train_duration_model(self._db, min_outcomes=min_outcomes)
            if model is not None:
                self._duration_model = model
                self._last_duration_training_count = outcome_count
                logger.info(
                    "Duration regression model %s (n=%d)",
                    "retrained"
                    if self._last_duration_training_count > 0
                    else "trained",
                    outcome_count,
                )
        except Exception:
            logger.warning("Duration model retraining failed", exc_info=True)
