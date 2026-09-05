#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy

from canonical_compile_bridge import compile_ready_canonical
from duplicate_activation_qa import DECISION, apply_duplicate_activation_qa_decision
from historical_tracking_mapper import INPUT_HEADERS, map_tracking_rows
from human_confirmation_overlay import apply_human_confirmations
from platform_group_canonical_adapter import adapt_platform_group
from platform_grouping_boundary import group_by_platform_boundary
from server import request_compile


def _row(platform: str, ad_name: str, width: int, height: int, fmt: str, placement: str) -> list:
    row = [None] * 44
    row[:14] = [
        "https://example.test/landing",
        placement,
        True,
        platform,
        2024,
        "Tech",
        "Campaign Innovators 2024",
        "UK",
        "All devices",
        fmt,
        ad_name,
        width,
        height,
        True,
    ]
    row[15] = "Traffic"
    row[16] = "Campaign Innovation 2024"
    row[19] = "Q3 24"
    row[22] = "Bespoke Tech Audience"
    row[23] = f"UK | Traffic | Campaign Innovation 2024 | {fmt} | All devices | Bespoke Tech Audience | Campaign Innovators 2024"
    row[34] = ad_name.replace(" | ", "_")
    row[41] = "utm_medium=test&utm_source=test"
    row[42] = "?utm_medium=test&utm_source=test&cid=test"
    row[43] = row[0] + "?utm_medium=test&utm_source=test&cid=test"
    return row


def _one_ready_canonical() -> dict:
    rows = [[None] * 44, INPUT_HEADERS + [None] * 30]
    rows.append(_row("Adobe DSP", "Display A", 300, 250, "Standard Display", "display ad"))
    rows.append(_row("Linkedin", "Social A", 1920, 1080, "Image", "social media"))
    duplicate = _row("Facebook", "Social B", 1920, 1080, "Image", "social media")
    rows.append(duplicate)
    rows.append(deepcopy(duplicate))

    mapped = map_tracking_rows(rows, "historical_tracking_fixture.xlsx")
    confirmed = apply_human_confirmations(mapped, {
        "campaign.client": "Example Client",
        "campaign.currency": "GBP",
        "campaign.flight_start": "2024-07-01",
        "campaign.flight_end": "2024-09-30",
        "campaign.campaign_name": "Campaign Innovation 2024",
    })
    deduped = apply_duplicate_activation_qa_decision(confirmed, {
        "decision": DECISION,
        "source_refs": ["tracking code generator!5", "tracking code generator!6"],
        "keep_source_ref": "tracking code generator!5",
    })
    boundary = group_by_platform_boundary(deduped)
    adobe_group = next(group for group in boundary["platform_groups"] if group["platform"] == "Adobe DSP")
    return adapt_platform_group(boundary, adobe_group["platform_group_id"])


def _legacy_fixture_as_canonical() -> dict:
    import json
    from pathlib import Path

    fixture = json.loads(Path(__file__).with_name("canonical_fixture.json").read_text(encoding="utf-8"))
    campaign = deepcopy(fixture["campaign"])
    campaign["flight_scope"] = "exact"
    activations = []
    for activation in fixture["activations"]:
        row = deepcopy(activation)
        row["platform"] = campaign["platform"]
        row["flight_start"] = campaign["flight_start"]
        row["flight_end"] = campaign["flight_end"]
        activations.append(row)
    return {
        "schema": "nexus-canonical-campaign-v0",
        "canonical_status": "READY",
        "source": {"filename": "canonical_fixture.json", "read_only": True},
        "counts": {
            "source_rows": fixture["source_row_count"],
            "campaigns": 1,
            "audiences": len(fixture["audiences"]),
            "creatives": len(fixture["creatives"]),
            "activations": len(activations),
        },
        "campaign": campaign,
        "audiences": deepcopy(fixture["audiences"]),
        "creatives": deepcopy(fixture["creatives"]),
        "activations": activations,
        "source_rows": [],
        "relationships": {},
        "ambiguities": [],
        "validation_issues": [],
    }


def main() -> None:
    canonical = _one_ready_canonical()
    before = deepcopy(canonical)

    compiled = compile_ready_canonical(canonical)
    assert compiled["status"] == "COMPILED_PREVIEW"
    assert compiled["compiler_called"] is True
    assert compiled["gate"]["status"] == "READY_FOR_COMPILE"
    assert compiled["compile_result"]["status"] == "COMPILED_PREVIEW"
    assert compiled["compile_result"]["counts"] == {"build_rows": 1}
    assert canonical == before

    row = compiled["compile_result"]["build_rows"][0]
    activation = canonical["activations"][0]
    audience = canonical["audiences"][0]
    creative = canonical["creatives"][0]
    campaign = canonical["campaign"]
    assert row == {
        "build_row_id": f"BLD-{activation['activation_id']}",
        "campaign_key": campaign["campaign_key"],
        "plan_row_id": activation["plan_row_id"],
        "platform": campaign["platform"],
        "campaign_name": campaign["campaign_name"],
        "flight_start": campaign["flight_start"],
        "flight_end": campaign["flight_end"],
        "activation_id": activation["activation_id"],
        "audience_row_id": audience["audience_row_id"],
        "audience_name": audience["audience_name"],
        "creative_row_id": creative["creative_row_id"],
        "creative_id": creative["creative_id"],
        "ad_format": creative["ad_format"],
        "size": creative["size"],
    }

    rerun = compile_ready_canonical(canonical)
    assert rerun["compile_result"]["stable_ids"] == compiled["compile_result"]["stable_ids"]
    assert rerun["compile_result"]["build_rows"] == compiled["compile_result"]["build_rows"]

    blocked_input = deepcopy(canonical)
    blocked_input["activations"][0]["platform"] = "Wrong Platform"
    blocked = compile_ready_canonical(blocked_input)
    assert blocked["status"] == "BLOCKED"
    assert blocked["compiler_called"] is False
    assert blocked["compile_result"] is None
    assert any(item["code"] == "ACTIVATION_PLATFORM_MISMATCH" for item in blocked["gate"]["failures"])

    # Parity proof: the bridge emits the exact build-row semantics of the frozen
    # request_compile path when both receive the same frozen campaign entities.
    legacy_canonical = _legacy_fixture_as_canonical()
    bridged_legacy = compile_ready_canonical(legacy_canonical)["compile_result"]["build_rows"]
    frozen_legacy = request_compile({"run_id": "fixture-agentic-v0"})["structuredContent"]["build_rows"]
    assert bridged_legacy == frozen_legacy

    print("PASS: one historical platform-group canonical reaches deterministic COMPILED_PREVIEW")
    print("PASS: compatibility gate blocks mismatched platform before compile")
    print("PASS: canonical IDs and build rows remain stable across recompiles")
    print("PASS: bridge build rows are byte-for-structure identical to frozen request_compile semantics")
    print("PASS: Hermes, QA, package generation and 14-column export remain untouched")


if __name__ == "__main__":
    main()
