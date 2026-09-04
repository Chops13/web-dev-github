#!/usr/bin/env python3
"""Narrow human-confirmation overlay for historical campaign candidates.

Only campaign.client, campaign.currency, campaign.flight_start,
campaign.flight_end, and campaign.campaign_name may be human-confirmed here.
Platform is deliberately excluded so mixed-platform source semantics remain blocked.
The source candidate object is never mutated.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

CANDIDATE_SCHEMA = "nexus-structural-candidates-v0"
ALLOWED_CONFIRMATIONS = {
    "campaign.client",
    "campaign.currency",
    "campaign.flight_start",
    "campaign.flight_end",
    "campaign.campaign_name",
}


def _required_text(value: Any, field: str) -> str:
    if value is None:
        raise ValueError(f"{field} confirmation is required")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} confirmation is required")
    return text


def _iso_date(value: Any, field: str) -> str:
    text = _required_text(value, field)
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def apply_human_confirmations(candidates: dict[str, Any], confirmations: dict[str, Any]) -> dict[str, Any]:
    """Apply only the five permitted human confirmations and re-evaluate blockers."""
    if not isinstance(candidates, dict) or candidates.get("schema") != CANDIDATE_SCHEMA:
        raise ValueError("Unsupported structural candidate payload")
    if not isinstance(confirmations, dict):
        raise ValueError("confirmations must be an object")

    unknown = sorted(set(confirmations).difference(ALLOWED_CONFIRMATIONS))
    if unknown:
        raise ValueError(f"Unsupported human confirmation fields: {unknown}")

    result = deepcopy(candidates)
    campaigns = result.get("campaigns")
    if not isinstance(campaigns, list) or len(campaigns) != 1 or not isinstance(campaigns[0], dict):
        raise ValueError("Expected exactly one campaign candidate")
    campaign = campaigns[0]

    applied: list[dict[str, Any]] = []
    for field, raw_value in confirmations.items():
        if field == "campaign.client":
            value = _required_text(raw_value, field)
            campaign["client"] = value
        elif field == "campaign.currency":
            value = _required_text(raw_value, field).upper()
            if len(value) != 3 or not value.isalpha():
                raise ValueError("campaign.currency must be a three-letter currency code")
            campaign["currency"] = value
        elif field == "campaign.flight_start":
            value = _iso_date(raw_value, field)
            campaign["flight_start"] = value
        elif field == "campaign.flight_end":
            value = _iso_date(raw_value, field)
            campaign["flight_end"] = value
        elif field == "campaign.campaign_name":
            value = _required_text(raw_value, field)
            choices = campaign.get("campaign_name_candidates") or []
            if value not in choices:
                raise ValueError("campaign.campaign_name must be one of the source-derived candidates")
            campaign["campaign_name"] = value
        else:  # defensive; unknowns are rejected above
            raise ValueError(f"Unsupported human confirmation field: {field}")
        applied.append({"field": field, "value": value, "origin": "human_confirmation"})

    start = campaign.get("flight_start")
    end = campaign.get("flight_end")
    if start and end and date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("campaign.flight_start must be on or before campaign.flight_end")

    resolved_fields = set(confirmations)
    result["ambiguities"] = [
        item for item in (result.get("ambiguities") or [])
        if item.get("field") not in resolved_fields
    ]

    # Deliberately never resolve/flatten mixed platform semantics in this overlay.
    if len(campaign.get("platform_candidates") or []) > 1:
        has_platform_blocker = any(
            item.get("field") == "campaign.platform"
            for item in result["ambiguities"]
        )
        if not has_platform_blocker:
            result["ambiguities"].append({
                "field": "campaign.platform",
                "reason": "MULTIPLE_SOURCE_VALUES",
                "candidates": sorted(campaign.get("platform_candidates") or []),
                "resolution_required": True,
            })
        campaign["platform"] = None

    existing = result.get("human_confirmations") or []
    result["human_confirmations"] = deepcopy(existing) + applied

    blocking_issues = [
        issue for issue in (result.get("validation_issues") or [])
        if issue.get("blocking", True)
    ]
    blocked = bool(result["ambiguities"] or blocking_issues)
    result["mapper_status"] = "NEEDS_CONFIRMATION" if blocked else "READY_CANDIDATES"
    result["compiler_allowed"] = not blocked
    return result
