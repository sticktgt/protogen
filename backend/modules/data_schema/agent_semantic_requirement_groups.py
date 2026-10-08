from __future__ import annotations

from typing import Any

from backend.modules.data_schema.agent_requirement_context import compact_requirements

_CURRENT_RESULT_ORDER = (
    "no_data",
    "cross_cutting_data",
    "unclear",
    "direct",
)
_EXCLUSIVE_RESULT_GROUPS = _CURRENT_RESULT_ORDER[:-1]


def group_requirements_by_current_result(
    document: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """Arrange every compact requirement once by the agent's current result.

    This is a presentation-only transformation for the coverage reviewer. It does
    not infer requirement meaning: exclusive groups come directly from the stored
    agent report and every remaining requirement is placed in the current direct
    group after technical completeness validation has already succeeded.
    """
    compact = compact_requirements(document)
    grouped_ids = {
        group: _assessment_ids(report.get(group))
        for group in _EXCLUSIVE_RESULT_GROUPS
    }
    grouped: dict[str, list[dict[str, Any]]] = {
        group: [] for group in _CURRENT_RESULT_ORDER
    }

    for requirement in compact.get("requirements", []):
        if not isinstance(requirement, dict):
            continue
        requirement_id = str(
            requirement.get("id") or requirement.get("code") or ""
        ).strip()
        destination = next(
            (
                group
                for group in _EXCLUSIVE_RESULT_GROUPS
                if requirement_id in grouped_ids[group]
            ),
            "direct",
        )
        grouped[destination].append(requirement)

    return {
        "projects": compact.get("projects", []),
        "groups": compact.get("groups", []),
        "clusters": compact.get("clusters", []),
        "current_result_review_order": list(_CURRENT_RESULT_ORDER),
        "current_result_counts": {
            group: len(grouped[group]) for group in _CURRENT_RESULT_ORDER
        },
        "by_current_result": grouped,
    }


def _assessment_ids(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {
        str(item.get("requirement_id") or "").strip()
        for item in value
        if isinstance(item, dict) and str(item.get("requirement_id") or "").strip()
    }
