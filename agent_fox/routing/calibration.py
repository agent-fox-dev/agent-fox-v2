"""Statistical model training, cross-validation, and accuracy tracking.

Trains a logistic regression classifier on historical feature vectors and
execution outcomes to predict complexity tiers. Provides cross-validated
accuracy scores for method selection decisions.

Requirements: 30-REQ-4.1, 30-REQ-4.2, 30-REQ-4.3, 30-REQ-4.E1
"""

from __future__ import annotations

import json
import logging
import warnings

import duckdb
import numpy as np
from sklearn.exceptions import FitFailedWarning
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder

from agent_fox.core.models import ModelTier
from agent_fox.routing.storage import count_outcomes, query_outcomes
from agent_fox.routing.types import FeatureVector

logger = logging.getLogger(__name__)


def _feature_vector_to_array(fv_json: str) -> list[float]:
    """Convert a JSON feature vector to a numeric array for sklearn."""
    fv = json.loads(fv_json) if isinstance(fv_json, str) else fv_json
    return [
        float(fv.get("subtask_count", 0)),
        float(fv.get("spec_word_count", 0)),
        float(fv.get("has_property_tests", False)),
        float(fv.get("edge_case_count", 0)),
        float(fv.get("dependency_count", 0)),
    ]


def _dataclass_to_array(fv: FeatureVector) -> list[float]:
    """Convert a FeatureVector dataclass to a numeric array."""
    return [
        float(fv.subtask_count),
        float(fv.spec_word_count),
        float(fv.has_property_tests),
        float(fv.edge_case_count),
        float(fv.dependency_count),
    ]


class StatisticalAssessor:
    """Logistic regression classifier for complexity tier prediction.

    Requirements: 30-REQ-4.1, 30-REQ-4.2, 30-REQ-4.3, 30-REQ-4.E1
    """

    def __init__(self, db: duckdb.DuckDBPyConnection) -> None:
        self._db = db
        self._model: LogisticRegression | None = None
        self._label_encoder: LabelEncoder | None = None
        self._accuracy: float = 0.0
        self._last_training_count: int = 0

    @property
    def last_training_count(self) -> int:
        """Number of outcomes at last training."""
        return self._last_training_count

    def is_ready(self, training_threshold: int) -> bool:
        """True if enough data points exist for training."""
        return count_outcomes(self._db) >= training_threshold

    def train(self) -> float:
        """Train logistic regression on historical data. Returns accuracy.

        Uses cross-validation to compute accuracy. On failure (e.g. zero
        variance, insufficient classes), returns 0.0 and logs a warning.

        Requirements: 30-REQ-4.1, 30-REQ-4.2, 30-REQ-4.E1
        """
        try:
            rows = query_outcomes(self._db)
            if not rows:
                logger.warning("No training data available")
                return 0.0

            X = np.array([_feature_vector_to_array(r[0]) for r in rows])
            y_raw = [str(r[1]) for r in rows]

            # Encode tier labels
            self._label_encoder = LabelEncoder()
            y = self._label_encoder.fit_transform(y_raw)

            # Check we have at least 2 classes
            n_classes = len(set(y))
            if n_classes < 2:
                logger.warning(
                    "Only %d class(es) in training data, cannot train classifier",
                    n_classes,
                )
                # Train anyway for prediction but accuracy is limited
                self._model = LogisticRegression(max_iter=1000)
                self._model.fit(X, y)
                self._accuracy = 1.0  # trivially correct with one class
                self._last_training_count = count_outcomes(self._db)
                return self._accuracy

            # Train with cross-validation
            self._model = LogisticRegression(max_iter=1000)

            # Use min(5, n_samples_per_class) for CV folds
            min_class_count = min(np.bincount(y))
            cv_folds = min(5, min_class_count, len(y))
            if cv_folds < 2:
                cv_folds = 2

            # Suppress expected sklearn warnings when folds have sparse
            # class distribution (e.g. 3 STANDARD + 1 ADVANCED).
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore", category=UserWarning, module="sklearn"
                )
                warnings.filterwarnings("ignore", category=FitFailedWarning)
                scores = cross_val_score(
                    self._model, X, y, cv=cv_folds, error_score=0.0
                )
            valid_scores = scores[~np.isnan(scores)]
            if len(valid_scores) == 0:
                logger.warning(
                    "All CV folds failed (n=%d, classes=%d), treating accuracy as 0.0",
                    len(y),
                    n_classes,
                )
                self._accuracy = 0.0
            else:
                self._accuracy = float(np.mean(valid_scores))

            # Fit final model on all data
            self._model.fit(X, y)
            self._last_training_count = count_outcomes(self._db)

            logger.info(
                "Statistical model trained: accuracy=%.3f (cv=%d, n=%d)",
                self._accuracy,
                cv_folds,
                len(y),
            )
            return self._accuracy

        except Exception:
            logger.warning("Statistical model training failed", exc_info=True)
            self._accuracy = 0.0
            return 0.0

    def predict(self, features: FeatureVector) -> tuple[ModelTier, float]:
        """Predict tier with confidence from trained model.

        Raises RuntimeError if the model has not been trained.
        """
        if self._model is None or self._label_encoder is None:
            raise RuntimeError("Statistical model not trained")

        X = np.array([_dataclass_to_array(features)])
        pred_idx = self._model.predict(X)[0]
        tier_str = self._label_encoder.inverse_transform([pred_idx])[0]

        # Get prediction probability as confidence
        proba = self._model.predict_proba(X)[0]
        confidence = float(np.max(proba))

        return ModelTier(tier_str), confidence
