"""Classification and segregation of backlog items between target projects and Ouroboros core.

In symbiotic mode, Ouroboros acts as autonomous engineer on a target project
(e.g. stand-appsec-pipeline) while maintaining its own self-evolution loop on system_repo.
Defects and improvements discovered in the target project must remain in the project's
own backlog and never contaminate Ouroboros's global improvement backlog or self-evolution
campaign. Only genuine Ouroboros tool, runtime, or platform improvements may enter
Ouroboros's self-evolution channel.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

# Keywords and patterns that identify Ouroboros core system/tool improvements
_SYSTEM_PATTERNS = [
    # Ouroboros tool names
    r"\broute_to_project\b",
    r"\brun_command\b",
    r"\bedit_text\b",
    r"\bsearch_code\b",
    r"\bread_file\b",
    r"\bwrite_file\b",
    r"\bknowledge_read\b",
    r"\bknowledge_write\b",
    r"\bscratchpad_append\b",
    r"\bcommit_reviewed\b",
    r"\bplan_task\b",
    r"\bset_next_wakeup\b",
    r"\btoggle_evolution\b",
    r"\btoggle_consciousness\b",
    r"\brequest_restart\b",
    # Ouroboros core modules & directories
    r"\bouroboros\b",
    r"\bsupervisor\b",
    r"\bplatform_layer\b",
    r"\bagent_task_pipeline\b",
    r"\bpost_task_evolution\b",
    r"\bsettings\.json\b",
    r"\bevolution_campaign\b",
    r"\bserver\.py\b",
    r"\blauncher\.py\b",
    # Ouroboros error / protocol tokens
    r"\bTOOL_ARG_ERROR\b",
    r"\bTOOL_REPORTED_FAILURE\b",
    r"\bAUTHORITY_SOURCE_UNAVAILABLE\b",
    r"\bLIGHT_MODE_BLOCKED\b",
    r"\bPREDECESSOR_REQUIRED\b",
    r"\bpredecessor_task_id\b",
    r"\bANCHOR_NOT_FOUND\b",
    r"\btriad_review\b",
    r"\bpre_commit_review\b",
    r"\bcontext_window_exceeded\b",
    r"\btoken_budget\b",
    r"\bprompt_bloat\b",
    r"\bprogressive_compaction\b",
    r"\btool friction\b",
    r"\btooling\b",
]

_SYSTEM_REGEX = re.compile("|".join(_SYSTEM_PATTERNS), re.IGNORECASE)

_SYSTEM_CATEGORIES = frozenset({
    "tool_ergonomics",
    "tool_failure",
    "tooling",
    "tools",
    "tool",
    "process",
    "agent_loop",
    "harness",
    "system",
    "platform",
    "ouroboros",
    "ouroboros_tool",
    "core",
    "prompt_discipline",
    "reflection",
    "context_fit",
})

# Patterns that identify target project (e.g. stand-appsec-pipeline) artifacts and domain logic
_PROJECT_PATTERNS = [
    r"\bstand-appsec-pipeline\b",
    r"\bstand48\b",
    r"\brunner\.py\b",
    r"\bdynamic_coordinator\b",
    r"\bapkid\b",
    r"\bfrida\b",
    r"\bjadx\b",
    r"\bdecompil\b",
    r"\bunpacker\b",
    r"\bapk\b",
    r"\bsast\b",
    r"\bsarif\b",
    r"\bboringssl\b",
    r"\bsqlcipher\b",
    r"\bkeystore\b",
    r"\bepic[1-5]\b",
    r"\btests/test_\b",
    r"\bsrc/\b",
    r"\brules/\b",
    r"\btest_stand_runner\b",
]
_PROJECT_REGEX = re.compile("|".join(_PROJECT_PATTERNS), re.IGNORECASE)


def is_system_improvement_candidate(
    candidate: Dict[str, Any],
    task: Optional[Dict[str, Any]] = None,
) -> bool:
    """Classify whether a backlog candidate is an Ouroboros system improvement.
    
    Returns True if the item belongs to Ouroboros core / self-evolution,
    False if it belongs to a project workspace (e.g. stand-appsec-pipeline).
    """
    if not isinstance(candidate, dict):
        return False

    explicit_scope = str(candidate.get("scope") or "").strip().lower()
    if explicit_scope == "project":
        return False
    if explicit_scope == "system":
        return True

    task = task or {}
    project_id = str(task.get("project_id") or "").strip()
    workspace_root = str(task.get("workspace_root") or "").strip()

    # Combine candidate textual content
    text_fields = [
        str(candidate.get("summary") or ""),
        str(candidate.get("evidence") or ""),
        str(candidate.get("source") or ""),
        str(candidate.get("context") or ""),
        str(candidate.get("proposed_next_step") or ""),
    ]
    blob = " ".join(text_fields)
    cat = str(candidate.get("category") or "").strip().lower()

    # If the candidate clearly mentions target project paths or components:
    if _PROJECT_REGEX.search(blob):
        return False

    # If category or content matches Ouroboros system patterns:
    if cat in _SYSTEM_CATEGORIES or _SYSTEM_REGEX.search(blob):
        return True

    # If task is NOT project-scoped, default to system
    if not project_id and not workspace_root:
        return True

    # If task is project-scoped and no strong system signal: default to project
    return False
