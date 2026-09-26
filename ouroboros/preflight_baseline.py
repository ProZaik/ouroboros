"""Known preflight baseline failures.

Discriminates historical baseline debt from new breakage (ibl-16223221bb32, ibl-e57bf49161c2).
When tests fail in preflight, the runner partitions failures into known baseline debt
and new failures. If only baseline debt failures are present, no new breakage has been introduced.
"""

from __future__ import annotations

import re
from typing import Sequence, Tuple


# Exact test IDs or base names of known external-landing baseline failures on this host/environment.
KNOWN_PREFLIGHT_FAILURES: frozenset[str] = frozenset({
    "tests/test_docs_sync.py::test_architecture_component_map_covers_every_live_runtime_module",
    "tests/test_docs_sync.py::test_architecture_settings_table_mirrors_config_defaults",
    "tests/test_domain_manifest.py::test_manifest_covers_the_tracked_population_exactly",
    "tests/test_domain_manifest.py::test_checker_cli_is_green_on_this_tree",
    "tests/test_generated_inventories.py::test_data_layout_inventory_is_byte_identical",
    "tests/test_generated_inventories.py::test_facade_inventory_is_byte_identical",
    "tests/test_presence_foundation.py::test_presence_state_filename_and_alias_are_owner_protected",
    "tests/test_large_task_artifacts.py::test_capture_does_not_reuse_mutable_external_file_alias",
    "tests/test_large_task_artifacts.py::test_capture_does_not_reuse_mutable_external_file_alias[hardlink]",
    "tests/test_tool_classification_differential.py::test_single_classifier_matches_the_retired_pair_except_approved_deltas",
    "tests/test_tool_classification_differential.py::test_native_golden_answers_have_identical_retired_text_inputs",
    "tests/test_tool_classification_differential.py::test_golden_covers_every_harvested_producer",
    "tests/test_plan_spec.py::test_resolve_evidence_and_constitutional_never_raise_on_hostile_locators",
})


def is_baseline_failure(test_id: str, baseline: frozenset[str] = KNOWN_PREFLIGHT_FAILURES) -> bool:
    """Check if a test ID matches the known baseline debt."""
    clean_id = test_id.strip()
    if clean_id in baseline:
        return True
    base_id = clean_id.split("[", 1)[0]
    if base_id in baseline:
        return True
    return False


def parse_failed_test_ids(output: str) -> list[str]:
    """Extract failed test IDs from pytest output.

    Matches lines from summary or short test summary info:
      FAILED tests/test_foo.py::test_bar - AssertionError: ...
      FAILED tests/test_foo.py::test_bar
      ERROR tests/test_foo.py::test_bar - Error: ...
    """
    failures: list[str] = []
    pattern = re.compile(r"^(?:FAILED|ERROR)\s+(\S+?)(?:\s+-\s+.*|\s*$)", re.MULTILINE)
    for match in pattern.finditer(output):
        test_id = match.group(1).strip()
        if test_id not in failures:
            failures.append(test_id)
    return failures


def discriminate_failures(
    failed_test_ids: Sequence[str],
    baseline: frozenset[str] = KNOWN_PREFLIGHT_FAILURES,
) -> Tuple[list[str], list[str]]:
    """Partition failed test IDs into (new_failures, baseline_debt)."""
    new_failures: list[str] = []
    baseline_debt: list[str] = []
    for test_id in failed_test_ids:
        if is_baseline_failure(test_id, baseline):
            baseline_debt.append(test_id)
        else:
            new_failures.append(test_id)
    return new_failures, baseline_debt
