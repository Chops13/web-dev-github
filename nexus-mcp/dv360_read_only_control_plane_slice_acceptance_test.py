#!/usr/bin/env python3
"""Acceptance test for the synthetic DV360 read-only control-plane slice.

Proves two operator-facing states without networking or writes:
1) exact Expected vs Actual -> HEALTHY / RECONCILED;
2) one £1 campaign budget mismatch -> DRIFTED with exact issue evidence.
"""
from __future__ import annotations

import copy

from dv360_read_only_control_plane_slice import DV360ReadOnlyControlPlaneSlice


def expected_state() -> dict:
    return {
        "schema_version": "nexus-expected-state-v1",
        "expected_state_id": "EXP-DV360-Q4-001",
        "graph_revision_id": "REV-Q4-001",
        "graph_hash": "GRAPH-HASH-Q4-001",
        "platform": "DV360",
        "adapter_version": "dv360-actual-state-v1",
        "account_context_id": "9001",
        "generated_at": "2026-09-07T13:00:00Z",
        "status": "EXPECTED_READY",
        "objects": [
            {
                "nexus_entity_id": "CMP-Q4-001",
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
                        "origin": "SOURCE",
                    },
                    {
                        "canonical_field": "campaign.flight.start",
                        "platform_field": "campaignFlight.plannedDates.startDate",
                        "expected": {"year": 2026, "month": 10, "day": 1},
                        "comparison_mode": "EXACT",
                        "origin": "SOURCE",
                    },
                    {
                        "canonical_field": "campaign.flight.end",
                        "platform_field": "campaignFlight.plannedDates.endDate",
                        "expected": {"year": 2026, "month": 12, "day": 31},
                        "comparison_mode": "EXACT",
                        "origin": "SOURCE",
                    },
                ],
                "relationships": [],
                "unmanaged_fields": [],
            },
            {
                "nexus_entity_id": "IO-Q4-001",
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
                        "origin": "DETERMINISTIC",
                    },
                    {
                        "canonical_field": "insertion_order.status",
                        "platform_field": "entityStatus",
                        "expected": "ENTITY_STATUS_ACTIVE",
                        "comparison_mode": "EXACT",
                        "origin": "SOURCE",
                    },
                ],
                "relationships": [
                    {"type": "PARENT_CAMPAIGN", "platform_object_id": "1001"}
                ],
                "unmanaged_fields": [],
            },
            {
                "nexus_entity_id": "ACT-Q4-001",
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
                        "origin": "DETERMINISTIC",
                    },
                    {
                        "canonical_field": "activation.creatives",
                        "platform_field": "creativeIds",
                        "expected": ["5001", "5002"],
                        "comparison_mode": "SET_EXACT",
                        "origin": "SOURCE",
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


def responses() -> dict:
    return {
        "campaign": [
            {
                "campaignId": "1001",
                "advertiserId": "9001",
                "displayName": "Q4 Enterprise Growth",
                "entityStatus": "ENTITY_STATUS_ACTIVE",
                "campaignFlight": {
                    "plannedSpendAmountMicros": "430000000000",
                    "plannedDates": {
                        "startDate": {"year": 2026, "month": 10, "day": 1},
                        "endDate": {"year": 2026, "month": 12, "day": 31},
                    },
                },
                "updateTime": "2026-09-07T13:05:00Z",
            }
        ],
        "insertion_order": [
            {
                "insertionOrderId": "2001",
                "advertiserId": "9001",
                "campaignId": "1001",
                "displayName": "UK Display Prospecting",
                "entityStatus": "ENTITY_STATUS_ACTIVE",
                "insertionOrderType": "RTB",
            }
        ],
        "line_item": [
            {
                "lineItemId": "3001",
                "advertiserId": "9001",
                "campaignId": "1001",
                "insertionOrderId": "2001",
                "displayName": "Enterprise Decision Makers | Display",
                "lineItemType": "LINE_ITEM_TYPE_DISPLAY_DEFAULT",
                "entityStatus": "ENTITY_STATUS_ACTIVE",
                "creativeIds": ["5002", "5001"],
                "warningMessages": [],
            }
        ],
    }


def bindings() -> dict:
    return {
        "CAMPAIGN": {"1001": "CMP-Q4-001"},
        "INSERTION_ORDER": {"2001": "IO-Q4-001"},
        "LINE_ITEM": {"3001": "ACT-Q4-001"},
    }


def main() -> None:
    slice_ = DV360ReadOnlyControlPlaneSlice()
    expected = expected_state()
    actual_payloads = responses()
    stable_expected = copy.deepcopy(expected)
    stable_payloads = copy.deepcopy(actual_payloads)

    clean = slice_.run(
        expected_state=expected,
        responses=actual_payloads,
        bindings=bindings(),
        captured_at="2026-09-07T13:06:00Z",
        pagination_complete={"campaign": True, "insertion_order": True, "line_item": True},
        raw_snapshot_reference="synthetic://dv360/clean",
    )

    assert clean["schema_version"] == "nexus-dv360-read-only-control-plane-run-v1"
    assert clean["actual_state"]["schema_version"] == "nexus-actual-state-v1"
    assert clean["actual_state"]["completeness"] == "COMPLETE"
    assert clean["drift"]["schema_version"] == "nexus-drift-v1"
    assert clean["drift"]["status"] == "RECONCILED"
    assert clean["health"]["health_status"] == "HEALTHY"
    assert clean["health"]["reconciliation_status"] == "RECONCILED"
    assert clean["health"]["expected_objects"] == 3
    assert clean["health"]["actual_objects"] == 3
    assert clean["health"]["issues_total"] == 0
    assert clean["health"]["blocking_count"] == 0
    assert clean["health"]["checks_total"] == clean["health"]["checks_matched"]

    drift_payloads = responses()
    drift_payloads["campaign"][0]["campaignFlight"]["plannedSpendAmountMicros"] = "430001000000"
    drifted = slice_.run(
        expected_state=expected,
        responses=drift_payloads,
        bindings=bindings(),
        captured_at="2026-09-07T13:07:00Z",
        pagination_complete={"campaign": True, "insertion_order": True, "line_item": True},
        raw_snapshot_reference="synthetic://dv360/drift-1-gbp",
    )

    assert drifted["drift"]["status"] == "DRIFTED"
    assert drifted["health"]["health_status"] == "DRIFTED"
    assert drifted["health"]["issues_total"] == 1
    assert drifted["health"]["drift_count"] == 1
    assert drifted["health"]["blocking_count"] == 1
    assert drifted["health"]["critical_count"] == 1

    issue = drifted["health"]["issues"][0]
    assert issue["state"] == "DRIFT"
    assert issue["nexus_entity_id"] == "CMP-Q4-001"
    assert issue["platform_object_type"] == "CAMPAIGN"
    assert issue["platform_object_id"] == "1001"
    assert issue["platform_field"] == "campaignFlight.plannedSpendAmountMicros"
    assert issue["expected"] == "430000000000"
    assert issue["actual"] == "430001000000"
    assert issue["severity"] == "CRITICAL"
    assert issue["blocking"] is True
    assert issue["detail"] == "MANAGED_FIELD_MISMATCH"

    assert expected == stable_expected
    assert actual_payloads == stable_payloads

    print("PASS: Expected -> DV360ActualStateAdapter -> comparator -> operator health summary")
    print("PASS: exact synthetic DV360 state -> HEALTHY / RECONCILED with zero issues")
    print("PASS: £1 campaign budget mismatch -> DRIFTED with one exact critical issue")
    print("PASS: operator summary exposes object counts, check counts and blocking counts")
    print("PASS: drift issue preserves Nexus identity, DV360 object ID, field, expected and actual")
    print("PASS: no networking, OAuth, writes or source mutation introduced")


if __name__ == "__main__":
    main()
