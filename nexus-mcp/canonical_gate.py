#!/usr/bin/env python3
"""Fail-closed compatibility gate between XLSX canonicalization and the frozen compiler.

This module does not alter the parser, Hermes/MCP surface, deterministic compiler,
QA, package generation, or CSV contract. It answers one question only: can this
canonical campaign safely enter the existing campaign-wide compiler semantics?
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

EXPECTED_SCHEMA = "nexus-canonical-campaign-v0"
REQUIRED_TOP_LEVEL = {
    "schema",
    "canonical_status",
    "source",
    "counts",
    "campaign",
    "audiences",
    "creatives",
    "activations",
    "source_rows",
    "relationships",
    "ambiguities",
    "validation_issues",
}


def _failure(code: str, field: str, detail: Any = None) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "field": field}
    if detail is not None:
        item["detail"] = detail
    return item


def assess_canonical_compatibility(canonical: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic READY_FOR_COMPILE or BLOCKED decision.

    The frozen compiler currently assumes one campaign-wide platform and one exact
    flight window. Any canonical input that cannot satisfy those semantics is
    blocked rather than flattened or guessed.
    """
    failures: list[dict[str, Any]] = []

    if not isinstance(canonical, dict):
        return {
            "status": "BLOCKED",
            "reason": "INVALID_CANONICAL",
            "compiler_allowed": False,
            "failures": [_failure("INVALID_TYPE", "canonical", type(canonical).__name__)],
            "unresolved": [],
            "validation_issues": [],
        }

    missing = sorted(REQUIRED_TOP_LEVEL.difference(canonical.keys()))
    if missing:
        failures.append(_failure("MISSING_TOP_LEVEL_FIELDS", "canonical", missing))

    schema = canonical.get("schema")
    if schema != EXPECTED_SCHEMA:
        failures.append(_failure("UNSUPPORTED_SCHEMA", "schema", schema))

    status = canonical.get("canonical_status")
    ambiguities = deepcopy(canonical.get("ambiguities") or [])
    validation_issues = deepcopy(canonical.get("validation_issues") or [])

    if status != "READY":
        failures.append(_failure("CANONICAL_NOT_READY", "canonical_status", status))
    if ambiguities:
        failures.append(_failure("UNRESOLVED_AMBIGUITIES", "ambiguities", ambiguities))
    if validation_issues:
        failures.append(_failure("VALIDATION_ISSUES", "validation_issues", validation_issues))

    campaign = canonical.get("campaign")
    activations = canonical.get("activations")
    if not isinstance(campaign, dict):
        failures.append(_failure("INVALID_CAMPAIGN", "campaign"))
        campaign = {}
    if not isinstance(activations, list) or not activations:
        failures.append(_failure("INVALID_ACTIVATIONS", "activations"))
        activations = []

    campaign_platform = campaign.get("platform")
    campaign_start = campaign.get("flight_start")
    campaign_end = campaign.get("flight_end")
    flight_scope = campaign.get("flight_scope")

    if not campaign_platform:
        failures.append(_failure("MISSING_CAMPAIGN_PLATFORM", "campaign.platform"))
    if not campaign_start or not campaign_end:
        failures.append(_failure("MISSING_CAMPAIGN_FLIGHT", "campaign.flight"))
    if flight_scope != "exact":
        failures.append(_failure("NON_EXACT_CAMPAIGN_FLIGHT", "campaign.flight_scope", flight_scope))

    for activation in activations:
        if not isinstance(activation, dict):
            failures.append(_failure("INVALID_ACTIVATION", "activations"))
            continue
        activation_id = activation.get("activation_id")
        if campaign_platform and activation.get("platform") != campaign_platform:
            failures.append(
                _failure(
                    "ACTIVATION_PLATFORM_MISMATCH",
                    "activation.platform",
                    {
                        "activation_id": activation_id,
                        "campaign": campaign_platform,
                        "activation": activation.get("platform"),
                    },
                )
            )
        if campaign_start and campaign_end and (
            activation.get("flight_start") != campaign_start
            or activation.get("flight_end") != campaign_end
        ):
            failures.append(
                _failure(
                    "ACTIVATION_FLIGHT_MISMATCH",
                    "activation.flight",
                    {
                        "activation_id": activation_id,
                        "campaign": {"flight_start": campaign_start, "flight_end": campaign_end},
                        "activation": {
                            "flight_start": activation.get("flight_start"),
                            "flight_end": activation.get("flight_end"),
                        },
                    },
                )
            )

    if failures:
        reason = status if status in {"NEEDS_CONFIRMATION", "BLOCKED"} else "INCOMPATIBLE_CANONICAL"
        return {
            "status": "BLOCKED",
            "reason": reason,
            "compiler_allowed": False,
            "failures": failures,
            "unresolved": ambiguities,
            "validation_issues": validation_issues,
        }

    return {
        "status": "READY_FOR_COMPILE",
        "reason": "COMPATIBLE",
        "compiler_allowed": True,
        "failures": [],
        "unresolved": [],
        "validation_issues": [],
    }


def execute_if_compatible(canonical: dict[str, Any], compiler_call: Callable[[], Any]) -> dict[str, Any]:
    """Invoke the unchanged compiler call only when the compatibility gate passes."""
    gate = assess_canonical_compatibility(canonical)
    if not gate["compiler_allowed"]:
        return {"gate": gate, "compiler_called": False, "compile_result": None}
    result = compiler_call()
    return {"gate": gate, "compiler_called": True, "compile_result": result}
