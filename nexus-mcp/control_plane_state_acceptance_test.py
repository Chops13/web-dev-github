#!/usr/bin/env python3
"""Acceptance proof for Nexus Expected/Actual/Drift v1 using fake read-only adapter."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from fake_control_plane_adapter import FakeControlPlaneAdapter

ROOT = Path(__file__).resolve().parent


def graph_fixture() -> dict:
    return {
        "schema_version": "nexus-campaign-graph-v1",
        "revision_id": "REV-001",
        "graph_hash": "graph-hash-001",
        "platform": "FAKE_DSP",
        "account_context_id": "ACCOUNT-001",
        "execution_objects": [
            {
                "nexus_entity_id": "ACT-001",
                "platform_object_type": "LINE_ITEM",
                "required": True,
                "managed_fields": [
                    {
                        "canonical_field": "activation.budget_minor",
                        "platform_field": "budget_minor",
                        "expected": 100000,
                        "comparison_mode": "NUMERIC_EXACT",
                        "origin": "SOURCE",
                    },
                    {
                        "canonical_field": "activation.flight_start",
                        "platform_field": "flight_start",
                        "expected": "2026-10-01",
                        "comparison_mode": "EXACT",
                        "origin": "SOURCE",
                    },
                ],
                "relationships": [],
                "unmanaged_fields": ["platform_created_at"],
            }
        ],
    }


def actual_object(object_id: str, *, budget_minor: int = 100000) -> dict:
    return {
        "platform_object_id": object_id,
        "platform_object_type": "LINE_ITEM",
        "nexus_binding": "ACT-001",
        "values": {
            "budget_minor": budget_minor,
            "flight_start": "2026-10-01",
            "platform_created_at": "ignored",
        },
        "relationships": [],
        "status": "ACTIVE",
    }


def assert_schemas() -> None:
    expected = json.loads((ROOT / "schemas" / "expected-state-v1.json").read_text())
    actual = json.loads((ROOT / "schemas" / "actual-state-v1.json").read_text())
    drift = json.loads((ROOT / "schemas" / "drift-v1.json").read_text())
    assert expected["$id"] == "nexus-expected-state-v1"
    assert actual["$id"] == "nexus-actual-state-v1"
    assert drift["$id"] == "nexus-drift-v1"


def main() -> None:
    assert_schemas()
    adapter = FakeControlPlaneAdapter("FAKE_DSP")
    graph = graph_fixture()
    frozen_graph = copy.deepcopy(graph)
    expected = adapter.build_expected(graph)

    # Expected-state generation must not mutate approved intent.
    assert graph == frozen_graph
    assert expected["schema_version"] == "nexus-expected-state-v1"
    assert expected["graph_hash"] == frozen_graph["graph_hash"]

    # 1. Exact match => RECONCILED.
    actual_match = adapter.read_actual("ACCOUNT-001", [actual_object("DSP-100")])
    match = adapter.compare(expected, actual_match)
    assert match["status"] == "RECONCILED"
    assert {r["state"] for r in match["records"]} == {"MATCH"}

    # 2. £1 drift in minor units => deterministic DRIFT, never rounded away.
    actual_budget_drift = adapter.read_actual("ACCOUNT-001", [actual_object("DSP-100", budget_minor=99900)])
    budget_drift = adapter.compare(expected, actual_budget_drift)
    assert budget_drift["status"] == "DRIFTED"
    budget_records = [r for r in budget_drift["records"] if r["state"] == "DRIFT"]
    assert len(budget_records) == 1
    assert budget_records[0]["canonical_field"] == "activation.budget_minor"
    assert budget_records[0]["expected"] == 100000
    assert budget_records[0]["actual"] == 99900

    # 3. Required object absent => deterministic MISSING drift.
    actual_missing = adapter.read_actual("ACCOUNT-001", [])
    missing = adapter.compare(expected, actual_missing)
    assert missing["status"] == "DRIFTED"
    assert [r["state"] for r in missing["records"]] == ["MISSING"]
    proposals = adapter.propose_reconciliation(missing)
    assert proposals[0]["action"] == "CREATE"
    assert proposals[0]["requires_human_approval"] is True

    # 4. Two actual objects claim one Nexus identity => fail closed.
    actual_ambiguous = adapter.read_actual(
        "ACCOUNT-001",
        [actual_object("DSP-100"), actual_object("DSP-101")],
    )
    ambiguous = adapter.compare(expected, actual_ambiguous)
    assert ambiguous["status"] == "BLOCKED"
    assert "AMBIGUOUS_BINDING" in {r["state"] for r in ambiguous["records"]}

    # Comparisons must also leave the approved graph untouched.
    assert graph == frozen_graph

    print("PASS: schemas load")
    print("PASS: exact match -> RECONCILED")
    print("PASS: £1 budget drift -> DRIFTED")
    print("PASS: missing object -> DRIFTED + CREATE proposal")
    print("PASS: ambiguous binding -> BLOCKED")
    print("PASS: Campaign Graph intent remained immutable")


if __name__ == "__main__":
    main()
