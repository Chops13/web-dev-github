#!/usr/bin/env python3
"""Acceptance test for DV360ExpectedVsActualComparator.

Frozen synthetic DV360 GET-shaped payloads only. No networking, OAuth, credentials,
or writes. Proves exact match, £1 budget drift, wrong parent relationship, and a
deferred-field fail-closed BLOCKED result.
"""
from __future__ import annotations

import copy

from dv360_actual_state_adapter import DV360ActualStateAdapter
from dv360_expected_actual_comparator import DV360ExpectedVsActualComparator


def synthetic_actual() -> dict:
    responses = {
        "campaign": [{
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
        }],
        "insertion_order": [{
            "insertionOrderId": "2001",
            "advertiserId": "9001",
            "campaignId": "1001",
            "displayName": "UK Display Prospecting",
            "insertionOrderType": "RTB",
            "entityStatus": "ENTITY_STATUS_ACTIVE",
            "optimizationObjective": "PERFORMANCE_GOAL_TYPE_CPA",
            "kpi": {"kpiType": "KPI_TYPE_CPA", "kpiAmountMicros": "25000000"},
            "budget": {
                "budgetUnit": "BUDGET_UNIT_CURRENCY",
                "automationType": "INSERTION_ORDER_AUTOMATION_TYPE_NONE",
            },
            "pacing": {"pacingType": "PACING_TYPE_EVEN"},
            "updateTime": "2026-09-07T12:00:01Z",
        }],
        "line_item": [{
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
        }],
    }
    bindings = {
        "CAMPAIGN": {"1001": "CMP-001"},
        "INSERTION_ORDER": {"2001": "IO-001"},
        "LINE_ITEM": {"3001": "ACT-001"},
    }
    return DV360ActualStateAdapter().read_actual(
        account_context_id="9001",
        responses=responses,
        bindings=bindings,
        captured_at="2026-09-07T12:05:00Z",
        pagination_complete={"campaign": True, "insertion_order": True, "line_item": True},
        raw_snapshot_reference="synthetic://dv360/comparator-v1",
    )


def expected_state() -> dict:
    return {
        "schema_version": "nexus-expected-state-v1",
        "expected_state_id": "EXPECTED-DV360-001",
        "graph_revision_id": "REV-001",
        "graph_hash": "GRAPH-HASH-001",
        "platform": "DV360",
        "adapter_version": "dv360-expected-v1",
        "account_context_id": "9001",
        "generated_at": "2026-09-07T12:04:00Z",
        "status": "EXPECTED_READY",
        "objects": [
            {
                "nexus_entity_id": "CMP-001",
                "platform_object_type": "CAMPAIGN",
                "expected_binding_id": "1001",
                "required": True,
                "desired_state": {},
                "managed_fields": [
                    {
                        "canonical_field": "campaign.name",
                        "platform_field": "displayName",
                        "expected": "Q4 Enterprise Growth",
                        "comparison_mode": "EXACT",
                        "origin": "SOURCE",
                    },
                    {
                        "canonical_field": "campaign.budget",
                        "platform_field": "campaignFlight.plannedSpendAmountMicros",
                        "expected": "430000000000",
                        "comparison_mode": "NUMERIC_EXACT",
                        "origin": "DETERMINISTIC",
                    },
                ],
                "relationships": [],
                "unmanaged_fields": [],
            },
            {
                "nexus_entity_id": "IO-001",
                "platform_object_type": "INSERTION_ORDER",
                "expected_binding_id": "2001",
                "required": True,
                "desired_state": {},
                "managed_fields": [
                    {
                        "canonical_field": "insertion_order.name",
                        "platform_field": "displayName",
                        "expected": "UK Display Prospecting",
                        "comparison_mode": "EXACT",
                        "origin": "SOURCE",
                    }
                ],
                "relationships": [
                    {"type": "PARENT_CAMPAIGN", "platform_object_id": "1001"}
                ],
                "unmanaged_fields": [],
            },
            {
                "nexus_entity_id": "ACT-001",
                "platform_object_type": "LINE_ITEM",
                "expected_binding_id": "3001",
                "required": True,
                "desired_state": {},
                "managed_fields": [
                    {
                        "canonical_field": "activation.name",
                        "platform_field": "displayName",
                        "expected": "Enterprise Decision Makers | Display",
                        "comparison_mode": "EXACT",
                        "origin": "SOURCE",
                    },
                    {
                        "canonical_field": "activation.creatives",
                        "platform_field": "creativeIds",
                        "expected": ["5001", "5002"],
                        "comparison_mode": "SET_EXACT",
                        "origin": "MAPPED",
                    },
                ],
                "relationships": [
                    {"type": "PARENT_CAMPAIGN", "platform_object_id": "1001"},
                    {"type": "PARENT_INSERTION_ORDER", "platform_object_id": "2001"},
                ],
                "unmanaged_fields": [],
            },
        ],
    }


def object_by_type(actual: dict, object_type: str) -> dict:
    matches = [obj for obj in actual["objects"] if obj["platform_object_type"] == object_type]
    assert len(matches) == 1
    return matches[0]


def main() -> None:
    comparator = DV360ExpectedVsActualComparator()
    expected = expected_state()
    actual = synthetic_actual()
    expected_before = copy.deepcopy(expected)
    actual_before = copy.deepcopy(actual)

    exact = comparator.compare(expected, actual)
    assert exact["schema_version"] == "nexus-drift-v1"
    assert exact["status"] == "RECONCILED"
    assert exact["expected_state_id"] == expected["expected_state_id"]
    assert exact["actual_state_id"] == actual["actual_state_id"]
    assert exact["records"]
    assert all(record["state"] == "MATCH" for record in exact["records"])

    # One currency unit = 1,000,000 micros in this frozen fixture.
    # £430,000 expected versus £429,999 actual therefore creates exactly £1 drift.
    budget_actual = copy.deepcopy(actual)
    campaign = object_by_type(budget_actual, "CAMPAIGN")
    campaign["values"]["comparable"]["campaignFlight.plannedSpendAmountMicros"] = "429999000000"
    budget_result = comparator.compare(expected, budget_actual)
    budget_drifts = [
        record for record in budget_result["records"]
        if record["platform_field"] == "campaignFlight.plannedSpendAmountMicros"
    ]
    assert budget_result["status"] == "DRIFTED"
    assert len(budget_drifts) == 1
    assert budget_drifts[0]["state"] == "DRIFT"
    assert budget_drifts[0]["expected"] == "430000000000"
    assert budget_drifts[0]["actual"] == "429999000000"
    assert budget_drifts[0]["comparison_rule"] == "NUMERIC_EXACT"

    wrong_parent_actual = copy.deepcopy(actual)
    line_item = object_by_type(wrong_parent_actual, "LINE_ITEM")
    for relationship in line_item["relationships"]:
        if relationship["type"] == "PARENT_INSERTION_ORDER":
            relationship["platform_object_id"] = "2999"
    parent_result = comparator.compare(expected, wrong_parent_actual)
    parent_drifts = [
        record for record in parent_result["records"]
        if record["platform_field"] == "PARENT_INSERTION_ORDER"
    ]
    assert parent_result["status"] == "DRIFTED"
    assert len(parent_drifts) == 1
    assert parent_drifts[0]["state"] == "DRIFT"
    assert parent_drifts[0]["detail"] == "PARENT_RELATIONSHIP_MISMATCH"
    assert parent_drifts[0]["expected"] == "2001"
    assert parent_drifts[0]["actual"] == ["2999"]

    deferred_expected = copy.deepcopy(expected)
    line_expected = next(
        obj for obj in deferred_expected["objects"] if obj["platform_object_type"] == "LINE_ITEM"
    )
    line_expected["managed_fields"].append({
        "canonical_field": "activation.bid",
        "platform_field": "bidStrategy.fixedBid.bidAmountMicros",
        "expected": "9000000",
        "comparison_mode": "NUMERIC_EXACT",
        "origin": "SOURCE",
    })
    deferred_result = comparator.compare(deferred_expected, actual)
    deferred_records = [
        record for record in deferred_result["records"]
        if record["platform_field"] == "bidStrategy.fixedBid.bidAmountMicros"
    ]
    assert deferred_result["status"] == "BLOCKED"
    assert len(deferred_records) == 1
    assert deferred_records[0]["state"] == "UNSUPPORTED"
    assert deferred_records[0]["blocking"] is True
    assert deferred_records[0]["severity"] == "EXECUTION_BLOCKER"
    assert deferred_records[0]["detail"] == "DEFERRED_FIELD_REQUIRED_BY_INTENT"

    assert expected == expected_before
    assert actual == actual_before

    print("PASS: exact Expected vs Actual -> nexus-drift-v1 RECONCILED")
    print("PASS: £1 campaign budget difference -> deterministic DRIFTED")
    print("PASS: wrong line-item parent IO relationship -> deterministic DRIFTED")
    print("PASS: deferred bidStrategy field required by Intent -> UNSUPPORTED/BLOCKED")
    print("PASS: only capability-declared fields can MATCH")
    print("PASS: Expected and Actual inputs remained immutable")


if __name__ == "__main__":
    main()
