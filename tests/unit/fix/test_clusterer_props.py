"""Property tests for clusterer.

Test Spec: TS-08-P3 (cluster coverage)
Property: Property 3 from design.md
Requirements: 08-REQ-3.1, 08-REQ-3.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.fix.checks import CheckCategory, CheckDescriptor, FailureRecord
from agent_fox.fix.clusterer import _fallback_cluster

# Strategy: generate failure records with various check names
check_name_st = st.sampled_from(["pytest", "ruff", "mypy", "npm test", "cargo test"])
category_st = st.sampled_from(
    [CheckCategory.TEST, CheckCategory.LINT, CheckCategory.TYPE],
)
output_st = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(categories=("L", "N", "P")),
)


@st.composite
def failure_record_st(draw):
    """Generate a random FailureRecord."""
    name = draw(check_name_st)
    cat = draw(category_st)
    output = draw(output_st)
    check = CheckDescriptor(name=name, command=["mock", name], category=cat)
    return FailureRecord(check=check, output=output, exit_code=1)


class TestClusterCoverage:
    """TS-08-P3: Cluster coverage.

    Property 3: For any non-empty list of failure records,
    _fallback_cluster() returns clusters whose union equals the input list.
    No failure is lost or duplicated.
    """

    @given(
        failures=st.lists(failure_record_st(), min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_all_failures_preserved(
        self,
        failures: list[FailureRecord],
    ) -> None:
        """Every input failure appears exactly once across all clusters."""
        clusters = _fallback_cluster(failures)

        all_clustered: list[FailureRecord] = []
        for cluster in clusters:
            all_clustered.extend(cluster.failures)

        # Same count (no loss or duplication)
        assert len(all_clustered) == len(failures)

        # Same identity set (exact same objects)
        assert set(id(f) for f in all_clustered) == set(id(f) for f in failures)
