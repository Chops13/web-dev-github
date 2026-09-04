#!/usr/bin/env python3
"""Explicit source-row QA decision for duplicate activation candidates.

Scope is intentionally narrow. This module resolves only a mapper-emitted
DUPLICATE_ACTIVATION_CANDIDATE issue after a human explicitly chooses which
source row to retain. Source rows and activation candidates are never deleted.
Mixed-platform ambiguity and every unrelated blocker remain untouched.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

CANDIDATE_SCHEMA = "nexus-structural-candidates-v0"
DECISION = "CONFIRM_DUPLICATE_KEEP_ONE"
ALLOWED_DECISION_FIELDS = {"decision", "source_refs", "keep_source_ref"}
SEMANTIC_FIELDS = (
    "platform",
    "audience_candidate_id",
    "creative_candidate_id",
    "placement_name",
    "campaign_period",
    "landing_page_url",
)


def _validated_decision(decision: dict[str, Any]) -> tuple[list[str], str]:
    if not isinstance(decision, dict):
        raise ValueError("decision must be an object")
    unknown = sorted(set(decision).difference(ALLOWED_DECISION_FIELDS))
    if unknown:
        raise ValueError(f"Unsupported duplicate QA decision fields: {unknown}")
    if decision.get("decision") != DECISION:
        raise ValueError(f"decision must equal {DECISION}")

    source_refs = decision.get("source_refs")
    if not isinstance(source_refs, list) or len(source_refs) < 2:
        raise ValueError("source_refs must contain at least two source-row references")
    if not all(isinstance(ref, str) and ref.strip() for ref in source_refs):
        raise ValueError("source_refs must contain non-empty strings")
    source_refs = [ref.strip() for ref in source_refs]
    if len(set(source_refs)) != len(source_refs):
        raise ValueError("source_refs must be unique")

    keep_source_ref = decision.get("keep_source_ref")
    if not isinstance(keep_source_ref, str) or keep_source_ref.strip() not in source_refs:
        raise ValueError("keep_source_ref must be one of source_refs")
    return source_refs, keep_source_ref.strip()


def apply_duplicate_activation_qa_decision(
    candidates: dict[str, Any], decision: dict[str, Any]
) -> dict[str, Any]:
    """Resolve exactly one duplicate-activation blocker without deleting evidence."""
    if not isinstance(candidates, dict) or candidates.get("schema") != CANDIDATE_SCHEMA:
        raise ValueError("Unsupported structural candidate payload")

    source_refs, keep_source_ref = _validated_decision(decision)
    requested_refs = set(source_refs)

    validation_issues = candidates.get("validation_issues")
    if not isinstance(validation_issues, list):
        raise ValueError("validation_issues must be a list")

    matches = [
        issue
        for issue in validation_issues
        if isinstance(issue, dict)
        and issue.get("type") == "DUPLICATE_ACTIVATION_CANDIDATE"
        and issue.get("blocking", True)
        and set(issue.get("source_refs") or []) == requested_refs
    ]
    if len(matches) != 1:
        raise ValueError("source_refs must match exactly one unresolved duplicate activation issue")

    source_rows = candidates.get("source_rows")
    activations = candidates.get("activations")
    if not isinstance(source_rows, list) or not isinstance(activations, list):
        raise ValueError("source_rows and activations must be lists")

    known_source_refs = {
        row.get("source_ref")
        for row in source_rows
        if isinstance(row, dict) and row.get("source_ref")
    }
    if not requested_refs.issubset(known_source_refs):
        raise ValueError("duplicate QA decision references unknown source rows")

    activation_by_ref: dict[str, dict[str, Any]] = {}
    for activation in activations:
        if not isinstance(activation, dict):
            continue
        ref = activation.get("source_ref")
        if ref in requested_refs:
            if ref in activation_by_ref:
                raise ValueError("expected one activation candidate per source row")
            activation_by_ref[ref] = activation
    if set(activation_by_ref) != requested_refs:
        raise ValueError("every duplicate source row must map to one activation candidate")

    semantic_values = {
        tuple(activation_by_ref[ref].get(field) for field in SEMANTIC_FIELDS)
        for ref in source_refs
    }
    if len(semantic_values) != 1:
        raise ValueError("source rows are not semantically identical activation candidates")

    result = deepcopy(candidates)
    exclude_refs = [ref for ref in source_refs if ref != keep_source_ref]

    resolved_issue = None
    for issue in result["validation_issues"]:
        if (
            isinstance(issue, dict)
            and issue.get("type") == "DUPLICATE_ACTIVATION_CANDIDATE"
            and issue.get("blocking", True)
            and set(issue.get("source_refs") or []) == requested_refs
        ):
            issue["blocking"] = False
            issue["resolution"] = {
                "decision": DECISION,
                "origin": "source_row_qa_decision",
                "keep_source_ref": keep_source_ref,
                "exclude_source_refs": exclude_refs,
            }
            resolved_issue = issue
            break
    if resolved_issue is None:  # defensive; pre-validation above guarantees a match
        raise ValueError("duplicate activation issue disappeared during resolution")

    for activation in result["activations"]:
        if not isinstance(activation, dict) or activation.get("source_ref") not in requested_refs:
            continue
        retained = activation["source_ref"] == keep_source_ref
        activation["source_row_qa"] = {
            "status": "RETAINED" if retained else "EXCLUDED_DUPLICATE",
            "origin": "source_row_qa_decision",
            "decision": DECISION,
        }
        activation["eligible_for_compile"] = retained

    result.setdefault("source_row_qa_decisions", []).append({
        "decision": DECISION,
        "origin": "source_row_qa_decision",
        "source_refs": source_refs,
        "keep_source_ref": keep_source_ref,
        "exclude_source_refs": exclude_refs,
    })

    blocking_issues = [
        issue
        for issue in result.get("validation_issues") or []
        if isinstance(issue, dict) and issue.get("blocking", True)
    ]
    blocked = bool((result.get("ambiguities") or []) or blocking_issues)
    result["mapper_status"] = "NEEDS_CONFIRMATION" if blocked else "READY_CANDIDATES"
    result["compiler_allowed"] = not blocked
    return result
