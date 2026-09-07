#!/usr/bin/env python3
"""Acceptance test for the DV360 read-only control-plane slice via transport.

Proves the existing clean/drift outcomes still hold while the slice consumes only
DV360ReadTransport. No networking, OAuth, credentials or writes are introduced.
"""
from __future__ import annotations

import copy
import inspect

from dv360_read_only_control_plane_slice import DV360ReadOnlyControlPlaneSlice
from dv360_read_transport import DV360ReadTransport, FrozenFakeDV360ReadTransport


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
                    {"canonical_field": "campaign.name", "platform_field": "displayName", "expected": "Q4 Enterprise Growth", "comparison_mode": "EXACT", "origin": "SOURCE"},
                    {"canonical_field": "campaign.budget", "platform_field": "campaignFlight.plannedSpendAmountMicros", "expected": "430000000000", "comparison_mode": "NUMERIC_EXACT", "origin": "SOURCE"},
                    {"canonical_field": "campaign.flight.start", "platform_field": "campaignFlight.plannedDates.startDate", "expected": {"year": 2026, "month": 10, "day": 1}, "comparison_mode": "EXACT", "origin": "SOURCE"},
                    {"canonical_field": "campaign.flight.end", "platform_field": "campaignFlight.plannedDates.endDate", "expected": {"year": 2026, "month": 12, "day": 31}, "comparison_mode": "EXACT", "origin": "SOURCE"},
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
                    {"canonical_field": "insertion_order.name", "platform_field": "displayName", "expected": "UK Display Prospecting", "comparison_mode": "EXACT", "origin": "DETERMINISTIC"},
                    {"canonical_field": "insertion_order.status", "platform_field": "entityStatus", "expected": "ENTITY_STATUS_ACTIVE", "comparison_mode": "EXACT", "origin": "SOURCE"},
                ],
                "relationships": [{"type": "PARENT_CAMPAIGN", "platform_object_id": "1001"}],
                "unmanaged_fields": [],
            },
            {
                "nexus_entity_id": "ACT-Q4-001",
                "platform_object_type": "LINE_ITEM",
                "expected_binding_id": "3001",
                "required": True,
                "desired_state": {},
                "managed_fields": [
                    {"canonical_field": "activation.name", "platform_field": "displayName", "expected": "Enterprise Decision Makers | Display", "comparison_mode": "EXACT", "origin": "DETERMINISTIC"},
                    {"canonical_field": "activation.creatives", "platform_field": "creativeIds", "expected": ["5001", "5002"], "comparison_mode": "SET_EXACT", "origin": "SOURCE"},
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
        "campaign": [{
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
        }],
        "insertion_order": [{
            "insertionOrderId": "2001",
            "advertiserId": "9001",
            "campaignId": "1001",
            "displayName": "UK Display Prospecting",
            "entityStatus": "ENTITY_STATUS_ACTIVE",
            "insertionOrderType": "RTB",
        }],
        "line_item": [{
            "lineItemId": "3001",
            "advertiserId": "9001",
            "campaignId": "1001",
            "insertionOrderId": "2001",
            "displayName": "Enterprise Decision Makers | Display",
            "lineItemType": "LINE_ITEM_TYPE_DISPLAY_DEFAULT",
            "entityStatus": "ENTITY_STATUS_ACTIVE",
            "creativeIds": ["5002", "5001"],
            "warningMessages": [],
        }],
    }


def bindings() -> dict:
    return {
        "CAMPAIGN": {"1001": "CMP-Q4-001"},
        "INSERTION_ORDER": {"2001": "IO-Q4-001"},
        "LINE_ITEM": {"3001": "ACT-Q4-001"},
    }


def fake_transport(payloads: dict, *, captured_at: str, reference: str) -> FrozenFakeDV360ReadTransport:
    return FrozenFakeDV360ReadTransport(
        account_context_id="9001",
        responses=payloads,
        bindings=bindings(),
        captured_at=captured_at,
        pagination_complete={"campaign": True, "insertion_order": True, "line_item": True},
        raw_snapshot_reference=reference,
    )


def main() -> None:
    expected = expected_state()
    clean_payloads = responses()
    stable_expected = copy.deepcopy(expected)
    stable_clean_payloads = copy.deepcopy(clean_payloads)

    clean_transport = fake_transport(
        clean_payloads,
        captured_at="2026-09-07T13:06:00Z",
        reference="synthetic://dv360/clean",
    )
    assert isinstance(clean_transport, DV360ReadTransport)
    assert clean_transport.transport_version == "dv360-frozen-fake-read-v1"

    # The control-plane slice no longer accepts raw responses/bindings directly.
    run_parameters = inspect.signature(DV360ReadOnlyControlPlaneSlice.run).parameters
    assert "responses" not in run_parameters
    assert "bindings" not in run_parameters
    assert set(run_parameters) == {"self", "expected_state"}

    clean = DV360ReadOnlyControlPlaneSlice(transport=clean_transport).run(expected_state=expected)
    assert clean["schema_version"] == "nexus-dv360-read-only-control-plane-run-v1"
    assert clean["transport_version"] == "dv360-frozen-fake-read-v1"
    assert clean["actual_state"]["schema_version"] == "nexus-actual-state-v1"
    assert clean["actual_state"]["completeness"] == "COMPLETE"
    assert clean["drift"]["schema_version"] == "nexus-drift-v1"
    assert clean["drift"]["status"] == "RECONCILED"
    assert clean["health"]["health_status"] == "HEALTHY"
    assert clean["health"]["issues_total"] == 0
    assert clean["health"]["blocking_count"] == 0
    assert clean["health"]["checks_total"] == clean["health"]["checks_matched"]

    drift_payloads = responses()
    drift_payloads["campaign"][0]["campaignFlight"]["plannedSpendAmountMicros"] = "430001000000"
    drift = DV360ReadOnlyControlPlaneSlice(
        transport=fake_transport(
            drift_payloads,
            captured_at="2026-09-07T13:07:00Z",
            reference="synthetic://dv360/drift-1-gbp",
        )
    ).run(expected_state=expected)

    assert drift["drift"]["status"] == "DRIFTED"
    assert drift["health"]["health_status"] == "DRIFTED"
    assert drift["health"]["issues_total"] == 1
    issue = drift["health"]["issues"][0]
    assert issue["nexus_entity_id"] == "CMP-Q4-001"
    assert issue["platform_object_id"] == "1001"
    assert issue["platform_field"] == "campaignFlight.plannedSpendAmountMicros"
    assert issue["expected"] == "430000000000"
    assert issue["actual"] == "430001000000"
    assert issue["blocking"] is True

    # Frozen fake transport returns deep-copied snapshots, so callers cannot mutate its source fixture.
    snap_one = clean_transport.read(account_context_id="9001")
    snap_one.responses["campaign"][0]["displayName"] = "MUTATED BY CALLER"
    snap_two = clean_transport.read(account_context_id="9001")
    assert snap_two.responses["campaign"][0]["displayName"] == "Q4 Enterprise Growth"

    try:
        clean_transport.read(account_context_id="wrong-account")
        raise AssertionError("transport must reject account-context mismatch")
    except ValueError as exc:
        assert str(exc) == "Transport account context mismatch"

    assert expected == stable_expected
    assert clean_payloads == stable_clean_payloads

    transport_source = inspect.getsource(FrozenFakeDV360ReadTransport)
    forbidden = ("requests.", "urllib", "httpx", "googleapiclient", "oauth", "patch(", "post(", "delete(")
    assert not any(token in transport_source.lower() for token in forbidden)

    print("PASS: control-plane slice consumes DV360ReadTransport, not raw synthetic responses")
    print("PASS: frozen fake transport -> Actual State -> comparator -> operator health summary")
    print("PASS: clean fixture remains HEALTHY / RECONCILED")
    print("PASS: £1 budget fixture remains DRIFTED with exact issue evidence")
    print("PASS: fake transport snapshots are isolated and account-scoped")
    print("PASS: no networking, OAuth or write surface introduced")


if __name__ == "__main__":
    main()
