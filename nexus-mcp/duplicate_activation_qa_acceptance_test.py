#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy

from duplicate_activation_qa import DECISION, apply_duplicate_activation_qa_decision
from historical_tracking_mapper import INPUT_HEADERS, map_tracking_rows
from human_confirmation_overlay import apply_human_confirmations


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


def _confirmed_candidates() -> dict:
    rows = [[None] * 44, INPUT_HEADERS + [None] * 30]
    rows.append(_row("Adobe DSP", "Display A", 300, 250, "Standard Display", "display ad"))
    rows.append(_row("Linkedin", "Social A", 1920, 1080, "Image", "social media"))
    duplicate = _row("Facebook", "Social B", 1920, 1080, "Image", "social media")
    rows.append(duplicate)
    rows.append(deepcopy(duplicate))

    mapped = map_tracking_rows(rows, "historical_tracking_fixture.xlsx")
    return apply_human_confirmations(mapped, {
        "campaign.client": "Example Client",
        "campaign.currency": "GBP",
        "campaign.flight_start": "2024-07-01",
        "campaign.flight_end": "2024-09-30",
        "campaign.campaign_name": "Campaign Innovation 2024",
    })


def main() -> None:
    candidates = _confirmed_candidates()
    before = deepcopy(candidates)

    assert [item["field"] for item in candidates["ambiguities"]] == ["campaign.platform"]
    duplicate_issues = [
        issue for issue in candidates["validation_issues"]
        if issue["type"] == "DUPLICATE_ACTIVATION_CANDIDATE"
    ]
    assert len(duplicate_issues) == 1
    assert duplicate_issues[0]["blocking"] is True
    assert duplicate_issues[0]["source_refs"] == [
        "tracking code generator!5",
        "tracking code generator!6",
    ]

    resolved = apply_duplicate_activation_qa_decision(candidates, {
        "decision": DECISION,
        "source_refs": ["tracking code generator!5", "tracking code generator!6"],
        "keep_source_ref": "tracking code generator!5",
    })

    assert candidates == before
    assert resolved["source_rows"] == before["source_rows"]
    assert len(resolved["source_rows"]) == 4
    assert len(resolved["activations"]) == 4

    issue = [
        item for item in resolved["validation_issues"]
        if item["type"] == "DUPLICATE_ACTIVATION_CANDIDATE"
    ][0]
    assert issue["blocking"] is False
    assert issue["resolution"] == {
        "decision": DECISION,
        "origin": "source_row_qa_decision",
        "keep_source_ref": "tracking code generator!5",
        "exclude_source_refs": ["tracking code generator!6"],
    }

    activation_by_ref = {a["source_ref"]: a for a in resolved["activations"]}
    assert activation_by_ref["tracking code generator!5"]["eligible_for_compile"] is True
    assert activation_by_ref["tracking code generator!5"]["source_row_qa"]["status"] == "RETAINED"
    assert activation_by_ref["tracking code generator!6"]["eligible_for_compile"] is False
    assert activation_by_ref["tracking code generator!6"]["source_row_qa"]["status"] == "EXCLUDED_DUPLICATE"

    assert resolved["source_row_qa_decisions"] == [{
        "decision": DECISION,
        "origin": "source_row_qa_decision",
        "source_refs": ["tracking code generator!5", "tracking code generator!6"],
        "keep_source_ref": "tracking code generator!5",
        "exclude_source_refs": ["tracking code generator!6"],
    }]

    # Mixed-platform source semantics remain the only ambiguity and stay blocking.
    assert [item["field"] for item in resolved["ambiguities"]] == ["campaign.platform"]
    assert resolved["campaigns"][0]["platform"] is None
    assert resolved["campaigns"][0]["platform_candidates"] == ["Adobe DSP", "Facebook", "Linkedin"]
    assert resolved["mapper_status"] == "NEEDS_CONFIRMATION"
    assert resolved["compiler_allowed"] is False

    try:
        apply_duplicate_activation_qa_decision(candidates, {
            "decision": DECISION,
            "source_refs": ["tracking code generator!4", "tracking code generator!5"],
            "keep_source_ref": "tracking code generator!5",
        })
    except ValueError as exc:
        assert "exactly one unresolved duplicate" in str(exc)
    else:
        raise AssertionError("Non-duplicate source rows must be rejected")

    try:
        apply_duplicate_activation_qa_decision(candidates, {
            "decision": "DROP_DUPLICATES_AUTOMATICALLY",
            "source_refs": ["tracking code generator!5", "tracking code generator!6"],
            "keep_source_ref": "tracking code generator!5",
        })
    except ValueError as exc:
        assert "decision must equal" in str(exc)
    else:
        raise AssertionError("Automatic duplicate removal must be rejected")

    try:
        apply_duplicate_activation_qa_decision(candidates, {
            "decision": DECISION,
            "source_refs": ["tracking code generator!5", "tracking code generator!6"],
            "keep_source_ref": "tracking code generator!7",
        })
    except ValueError as exc:
        assert "must be one of source_refs" in str(exc)
    else:
        raise AssertionError("Retained row must come from the duplicate source-row set")

    print("PASS: duplicate activation resolved only by explicit source-row QA decision")
    print("PASS: retained/excluded source rows stay preserved with auditable dispositions")
    print("PASS: duplicate blocker clears without deleting source rows or activation candidates")
    print("PASS: mixed-platform ambiguity remains blocking; compiler stays disallowed")


if __name__ == "__main__":
    main()
