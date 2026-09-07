#!/usr/bin/env python3
"""Acceptance test for the DV360 read-only capability declaration.

Uses frozen synthetic Campaign / InsertionOrder / LineItem payloads only.
No API connection, OAuth, credentials, or writes.

Proof target:
- fields explicitly declared comparable may deterministically emit MATCH;
- undeclared fields must fail closed as UNSUPPORTED/BLOCKED;
- no undeclared field may ever emit MATCH.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CAPABILITY_PATH = ROOT / "capabilities" / "dv360-read-v1.json"


def get_path(payload: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def comparable_map(capability: dict[str, Any], resource_name: str) -> dict[str, dict[str, Any]]:
    resource = capability["resources"][resource_name]
    return {entry["path"]: entry for entry in resource["comparable_fields"]}


def compare_expected_fields(
    capability: dict[str, Any],
    resource_name: str,
    expected_fields: dict[str, Any],
    actual: dict[str, Any],
) -> dict[str, Any]:
    declared = comparable_map(capability, resource_name)
    records: list[dict[str, Any]] = []

    for path, expected in expected_fields.items():
        declaration = declared.get(path)
        if declaration is None:
            records.append({
                "path": path,
                "state": "UNSUPPORTED",
                "blocking": True,
                "reason": "FIELD_NOT_DECLARED_COMPARABLE",
            })
            continue

        present, actual_value = get_path(actual, path)
        if not present:
            records.append({
                "path": path,
                "state": "READ_ERROR",
                "blocking": True,
                "reason": "DECLARED_FIELD_MISSING_FROM_ACTUAL",
            })
            continue

        mode = declaration["comparison"]
        if mode in {"EXACT", "NUMERIC_EXACT", "EXACT_RELATIONSHIP"}:
            matches = expected == actual_value
        elif mode == "SET_EXACT":
            matches = set(expected) == set(actual_value)
        else:
            records.append({
                "path": path,
                "state": "UNSUPPORTED",
                "blocking": True,
                "reason": f"COMPARISON_MODE_NOT_IMPLEMENTED:{mode}",
            })
            continue

        records.append({
            "path": path,
            "state": "MATCH" if matches else "DRIFT",
            "blocking": not matches,
            "comparison": mode,
            "expected": expected,
            "actual": actual_value,
        })

    status = "BLOCKED" if any(r["state"] in {"UNSUPPORTED", "READ_ERROR"} for r in records) else (
        "DRIFTED" if any(r["state"] == "DRIFT" for r in records) else "RECONCILED"
    )
    return {"status": status, "records": records}


def main() -> None:
    capability = json.loads(CAPABILITY_PATH.read_text(encoding="utf-8"))

    assert capability["schema_version"] == "nexus-platform-capability-v1"
    assert capability["capability_id"] == "dv360-read-v1"
    assert capability["platform"] == "DV360"
    assert capability["api_version"] == "v4"
    assert capability["mode"] == "READ_ONLY"
    assert capability["writes_allowed"] is False
    assert capability["oauth_flow_in_scope"] is False
    assert capability["other_platforms_in_scope"] is False

    campaign = {
        "campaignId": "1001",
        "advertiserId": "9001",
        "displayName": "Q4 Enterprise Growth",
        "entityStatus": "ENTITY_STATUS_ACTIVE",
        "campaignGoal": {
            "campaignGoalType": "CAMPAIGN_GOAL_TYPE_PERFORMANCE",
            "performanceGoal": {
                "performanceGoalType": "PERFORMANCE_GOAL_TYPE_CPA",
                "performanceGoalAmountMicros": "25000000",
            },
        },
        "campaignFlight": {
            "plannedSpendAmountMicros": "430000000000",
            "plannedDates": {
                "startDate": {"year": 2026, "month": 10, "day": 1},
                "endDate": {"year": 2026, "month": 12, "day": 31},
            },
        },
        "frequencyCap": {"unlimited": False},
        "updateTime": "2026-09-07T12:00:00Z",
    }

    insertion_order = {
        "insertionOrderId": "2001",
        "advertiserId": "9001",
        "campaignId": "1001",
        "displayName": "UK Display Prospecting",
        "insertionOrderType": "RTB",
        "entityStatus": "ENTITY_STATUS_ACTIVE",
        "optimizationObjective": "PERFORMANCE_GOAL_TYPE_CPA",
        "kpi": {"kpiType": "KPI_TYPE_CPA", "kpiAmountMicros": "25000000"},
        "budget": {"budgetUnit": "BUDGET_UNIT_CURRENCY", "automationType": "INSERTION_ORDER_AUTOMATION_TYPE_NONE"},
        "pacing": {"pacingType": "PACING_TYPE_EVEN"},
        "updateTime": "2026-09-07T12:00:01Z",
    }

    line_item = {
        "lineItemId": "3001",
        "advertiserId": "9001",
        "campaignId": "1001",
        "insertionOrderId": "2001",
        "displayName": "Enterprise Decision Makers | Display",
        "lineItemType": "LINE_ITEM_TYPE_DISPLAY_DEFAULT",
        "entityStatus": "ENTITY_STATUS_ACTIVE",
        "flight": {
            "flightDateType": "LINE_ITEM_FLIGHT_DATE_TYPE_CUSTOM",
            "dateRange": {
                "startDate": {"year": 2026, "month": 10, "day": 1},
                "endDate": {"year": 2026, "month": 12, "day": 31},
            },
        },
        "budget": {
            "budgetAllocationType": "LINE_ITEM_BUDGET_ALLOCATION_TYPE_FIXED",
            "budgetUnit": "BUDGET_UNIT_CURRENCY",
            "maxAmount": "100000000000",
        },
        "creativeIds": ["5002", "5001"],
        "excludeNewExchanges": True,
        "containsEuPoliticalAds": "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
        "bidStrategy": {"fixedBid": {"bidAmountMicros": "9000000"}},
        "warningMessages": [],
    }

    campaign_expected = {
        "displayName": "Q4 Enterprise Growth",
        "entityStatus": "ENTITY_STATUS_ACTIVE",
        "campaignGoal.campaignGoalType": "CAMPAIGN_GOAL_TYPE_PERFORMANCE",
        "campaignFlight.plannedSpendAmountMicros": "430000000000",
        "campaignFlight.plannedDates.startDate": {"year": 2026, "month": 10, "day": 1},
    }
    io_expected = {
        "campaignId": "1001",
        "displayName": "UK Display Prospecting",
        "entityStatus": "ENTITY_STATUS_ACTIVE",
        "budget.budgetUnit": "BUDGET_UNIT_CURRENCY",
    }
    line_expected = {
        "campaignId": "1001",
        "insertionOrderId": "2001",
        "displayName": "Enterprise Decision Makers | Display",
        "flight.flightDateType": "LINE_ITEM_FLIGHT_DATE_TYPE_CUSTOM",
        "creativeIds": ["5001", "5002"],
    }

    campaign_result = compare_expected_fields(capability, "campaign", campaign_expected, campaign)
    io_result = compare_expected_fields(capability, "insertion_order", io_expected, insertion_order)
    line_result = compare_expected_fields(capability, "line_item", line_expected, line_item)

    assert campaign_result["status"] == "RECONCILED"
    assert io_result["status"] == "RECONCILED"
    assert line_result["status"] == "RECONCILED"
    assert all(r["state"] == "MATCH" for r in campaign_result["records"])
    assert all(r["state"] == "MATCH" for r in io_result["records"])
    assert all(r["state"] == "MATCH" for r in line_result["records"])

    # Undeclared/deferred fields are intentionally present in synthetic Actual State.
    # Asking Nexus to compare them must fail closed rather than manufacture MATCH.
    undeclared_cases = [
        ("campaign", {"frequencyCap.unlimited": False}, campaign),
        ("insertion_order", {"pacing.pacingType": "PACING_TYPE_EVEN"}, insertion_order),
        ("line_item", {"bidStrategy.fixedBid.bidAmountMicros": "9000000"}, line_item),
    ]
    for resource_name, expected, actual in undeclared_cases:
        result = compare_expected_fields(capability, resource_name, expected, actual)
        assert result["status"] == "BLOCKED"
        assert len(result["records"]) == 1
        assert result["records"][0]["state"] == "UNSUPPORTED"
        assert result["records"][0]["reason"] == "FIELD_NOT_DECLARED_COMPARABLE"

    # Strong invariant: every emitted MATCH must correspond to a declared comparable path.
    for resource_name, result in [
        ("campaign", campaign_result),
        ("insertion_order", io_result),
        ("line_item", line_result),
    ]:
        declared = set(comparable_map(capability, resource_name))
        matched = {r["path"] for r in result["records"] if r["state"] == "MATCH"}
        assert matched <= declared

    print("PASS: DV360 capability is READ_ONLY v4 with writes/OAuth/other DSPs out of scope")
    print("PASS: declared Campaign fields can emit deterministic MATCH")
    print("PASS: declared InsertionOrder fields can emit deterministic MATCH")
    print("PASS: declared LineItem fields can emit deterministic MATCH")
    print("PASS: undeclared Campaign/IO/LineItem fields fail closed as UNSUPPORTED/BLOCKED")
    print("PASS: no undeclared field can emit MATCH")


if __name__ == "__main__":
    main()
