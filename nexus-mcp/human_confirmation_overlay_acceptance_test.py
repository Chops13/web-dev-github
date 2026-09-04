#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy

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


def _fixture_candidates() -> dict:
    rows = [[None] * 44, INPUT_HEADERS + [None] * 30]
    rows.append(_row("Adobe DSP", "Display A", 300, 250, "Standard Display", "display ad"))
    rows.append(_row("Linkedin", "Social A", 1920, 1080, "Image", "social media"))
    duplicate = _row("Facebook", "Social B", 1920, 1080, "Image", "social media")
    rows.append(duplicate)
    rows.append(deepcopy(duplicate))
    return map_tracking_rows(rows, "historical_tracking_fixture.xlsx")


def main() -> None:
    candidates = _fixture_candidates()
    before = deepcopy(candidates)

    confirmed = apply_human_confirmations(candidates, {
        "campaign.client": "Example Client",
        "campaign.currency": "gbp",
        "campaign.flight_start": "2024-07-01",
        "campaign.flight_end": "2024-09-30",
        "campaign.campaign_name": "Campaign Innovation 2024",
    })

    campaign = confirmed["campaigns"][0]
    assert campaign["client"] == "Example Client"
    assert campaign["currency"] == "GBP"
    assert campaign["flight_start"] == "2024-07-01"
    assert campaign["flight_end"] == "2024-09-30"
    assert campaign["campaign_name"] == "Campaign Innovation 2024"

    unresolved_fields = [item["field"] for item in confirmed["ambiguities"]]
    assert unresolved_fields == ["campaign.platform"]
    assert confirmed["ambiguities"][0]["candidates"] == ["Adobe DSP", "Facebook", "Linkedin"]
    assert campaign["platform"] is None
    assert confirmed["mapper_status"] == "NEEDS_CONFIRMATION"
    assert confirmed["compiler_allowed"] is False

    assert confirmed["validation_issues"]
    assert confirmed["validation_issues"][0]["type"] == "DUPLICATE_ACTIVATION_CANDIDATE"
    assert confirmed["validation_issues"][0]["blocking"] is True

    assert [entry["field"] for entry in confirmed["human_confirmations"]] == [
        "campaign.client",
        "campaign.currency",
        "campaign.flight_start",
        "campaign.flight_end",
        "campaign.campaign_name",
    ]
    assert all(entry["origin"] == "human_confirmation" for entry in confirmed["human_confirmations"])
    assert candidates == before
    assert confirmed["source_rows"] == before["source_rows"]

    try:
        apply_human_confirmations(candidates, {"campaign.platform": "Adobe DSP"})
    except ValueError as exc:
        assert "Unsupported human confirmation fields" in str(exc)
    else:
        raise AssertionError("Platform confirmation must be rejected")

    try:
        apply_human_confirmations(candidates, {"campaign.campaign_name": "Invented Campaign"})
    except ValueError as exc:
        assert "source-derived candidates" in str(exc)
    else:
        raise AssertionError("Invented campaign-name confirmation must be rejected")

    try:
        apply_human_confirmations(candidates, {
            "campaign.flight_start": "2024-10-01",
            "campaign.flight_end": "2024-09-30",
        })
    except ValueError as exc:
        assert "on or before" in str(exc)
    else:
        raise AssertionError("Reversed flight dates must be rejected")

    print("PASS: five permitted human confirmations overlay without mutating source candidates")
    print("PASS: client/currency/exact flight dates/campaign-name ambiguity resolved by human evidence")
    print("PASS: mixed-platform ambiguity remains blocking and cannot be human-overridden here")
    print("PASS: duplicate activation blocker remains intact; compiler stays disallowed")


if __name__ == "__main__":
    main()
