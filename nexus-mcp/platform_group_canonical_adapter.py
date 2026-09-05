#!/usr/bin/env python3
"""Adapt one deterministic platform group into the existing Nexus canonical contract.

Scope is intentionally narrow. This module accepts a READY_PLATFORM_GROUPS boundary,
selects exactly one READY_FOR_CANONICAL_ADAPTER platform group, and emits one
nexus-canonical-campaign-v0 payload. It does not call Hermes, MCP, the compiler, QA,
or package generation. Source-row evidence is preserved, including rows previously
excluded by explicit duplicate QA decisions.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

BOUNDARY_SCHEMA = "nexus-platform-groups-v0"
CANONICAL_SCHEMA = "nexus-canonical-campaign-v0"
EXPECTED_BOUNDARY_STATUS = "READY_PLATFORM_GROUPS"
EXPECTED_GROUP_STATUS = "READY_FOR_CANONICAL_ADAPTER"


def _stable_id(prefix: str, *parts: Any, length: int = 12) -> str:
    normalized = "\x1f".join("" if part is None else str(part).strip().casefold() for part in parts)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:length].upper()
    return f"{prefix}-{digest}"


def _required_text(value: Any, field: str) -> str:
    if value is None:
        raise ValueError(f"{field} is required")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _source_maps(group: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    rows = group.get("source_rows")
    activations = group.get("activation_candidates")
    if not isinstance(rows, list) or not isinstance(activations, list) or not activations:
        raise ValueError("platform group requires source_rows and at least one activation candidate")

    row_by_ref: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("source_rows must contain objects")
        ref = _required_text(row.get("source_ref"), "source_row.source_ref")
        if ref in row_by_ref:
            raise ValueError(f"duplicate source_ref in platform group: {ref}")
        row_by_ref[ref] = row

    eligible_refs: set[str] = set()
    for activation in activations:
        if not isinstance(activation, dict):
            raise ValueError("activation_candidates must contain objects")
        ref = _required_text(activation.get("source_ref"), "activation.source_ref")
        if ref not in row_by_ref:
            raise ValueError(f"activation source_ref missing from source_rows: {ref}")
        eligible_refs.add(ref)
    return row_by_ref, eligible_refs


def adapt_platform_group(boundary: dict[str, Any], platform_group_id: str) -> dict[str, Any]:
    """Return one source-backed Nexus canonical campaign for one exact platform group."""
    if not isinstance(boundary, dict) or boundary.get("schema") != BOUNDARY_SCHEMA:
        raise ValueError("Unsupported platform boundary payload")
    if boundary.get("status") != EXPECTED_BOUNDARY_STATUS:
        raise ValueError("Platform boundary is not ready for canonical adaptation")
    if boundary.get("unresolved_ambiguities"):
        raise ValueError("Platform boundary still contains unresolved ambiguities")
    if boundary.get("blocking_validation_issues"):
        raise ValueError("Platform boundary still contains blocking validation issues")

    groups = boundary.get("platform_groups")
    if not isinstance(groups, list):
        raise ValueError("platform_groups must be a list")
    matches = [group for group in groups if isinstance(group, dict) and group.get("platform_group_id") == platform_group_id]
    if len(matches) != 1:
        raise ValueError("platform_group_id must match exactly one platform group")
    group = matches[0]
    if group.get("status") != EXPECTED_GROUP_STATUS:
        raise ValueError("Platform group is not ready for canonical adaptation")

    campaign_source = group.get("campaign")
    if not isinstance(campaign_source, dict):
        raise ValueError("platform group campaign must be an object")

    client = _required_text(campaign_source.get("client"), "campaign.client")
    campaign_name = _required_text(campaign_source.get("campaign_name"), "campaign.campaign_name")
    objective = _required_text(campaign_source.get("objective"), "campaign.objective")
    market = _required_text(campaign_source.get("market"), "campaign.market")
    currency = _required_text(campaign_source.get("currency"), "campaign.currency").upper()
    platform = _required_text(campaign_source.get("platform"), "campaign.platform")
    flight_start = _required_text(campaign_source.get("flight_start"), "campaign.flight_start")
    flight_end = _required_text(campaign_source.get("flight_end"), "campaign.flight_end")

    if group.get("platform") != platform:
        raise ValueError("platform group and campaign platform disagree")
    if campaign_source.get("platform_candidates") != [platform]:
        raise ValueError("platform group campaign must contain exactly one platform candidate")

    campaign_key = _stable_id("CMP", client, campaign_name, objective, market, currency)
    row_by_ref, eligible_refs = _source_maps(group)

    audiences_by_candidate: dict[str, dict[str, Any]] = {}
    creatives_by_candidate: dict[str, dict[str, Any]] = {}
    activations: list[dict[str, Any]] = []
    plan_row_counts: dict[str, int] = {}

    for activation in group["activation_candidates"]:
        ref = _required_text(activation.get("source_ref"), "activation.source_ref")
        row = row_by_ref[ref]
        inputs = row.get("input_values")
        derived = row.get("derived_values")
        if not isinstance(inputs, dict) or not isinstance(derived, dict):
            raise ValueError(f"source row {ref} lacks input_values/derived_values evidence")

        activation_platform = _required_text(activation.get("platform"), "activation.platform")
        if activation_platform != platform:
            raise ValueError(f"activation {ref} crosses platform group boundary")

        audience_candidate_id = _required_text(activation.get("audience_candidate_id"), "activation.audience_candidate_id")
        audience_name = _required_text(derived.get("targeting"), f"{ref}.targeting")
        audience_row_id = _stable_id("AUD", campaign_key, audience_name)
        existing_audience = audiences_by_candidate.get(audience_candidate_id)
        if existing_audience and existing_audience["audience_name"] != audience_name:
            raise ValueError(f"audience candidate {audience_candidate_id} maps to conflicting source names")
        audiences_by_candidate.setdefault(audience_candidate_id, {
            "audience_row_id": audience_row_id,
            "audience_name": audience_name,
            "source_evidence": [],
            "source_candidate_id": audience_candidate_id,
        })["source_evidence"].append(ref)

        creative_candidate_id = _required_text(activation.get("creative_candidate_id"), "activation.creative_candidate_id")
        creative_id = _required_text(inputs.get("Ad Name"), f"{ref}.Ad Name")
        ad_format = _required_text(inputs.get("Format Type"), f"{ref}.Format Type")
        width = inputs.get("ad width")
        height = inputs.get("ad height")
        if width in (None, "") or height in (None, ""):
            raise ValueError(f"{ref} requires ad width and ad height")
        size = f"{width}x{height}"
        destination_url = _required_text(inputs.get("target URL"), f"{ref}.target URL")
        creative_row_id = _stable_id("CRE", campaign_key, creative_id)
        creative_shape = (creative_id, ad_format, size, destination_url)
        existing_creative = creatives_by_candidate.get(creative_candidate_id)
        if existing_creative:
            existing_shape = (
                existing_creative["creative_id"], existing_creative["ad_format"],
                existing_creative["size"], existing_creative["destination_url"],
            )
            if existing_shape != creative_shape:
                raise ValueError(f"creative candidate {creative_candidate_id} maps to conflicting source evidence")
        creatives_by_candidate.setdefault(creative_candidate_id, {
            "creative_row_id": creative_row_id,
            "creative_id": creative_id,
            "ad_format": ad_format,
            "size": size,
            "ratio": None,
            "asset_name": creative_id,
            "file_type": None,
            "destination_url": destination_url,
            "version": None,
            "status": None,
            "source_evidence": [],
            "source_candidate_id": creative_candidate_id,
            "creative_id_origin": "source.Ad Name",
        })["source_evidence"].append(ref)

        plan_row_id = ref
        plan_row_counts[plan_row_id] = plan_row_counts.get(plan_row_id, 0) + 1
        activation_id = _stable_id(
            "ACT", campaign_key, plan_row_id, audience_name, creative_id,
            platform, flight_start, flight_end,
        )
        activations.append({
            "activation_id": activation_id,
            "plan_row_id": plan_row_id,
            "plan_row_id_origin": "source_ref",
            "audience_row_id": audience_row_id,
            "creative_row_id": creative_row_id,
            "source_ref": ref,
            "platform": platform,
            "flight_start": flight_start,
            "flight_end": flight_end,
            "planned_budget": None,
            "buying_method": None,
            "serving_location": inputs.get("placement (medium)"),
            "size": size,
            "landing_page_url": destination_url,
            "operator_notes": None,
            "placement_name": activation.get("placement_name"),
            "final_tracking_url": activation.get("final_tracking_url"),
            "source_candidate_id": activation.get("activation_candidate_id"),
        })

    canonical_source_rows: list[dict[str, Any]] = []
    for source_row in group["source_rows"]:
        row_copy = deepcopy(source_row)
        ref = row_copy["source_ref"]
        row_copy["canonical_disposition"] = "ACTIVATION_SOURCE" if ref in eligible_refs else "EVIDENCE_ONLY_EXCLUDED"
        canonical_source_rows.append(row_copy)

    campaign_evidence = list(group.get("source_evidence") or [row["source_ref"] for row in canonical_source_rows])
    campaign = {
        "campaign_key": campaign_key,
        "client": client,
        "campaign_name": campaign_name,
        "objective": objective,
        "market": market,
        "currency": currency,
        "platform": platform,
        "flight_start": flight_start,
        "flight_end": flight_end,
        "flight_scope": "exact",
        "source_evidence": campaign_evidence,
        "source_campaign_candidate_id": campaign_source.get("campaign_candidate_id"),
        "platform_origin": campaign_source.get("platform_origin"),
    }

    source = deepcopy(boundary.get("source") or {})
    source.setdefault("sheets", ["tracking code generator"])
    source["read_only"] = True
    source["platform_group_id"] = platform_group_id
    source["adapter"] = "historical_tracking_platform_group_v0"

    excluded_refs = sorted(set(row_by_ref).difference(eligible_refs))
    return {
        "schema": CANONICAL_SCHEMA,
        "canonical_status": "READY",
        "source": source,
        "counts": {
            "source_rows": len(canonical_source_rows),
            "campaigns": 1,
            "audiences": len(audiences_by_candidate),
            "creatives": len(creatives_by_candidate),
            "activations": len(activations),
        },
        "campaign": campaign,
        "audiences": sorted(audiences_by_candidate.values(), key=lambda item: item["audience_row_id"]),
        "creatives": sorted(creatives_by_candidate.values(), key=lambda item: item["creative_row_id"]),
        "activations": sorted(activations, key=lambda item: item["source_ref"]),
        "source_rows": canonical_source_rows,
        "relationships": {
            "plan_row_activation_counts": dict(sorted(plan_row_counts.items())),
            "one_to_many_plan_rows": sorted(key for key, count in plan_row_counts.items() if count > 1),
            "excluded_source_rows": excluded_refs,
            "platform_group_id": platform_group_id,
        },
        "ambiguities": [],
        "validation_issues": [],
    }
