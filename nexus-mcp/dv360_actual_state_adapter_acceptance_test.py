#!/usr/bin/env python3
"""Acceptance test for DV360ActualStateAdapter using frozen synthetic GET payloads only."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from dv360_actual_state_adapter import DV360ActualStateAdapter

ROOT = Path(__file__).resolve().parent


def main() -> None:
    schema = json.loads((ROOT / "schemas" / "actual-state-v1.json").read_text(encoding="utf-8"))
    adapter = DV360ActualStateAdapter()

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
        "campaignBudgets": [
            {
                "budgetId": "1101",
                "displayName": "Q4 Main Budget",
                "budgetUnit": "BUDGET_UNIT_CURRENCY",
                "budgetAmountMicros": "430000000000",
                "dateRange": {
                    "startDate": {"year": 2026, "month": 10, "day": 1},
                    "endDate": {"year": 2026, "month": 12, "day": 31},
                },
                "externalBudgetSource": "EXTERNAL_BUDGET_SOURCE_NONE",
            }
        ],
        "frequencyCap": {"unlimited": False},
        "updateTime": "2026-09-07T12:00:00Z",
        "name": "advertisers/9001/campaigns/1001",
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
        "budget": {
            "budgetUnit": "BUDGET_UNIT_CURRENCY",
            "automationType": "INSERTION_ORDER_AUTOMATION_TYPE_NONE",
            "budgetSegments": [
                {
                    "campaignBudgetId": "1101",
                    "dateRange": {
                        "startDate": {"year": 2026, "month": 10, "day": 1},
                        "endDate": {"year": 2026, "month": 12, "day": 31},
                    },
                    "budgetAmountMicros": "180000000000",
                }
            ],
        },
        "pacing": {"pacingType": "PACING_TYPE_EVEN"},
        "updateTime": "2026-09-07T12:00:01Z",
        "name": "advertisers/9001/insertionOrders/2001",
        "reservationType": "RESERVATION_TYPE_NOT_GUARANTEED",
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
        "warningMessages": ["SYNTHETIC_WARNING"],
        "name": "advertisers/9001/lineItems/3001",
        "reservationType": "RESERVATION_TYPE_NOT_GUARANTEED",
    }

    responses = {
        "campaign": [campaign],
        "insertion_order": [insertion_order],
        "line_item": [line_item],
    }
    frozen_responses = copy.deepcopy(responses)

    actual = adapter.read_actual(
        account_context_id="9001",
        responses=responses,
        bindings={
            "CAMPAIGN": {"1001": "CMP-001"},
            "INSERTION_ORDER": {"2001": "IO-001"},
            "LINE_ITEM": {"3001": "ACT-001"},
        },
        captured_at="2026-09-07T13:00:00Z",
        pagination_complete={"campaign": True, "insertion_order": True, "line_item": True},
        raw_snapshot_reference="synthetic://dv360-read-v1/fixture-001",
    )

    assert schema["$id"] == "nexus-actual-state-v1"
    assert actual["schema_version"] == "nexus-actual-state-v1"
    assert actual["platform"] == "DV360"
    assert actual["adapter_version"] == "dv360-actual-state-v1"
    assert actual["account_context_id"] == "9001"
    assert actual["completeness"] == "COMPLETE"
    assert actual["read_failures"] == []
    assert len(actual["objects"]) == 3

    by_type = {obj["platform_object_type"]: obj for obj in actual["objects"]}
    assert by_type["CAMPAIGN"]["platform_object_id"] == "1001"
    assert by_type["CAMPAIGN"]["nexus_binding"] == "CMP-001"
    assert by_type["INSERTION_ORDER"]["nexus_binding"] == "IO-001"
    assert by_type["LINE_ITEM"]["nexus_binding"] == "ACT-001"

    campaign_values = by_type["CAMPAIGN"]["values"]
    assert campaign_values["comparable"]["displayName"] == "Q4 Enterprise Growth"
    assert campaign_values["comparable"]["campaignFlight.plannedSpendAmountMicros"] == "430000000000"
    assert campaign_values["observe_only"]["updateTime"] == "2026-09-07T12:00:00Z"
    assert campaign_values["deferred"]["frequencyCap"] == {"unlimited": False}
    assert campaign_values["nested_collections"]["campaignBudgets"][0]["platform_object_id"] == "1101"
    assert campaign_values["nested_collections"]["campaignBudgets"][0]["comparable"]["budgetAmountMicros"] == "430000000000"

    io_values = by_type["INSERTION_ORDER"]["values"]
    assert io_values["comparable"]["campaignId"] == "1001"
    assert io_values["deferred"]["pacing"] == {"pacingType": "PACING_TYPE_EVEN"}
    assert io_values["nested_collections"]["budget.budgetSegments"][0]["comparable"]["campaignBudgetId"] == "1101"

    li_values = by_type["LINE_ITEM"]["values"]
    assert li_values["comparable"]["creativeIds"] == ["5002", "5001"]
    assert li_values["deferred"]["bidStrategy"] == {"fixedBid": {"bidAmountMicros": "9000000"}}
    assert li_values["observe_only"]["warningMessages"] == ["SYNTHETIC_WARNING"]

    io_relationships = by_type["INSERTION_ORDER"]["relationships"]
    li_relationships = by_type["LINE_ITEM"]["relationships"]
    assert io_relationships == [{"type": "PARENT_CAMPAIGN", "platform_object_id": "1001"}]
    assert li_relationships == [
        {"type": "PARENT_CAMPAIGN", "platform_object_id": "1001"},
        {"type": "PARENT_INSERTION_ORDER", "platform_object_id": "2001"},
    ]

    # Strong boundary: caller payloads are never mutated.
    assert responses == frozen_responses

    # Incomplete pagination must not claim a complete Actual State.
    partial = adapter.read_actual(
        account_context_id="9001",
        responses=responses,
        bindings={},
        captured_at="2026-09-07T13:01:00Z",
        pagination_complete={"campaign": True, "insertion_order": True, "line_item": False},
    )
    assert partial["completeness"] == "PARTIAL"
    assert {failure["reason"] for failure in partial["read_failures"]} == {"INCOMPLETE_PAGINATION"}

    print("PASS: synthetic DV360 Campaign/IO/LineItem GET payloads -> nexus-actual-state-v1")
    print("PASS: capability-declared comparable fields projected without source mutation")
    print("PASS: observe-only and deferred fields remain explicitly segregated from comparable truth")
    print("PASS: campaign/IO/line-item platform IDs bind to stable Nexus identities")
    print("PASS: parent campaign/IO relationships preserved deterministically")
    print("PASS: incomplete pagination -> PARTIAL, never COMPLETE")


if __name__ == "__main__":
    main()
