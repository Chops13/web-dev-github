#!/usr/bin/env python3
"""Read-only DV360 control-plane slice for Nexus v1.

Composes the already-approved pieces:
Expected State -> DV360ReadTransport -> DV360ActualStateAdapter
-> DV360ExpectedVsActualComparator -> compact operator health summary.

No OAuth, credentials, writes, or reconciliation actions exist here.
Networking remains outside this slice; the current accepted transport is frozen/fake.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

from dv360_actual_state_adapter import DV360ActualStateAdapter
from dv360_expected_actual_comparator import DV360ExpectedVsActualComparator
from dv360_read_transport import DV360ReadTransport


class DV360ReadOnlyControlPlaneSlice:
    """Compose read-only DV360 retrieval, Actual State, drift and operator feedback."""

    slice_version = "dv360-read-only-control-plane-v1"
    platform = "DV360"

    def __init__(self, *, transport: DV360ReadTransport) -> None:
        if not isinstance(transport, DV360ReadTransport):
            raise TypeError("transport must implement DV360ReadTransport")
        self.transport = transport
        self.actual_adapter = DV360ActualStateAdapter()
        self.comparator = DV360ExpectedVsActualComparator()

    @staticmethod
    def _health_summary(
        expected_state: dict[str, Any],
        actual_state: dict[str, Any],
        drift: dict[str, Any],
    ) -> dict[str, Any]:
        records = drift.get("records", [])
        state_counts = Counter(record.get("state") for record in records)
        expected_type_counts = Counter(obj.get("platform_object_type") for obj in expected_state.get("objects", []))
        actual_type_counts = Counter(obj.get("platform_object_type") for obj in actual_state.get("objects", []))

        status = drift["status"]
        health_status = {
            "RECONCILED": "HEALTHY",
            "DRIFTED": "DRIFTED",
            "BLOCKED": "BLOCKED",
            "UNKNOWN": "UNKNOWN",
        }[status]

        issue_records = [record for record in records if record.get("state") != "MATCH"]
        blocking_records = [record for record in issue_records if record.get("blocking") is True]
        critical_records = [
            record for record in issue_records
            if record.get("severity") in {"CRITICAL", "EXECUTION_BLOCKER"}
        ]

        return {
            "schema_version": "nexus-operator-health-summary-v1",
            "platform": "DV360",
            "slice_version": DV360ReadOnlyControlPlaneSlice.slice_version,
            "health_status": health_status,
            "reconciliation_status": status,
            "actual_completeness": actual_state["completeness"],
            "expected_objects": len(expected_state.get("objects", [])),
            "actual_objects": len(actual_state.get("objects", [])),
            "expected_object_counts": dict(sorted(expected_type_counts.items())),
            "actual_object_counts": dict(sorted(actual_type_counts.items())),
            "checks_total": len(records),
            "checks_matched": state_counts.get("MATCH", 0),
            "issues_total": len(issue_records),
            "drift_count": state_counts.get("DRIFT", 0),
            "missing_count": state_counts.get("MISSING", 0),
            "ambiguous_binding_count": state_counts.get("AMBIGUOUS_BINDING", 0),
            "unsupported_count": state_counts.get("UNSUPPORTED", 0),
            "read_error_count": state_counts.get("READ_ERROR", 0),
            "blocking_count": len(blocking_records),
            "critical_count": len(critical_records),
            "issues": [
                {
                    "state": record.get("state"),
                    "nexus_entity_id": record.get("nexus_entity_id"),
                    "platform_object_type": record.get("platform_object_type"),
                    "platform_object_id": record.get("platform_object_id"),
                    "platform_field": record.get("platform_field"),
                    "expected": copy.deepcopy(record.get("expected")),
                    "actual": copy.deepcopy(record.get("actual")),
                    "severity": record.get("severity"),
                    "blocking": record.get("blocking"),
                    "detail": record.get("detail"),
                }
                for record in issue_records
            ],
        }

    def run(self, *, expected_state: dict[str, Any]) -> dict[str, Any]:
        """Run one deterministic read-only control-plane cycle through the transport boundary."""
        expected = copy.deepcopy(expected_state)

        if expected.get("schema_version") != "nexus-expected-state-v1":
            raise ValueError("expected_state must use nexus-expected-state-v1")
        if expected.get("platform") != self.platform:
            raise ValueError("DV360 control-plane slice accepts DV360 Expected State only")

        snapshot = self.transport.read(account_context_id=expected["account_context_id"])
        actual = self.actual_adapter.read_actual(
            account_context_id=expected["account_context_id"],
            responses=copy.deepcopy(snapshot.responses),
            bindings=copy.deepcopy(snapshot.bindings),
            captured_at=snapshot.captured_at,
            pagination_complete=copy.deepcopy(snapshot.pagination_complete),
            raw_snapshot_reference=snapshot.raw_snapshot_reference,
        )
        drift = self.comparator.compare(expected, actual)
        health = self._health_summary(expected, actual, drift)

        return {
            "schema_version": "nexus-dv360-read-only-control-plane-run-v1",
            "platform": self.platform,
            "slice_version": self.slice_version,
            "transport_version": self.transport.transport_version,
            "expected_state_id": expected["expected_state_id"],
            "actual_state": actual,
            "drift": drift,
            "health": health,
        }
