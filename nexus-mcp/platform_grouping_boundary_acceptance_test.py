#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy

from duplicate_activation_qa import DECISION, apply_duplicate_activation_qa_decision
from historical_tracking_mapper import INPUT_HEADERS, map_tracking_rows
from human_confirmation_overlay import apply_human_confirmations
from platform_grouping_boundary import RESOLUTION, group_by_platform_boundary


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


def _ready_for_platform_boundary() -> dict:
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
    return apply_duplicate_activation_qa_decision(confirmed, {
        "decision": DECISION,
        "source_refs": ["tracking code generator!5", "tracking code generator!6"],
        "keep_source_ref": "tracking code generator!5",
    })


def main() -> None:
    candidates = _ready_for_platform_boundary()
    before = deepcopy(candidates)

    assert [item["field"] for item in candidates["ambiguities"]] == ["campaign.platform"]
    assert not [issue for issue in candidates["validation_issues"] if issue.get("blocking", True)]
    assert candidates["compiler_allowed"] is False

    grouped = group_by_platform_boundary(candidates)

    assert candidates == before
    assert grouped["schema"] == "nexus-platform-groups-v0"
    assert grouped["status"] == "READY_PLATFORM_GROUPS"
    assert grouped["reason"] == "MIXED_PLATFORM_BOUNDARY_RESOLVED"
    assert grouped["compiler_allowed"] is False
    assert grouped["next_stage"] == "PLATFORM_GROUP_TO_CANONICAL_ADAPTER"
    assert grouped["counts"] == {
        "source_rows": 4,
        "platform_groups": 3,
        "eligible_activations": 3,
        "excluded_activations": 1,
    }
    assert grouped["source_rows"] == before["source_rows"]
    assert grouped["unresolved_ambiguities"] == []
    assert grouped["blocking_validation_issues"] == []

    groups = {group["platform"]: group for group in grouped["platform_groups"]}
    assert sorted(groups) == ["Adobe DSP", "Facebook", "Linkedin"]
    assert all(group["status"] == "READY_FOR_CANONICAL_ADAPTER" for group in groups.values())
    assert all(group["campaign"]["platform"] == platform for platform, group in groups.items())
    assert all(group["campaign"]["platform_candidates"] == [platform] for platform, group in groups.items())
    assert all(group["campaign"]["platform_origin"] == "source_activation_partition" for group in groups.values())
    assert all(len(group["activation_candidates"]) == 1 for group in groups.values())

    facebook = groups["Facebook"]
    assert facebook["source_evidence"] == [
        "tracking code generator!5",
        "tracking code generator!6",
    ]
    assert len(facebook["eligible_activation_candidate_ids"]) == 1
    assert len(facebook["excluded_activation_candidate_ids"]) == 1
    assert [row["source_ref"] for row in facebook["source_rows"]] == [
        "tracking code generator!5",
        "tracking code generator!6",
    ]

    assert grouped["boundary_resolutions"] == [{
        "field": "campaign.platform",
        "resolution": RESOLUTION,
        "origin": "deterministic_rule",
        "source_candidates": ["Adobe DSP", "Facebook", "Linkedin"],
        "platform_group_ids": [group["platform_group_id"] for group in grouped["platform_groups"]],
    }]

    # This stage resolves only platform structure. Any other unresolved campaign fact
    # must still fail closed rather than hitching a ride through the partition.
    not_ready = deepcopy(candidates)
    not_ready["ambiguities"].insert(0, {
        "field": "campaign.currency",
        "reason": "MISSING_SOURCE_FIELD",
        "candidates": [],
        "resolution_required": True,
    })
    rejected = group_by_platform_boundary(not_ready)
    assert rejected["status"] == "BLOCKED"
    assert rejected["reason"] == "PRECONDITIONS_FAILED"
    assert rejected["platform_groups"] == []
    assert rejected["compiler_allowed"] is False

    print("PASS: mixed source campaign partitions deterministically into 3 exact platform groups")
    print("PASS: 4 source rows remain preserved, including the prior excluded duplicate row")
    print("PASS: each platform group contains only eligible activations for that exact platform")
    print("PASS: no compiler/Hermes call occurs; groups stop at READY_FOR_CANONICAL_ADAPTER")
    print("PASS: unrelated ambiguity still fails closed")


if __name__ == "__main__":
    main()
