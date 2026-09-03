#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy

from historical_tracking_mapper import INPUT_HEADERS, map_tracking_rows


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


def main() -> None:
    rows = [[None] * 44, INPUT_HEADERS + [None] * 30]
    for final in (1, 2):
        for width, height in ((160, 600), (300, 250), (728, 90), (970, 250)):
            rows.append(_row("Adobe DSP", f"Example | UK | Brand | Campaign Innovators 2024 | Q3-24 | Display | Adobe-DSP | {width}x{height} | Finals {final}", width, height, "Standard Display", "display ad"))
    rows.append(_row("Linkedin", "Campaign Innovation 2024 | Retargeting | LinkedIn | Final Social 1 | Static Image", 1920, 1080, "Image", "social media"))
    rows.append(_row("Linkedin", "Campaign Innovation 2024 | Retargeting | LinkedIn | Final Social 2 | Static Image", 1920, 1080, "Image", "social media"))
    rows.append(_row("Facebook", "Campaign Innovation 2024 | Retargeting | Facebook | Facebook 1 | Static Image", 1920, 1080, "Image", "social media"))
    duplicate = _row("Facebook", "Campaign Innovation 2024 | Retargeting | Facebook | Facebook 2 | Static Image", 1920, 1080, "Image", "social media")
    rows.append(duplicate)
    rows.append(deepcopy(duplicate))

    before = deepcopy(rows)
    result = map_tracking_rows(rows, "historical_tracking_fixture.xlsx")

    assert result["mapper_status"] == "NEEDS_CONFIRMATION"
    assert result["compiler_allowed"] is False
    assert result["counts"] == {
        "source_rows": 13,
        "campaign_candidates": 1,
        "audience_candidates": 1,
        "creative_candidates": 12,
        "activation_candidates": 13,
    }
    assert [r["source_ref"] for r in result["source_rows"]] == [f"tracking code generator!{n}" for n in range(3, 16)]
    assert len({a["activation_candidate_id"] for a in result["activations"]}) == 13

    campaign = result["campaigns"][0]
    assert campaign["objective"] == "Traffic"
    assert campaign["market"] == "UK"
    assert campaign["campaign_period"] == "Q3 24"
    assert campaign["campaign_name"] is None
    assert campaign["campaign_name_candidates"] == ["Campaign Innovation 2024", "Campaign Innovators 2024"]
    assert campaign["platform"] is None
    assert campaign["platform_candidates"] == ["Adobe DSP", "Facebook", "Linkedin"]
    assert campaign["client"] is None and campaign["currency"] is None
    assert campaign["flight_start"] is None and campaign["flight_end"] is None

    assert [a["field"] for a in result["ambiguities"]] == [
        "campaign.client", "campaign.currency", "campaign.flight_start", "campaign.flight_end",
        "campaign.campaign_name", "campaign.platform",
    ]
    assert result["validation_issues"] and result["validation_issues"][0]["source_refs"] == [
        "tracking code generator!14", "tracking code generator!15"
    ]
    assert result["validation_issues"][0]["blocking"] is True
    assert rows == before

    print("PASS: 13 source rows preserved read-only with exact row evidence")
    print("PASS: 1 campaign / 1 audience / 12 creative / 13 activation candidates emitted")
    print("PASS: missing/conflicting campaign facts block compilation without invention")
    print("PASS: duplicate source rows 14/15 retained and flagged as blocking")


if __name__ == "__main__":
    main()