#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
from copy import deepcopy

from canonical_qa_package_bridge import compile_qa_package
from duplicate_activation_qa import DECISION, apply_duplicate_activation_qa_decision
from historical_tracking_mapper import INPUT_HEADERS, map_tracking_rows
from human_confirmation_overlay import apply_human_confirmations
from platform_group_canonical_adapter import adapt_platform_group
from platform_grouping_boundary import group_by_platform_boundary
from server import TRAFFICKING_COLUMNS


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


def _eight_adobe_canonical() -> dict:
    rows = [[None] * 44, INPUT_HEADERS + [None] * 30]
    for final in (1, 2):
        for width, height in ((160, 600), (300, 250), (728, 90), (970, 250)):
            rows.append(_row(
                "Adobe DSP",
                f"Example | UK | Brand | Campaign Innovators 2024 | Q3-24 | Display | Adobe-DSP | {width}x{height} | Finals {final}",
                width,
                height,
                "Standard Display",
                "display ad",
            ))
    rows.append(_row("Linkedin", "Campaign Innovation 2024 | Retargeting | LinkedIn | Final Social 1 | Static Image", 1920, 1080, "Image", "social media"))
    rows.append(_row("Linkedin", "Campaign Innovation 2024 | Retargeting | LinkedIn | Final Social 2 | Static Image", 1920, 1080, "Image", "social media"))
    rows.append(_row("Facebook", "Campaign Innovation 2024 | Retargeting | Facebook | Facebook 1 | Static Image", 1920, 1080, "Image", "social media"))
    duplicate = _row("Facebook", "Campaign Innovation 2024 | Retargeting | Facebook | Facebook 2 | Static Image", 1920, 1080, "Image", "social media")
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
        "source_refs": ["tracking code generator!14", "tracking code generator!15"],
        "keep_source_ref": "tracking code generator!14",
    })
    boundary = group_by_platform_boundary(deduped)
    adobe = next(group for group in boundary["platform_groups"] if group["platform"] == "Adobe DSP")
    return adapt_platform_group(boundary, adobe["platform_group_id"])


def main() -> None:
    canonical = _eight_adobe_canonical()
    before = deepcopy(canonical)
    result = compile_qa_package(canonical)

    assert result["status"] == "READY_FOR_APPROVAL"
    assert result["compiled"]["status"] == "COMPILED_PREVIEW"
    assert result["compiled"]["compile_result"]["counts"] == {"build_rows": 8}
    assert result["qa"]["status"] == "PASS"
    assert result["qa"]["counts"]["failures"] == 0
    assert result["package"]["package_created"] is True
    assert result["package"]["publishes"] is False
    assert result["package"]["artifact"]["columns"] == TRAFFICKING_COLUMNS
    assert result["package"]["artifact"]["row_count"] == 8
    assert canonical == before

    reader = csv.DictReader(io.StringIO(result["package"]["artifact"]["content"]))
    exported = list(reader)
    assert reader.fieldnames == TRAFFICKING_COLUMNS
    assert len(exported) == 8
    assert all(row["Platform"] == "Adobe DSP" for row in exported)
    assert all(row["Placement_Name"] for row in exported)
    assert all(row["Landing_Page_URL"].startswith("https://") for row in exported)
    assert all(row["Final_Tracking_URL"].startswith("https://") for row in exported)

    broken = deepcopy(canonical)
    broken["activations"][0]["final_tracking_url"] = None
    blocked = compile_qa_package(broken)
    assert blocked["status"] == "BLOCKED"
    assert blocked["qa"]["status"] == "BLOCKED"
    assert blocked["package"]["package_created"] is False
    assert blocked["package"]["artifact"] is None
    assert any(item["check_id"] == "QA-TRACKING-URL-001" for item in blocked["qa"]["failures"])

    assert TRAFFICKING_COLUMNS == [
        "Campaign_Key", "Plan_Row_ID", "Platform", "Campaign_Name", "Placement_Name",
        "Ad_Format", "Flight_Dates", "Audience_Targeting", "Creative_ID", "Landing_Page_URL",
        "Final_Tracking_URL", "Activation_ID", "Audience_Row_ID", "Creative_Row_ID",
    ]

    print("PASS: 8 Adobe build rows complete deterministic QA with zero failures")
    print("PASS: QA PASS creates one 8-row in-memory nexus_trafficking.csv")
    print("PASS: export columns exactly match the frozen 14-column trafficking contract")
    print("PASS: source-backed placement/landing/tracking values populate the frozen columns")
    print("PASS: missing tracking evidence blocks package generation fail-closed")


if __name__ == "__main__":
    main()
