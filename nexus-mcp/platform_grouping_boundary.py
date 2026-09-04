#!/usr/bin/env python3
"""Deterministic structural boundary for mixed-platform historical campaign candidates.

This module does one thing: turn one source campaign that contains multiple execution
platforms into explicit platform-scoped structural groups. It does not flatten the
platforms into one campaign, does not call the frozen compiler, and does not modify
Hermes/MCP or source evidence.

Input is expected to have already passed the narrow human-confirmation overlay and any
source-row QA decisions. The only unresolved ambiguity permitted here is
campaign.platform. All unrelated blockers remain fail-closed.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

CANDIDATE_SCHEMA = "nexus-structural-candidates-v0"
BOUNDARY_SCHEMA = "nexus-platform-groups-v0"
PLATFORM_FIELD = "campaign.platform"
RESOLUTION = "DETERMINISTIC_PLATFORM_PARTITION"


def _stable_id(prefix: str, *parts: Any) -> str:
    normalized = "\x1f".join("" if part is None else str(part).strip().casefold() for part in parts)
    return f"{prefix}-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:12].upper()}"


def _blocked(reason: str, failures: list[dict[str, Any]], candidates: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": BOUNDARY_SCHEMA,
        "status": "BLOCKED",
        "reason": reason,
        "compiler_allowed": False,
        "platform_groups": [],
        "failures": failures,
        "source": deepcopy(candidates.get("source")),
        "source_rows": deepcopy(candidates.get("source_rows") or []),
    }


def group_by_platform_boundary(candidates: dict[str, Any]) -> dict[str, Any]:
    """Partition eligible activation candidates by exact source platform.

    The output is still pre-compiler structure. Each group receives one exact platform,
    while all source rows, including rows excluded by prior duplicate QA, remain visible
    as evidence. No group is submitted to the frozen compiler here.
    """
    if not isinstance(candidates, dict) or candidates.get("schema") != CANDIDATE_SCHEMA:
        raise ValueError("Unsupported structural candidate payload")

    campaigns = candidates.get("campaigns")
    activations = candidates.get("activations")
    source_rows = candidates.get("source_rows")
    ambiguities = candidates.get("ambiguities") or []
    validation_issues = candidates.get("validation_issues") or []

    if not isinstance(campaigns, list) or len(campaigns) != 1 or not isinstance(campaigns[0], dict):
        raise ValueError("Expected exactly one campaign candidate")
    if not isinstance(activations, list) or not isinstance(source_rows, list):
        raise ValueError("activations and source_rows must be lists")
    if not isinstance(ambiguities, list) or not isinstance(validation_issues, list):
        raise ValueError("ambiguities and validation_issues must be lists")

    campaign = campaigns[0]
    failures: list[dict[str, Any]] = []

    unrelated_ambiguities = [
        deepcopy(item)
        for item in ambiguities
        if not isinstance(item, dict) or item.get("field") != PLATFORM_FIELD
    ]
    if unrelated_ambiguities:
        failures.append({
            "code": "UNRELATED_AMBIGUITY_REMAINS",
            "detail": unrelated_ambiguities,
        })

    platform_ambiguities = [
        item for item in ambiguities
        if isinstance(item, dict) and item.get("field") == PLATFORM_FIELD
    ]
    if len(platform_ambiguities) != 1:
        failures.append({
            "code": "EXPECTED_ONE_MIXED_PLATFORM_AMBIGUITY",
            "found": len(platform_ambiguities),
        })

    blocking_issues = [
        deepcopy(issue)
        for issue in validation_issues
        if isinstance(issue, dict) and issue.get("blocking", True)
    ]
    if blocking_issues:
        failures.append({
            "code": "BLOCKING_VALIDATION_ISSUES_REMAIN",
            "detail": blocking_issues,
        })

    platform_candidates = sorted({
        str(value).strip()
        for value in (campaign.get("platform_candidates") or [])
        if str(value).strip()
    })
    if len(platform_candidates) < 2:
        failures.append({
            "code": "MIXED_PLATFORM_SET_REQUIRED",
            "candidates": platform_candidates,
        })

    if campaign.get("platform") not in (None, ""):
        failures.append({
            "code": "CAMPAIGN_PLATFORM_MUST_REMAIN_UNRESOLVED_BEFORE_PARTITION",
            "value": campaign.get("platform"),
        })

    eligible_activations: list[dict[str, Any]] = []
    excluded_activations: list[dict[str, Any]] = []
    for activation in activations:
        if not isinstance(activation, dict):
            failures.append({"code": "INVALID_ACTIVATION_CANDIDATE"})
            continue
        platform = activation.get("platform")
        if not isinstance(platform, str) or not platform.strip():
            failures.append({
                "code": "ACTIVATION_PLATFORM_MISSING",
                "activation_candidate_id": activation.get("activation_candidate_id"),
            })
            continue
        if platform.strip() not in platform_candidates:
            failures.append({
                "code": "ACTIVATION_PLATFORM_OUTSIDE_SOURCE_SET",
                "activation_candidate_id": activation.get("activation_candidate_id"),
                "platform": platform,
            })
            continue
        if activation.get("eligible_for_compile") is False:
            excluded_activations.append(activation)
        else:
            eligible_activations.append(activation)

    if failures:
        return _blocked("PRECONDITIONS_FAILED", failures, candidates)

    source_row_by_ref = {
        row.get("source_ref"): row
        for row in source_rows
        if isinstance(row, dict) and row.get("source_ref")
    }

    groups: list[dict[str, Any]] = []
    for platform in platform_candidates:
        eligible = [a for a in eligible_activations if a.get("platform") == platform]
        excluded = [a for a in excluded_activations if a.get("platform") == platform]
        if not eligible:
            return _blocked(
                "EMPTY_PLATFORM_GROUP",
                [{"code": "NO_ELIGIBLE_ACTIVATIONS", "platform": platform}],
                candidates,
            )

        group_refs = [a.get("source_ref") for a in eligible + excluded]
        if any(ref not in source_row_by_ref for ref in group_refs):
            return _blocked(
                "SOURCE_EVIDENCE_MISSING",
                [{"code": "UNKNOWN_SOURCE_REF", "platform": platform, "source_refs": group_refs}],
                candidates,
            )

        group_campaign = deepcopy(campaign)
        group_campaign["platform"] = platform
        group_campaign["platform_candidates"] = [platform]
        group_campaign["platform_origin"] = "source_activation_partition"

        groups.append({
            "platform_group_id": _stable_id("PLATGRP", campaign.get("campaign_candidate_id"), platform),
            "platform": platform,
            "status": "READY_FOR_CANONICAL_ADAPTER",
            "campaign": group_campaign,
            "eligible_activation_candidate_ids": [a.get("activation_candidate_id") for a in eligible],
            "excluded_activation_candidate_ids": [a.get("activation_candidate_id") for a in excluded],
            "activation_candidates": deepcopy(eligible),
            "source_evidence": group_refs,
            "source_rows": [deepcopy(source_row_by_ref[ref]) for ref in group_refs],
            "audience_candidate_ids": sorted({
                a.get("audience_candidate_id") for a in eligible if a.get("audience_candidate_id")
            }),
            "creative_candidate_ids": sorted({
                a.get("creative_candidate_id") for a in eligible if a.get("creative_candidate_id")
            }),
        })

    boundary_resolution = {
        "field": PLATFORM_FIELD,
        "resolution": RESOLUTION,
        "origin": "deterministic_rule",
        "source_candidates": platform_candidates,
        "platform_group_ids": [group["platform_group_id"] for group in groups],
    }

    return {
        "schema": BOUNDARY_SCHEMA,
        "status": "READY_PLATFORM_GROUPS",
        "reason": "MIXED_PLATFORM_BOUNDARY_RESOLVED",
        "compiler_allowed": False,
        "next_stage": "PLATFORM_GROUP_TO_CANONICAL_ADAPTER",
        "counts": {
            "source_rows": len(source_rows),
            "platform_groups": len(groups),
            "eligible_activations": len(eligible_activations),
            "excluded_activations": len(excluded_activations),
        },
        "source": deepcopy(candidates.get("source")),
        "source_rows": deepcopy(source_rows),
        "platform_groups": groups,
        "boundary_resolutions": [boundary_resolution],
        "unresolved_ambiguities": [],
        "blocking_validation_issues": [],
    }
