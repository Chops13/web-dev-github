#!/usr/bin/env python3
"""Bridge one READY Nexus canonical payload into the existing deterministic compile semantics.

This is deliberately narrow. It accepts only nexus-canonical-campaign-v0 payloads that
pass the existing canonical compatibility gate, then emits the same build-row shape as
the frozen request_compile path. It does not call or modify Hermes, MCP, QA, package
generation, or the frozen trafficking export contract.

No campaign, audience, creative, or activation identity is generated here. The bridge
consumes the deterministic IDs already present in canonical input and creates only the
existing derived build_row_id = BLD-{activation_id}.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from canonical_gate import assess_canonical_compatibility


def _index_unique(items: Any, key: str, entity: str) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError(f"{entity} must be a list")
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{entity} must contain objects")
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{entity}.{key} is required")
        value = value.strip()
        if value in indexed:
            raise ValueError(f"duplicate {entity}.{key}: {value}")
        indexed[value] = item
    return indexed


def compile_ready_canonical(canonical: dict[str, Any]) -> dict[str, Any]:
    """Compile one gate-compatible canonical campaign using frozen build-row semantics."""
    gate = assess_canonical_compatibility(canonical)
    if not gate.get("compiler_allowed"):
        return {
            "status": "BLOCKED",
            "compiler_called": False,
            "gate": gate,
            "compile_result": None,
        }

    before = deepcopy(canonical)
    campaign = canonical["campaign"]
    audiences = _index_unique(canonical.get("audiences"), "audience_row_id", "audiences")
    creatives = _index_unique(canonical.get("creatives"), "creative_row_id", "creatives")
    activations = canonical.get("activations")
    if not isinstance(activations, list) or not activations:
        raise ValueError("activations must be a non-empty list")

    build_rows: list[dict[str, Any]] = []
    seen_activation_ids: set[str] = set()
    seen_build_row_ids: set[str] = set()

    for activation in activations:
        if not isinstance(activation, dict):
            raise ValueError("activations must contain objects")
        activation_id = activation.get("activation_id")
        if not isinstance(activation_id, str) or not activation_id.strip():
            raise ValueError("activation.activation_id is required")
        activation_id = activation_id.strip()
        if activation_id in seen_activation_ids:
            raise ValueError(f"duplicate activation.activation_id: {activation_id}")
        seen_activation_ids.add(activation_id)

        audience_row_id = activation.get("audience_row_id")
        creative_row_id = activation.get("creative_row_id")
        if audience_row_id not in audiences:
            raise ValueError(f"activation {activation_id} references unknown audience_row_id: {audience_row_id}")
        if creative_row_id not in creatives:
            raise ValueError(f"activation {activation_id} references unknown creative_row_id: {creative_row_id}")

        audience = audiences[audience_row_id]
        creative = creatives[creative_row_id]
        build_row_id = f"BLD-{activation_id}"
        if build_row_id in seen_build_row_ids:
            raise ValueError(f"duplicate build_row_id: {build_row_id}")
        seen_build_row_ids.add(build_row_id)

        build_rows.append({
            "build_row_id": build_row_id,
            "campaign_key": campaign["campaign_key"],
            "plan_row_id": activation["plan_row_id"],
            "platform": campaign["platform"],
            "campaign_name": campaign["campaign_name"],
            "flight_start": campaign["flight_start"],
            "flight_end": campaign["flight_end"],
            "activation_id": activation_id,
            "audience_row_id": audience_row_id,
            "audience_name": audience["audience_name"],
            "creative_row_id": creative_row_id,
            "creative_id": creative["creative_id"],
            "ad_format": creative["ad_format"],
            "size": creative["size"],
        })

    if canonical != before:
        raise AssertionError("compile bridge mutated canonical input")

    source = canonical.get("source") or {}
    compile_result = {
        "stub": False,
        "tool": "request_compile",
        "status": "COMPILED_PREVIEW",
        "read_only": True,
        "in_memory": True,
        "writes_files": False,
        "source_schema": canonical.get("schema"),
        "source_platform_group_id": source.get("platform_group_id"),
        "counts": {"build_rows": len(build_rows)},
        "stable_ids": {
            "campaign_key": campaign["campaign_key"],
            "activation_ids": [row["activation_id"] for row in build_rows],
            "build_row_ids": [row["build_row_id"] for row in build_rows],
        },
        "build_rows": build_rows,
    }
    return {
        "status": "COMPILED_PREVIEW",
        "compiler_called": True,
        "gate": gate,
        "compile_result": compile_result,
    }
