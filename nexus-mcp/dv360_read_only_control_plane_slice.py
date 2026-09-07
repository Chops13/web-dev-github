#!/usr/bin/env python3
"""Synthetic/read-only DV360 control-plane slice for Nexus v1.

Composes the already-approved pieces:
Expected State -> DV360ActualStateAdapter -> DV360ExpectedVsActualComparator
-> compact operator health summary.

No networking, OAuth, credentials, writes, or reconciliation actions exist here.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

from dv360_actual_state_adapter import DV360ActualStateAdapter
from dv360_expected_actual_comparator import DV360ExpectedVsActualComparator


class DV360ReadOnlyControlPlaneSlice:
    """Compose read-only DV360 Actual State and deterministic drift into operator feedback."""

    slice_version = "dv360-read-only-control-plane-v1"
    platform = "DV360"

    def __init__(self) -> None:
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

    def run(
        self,
        *,
        expected_state: dict[str, Any],
        responses: dict[str, list[dict[str, Any]]],
        bindings: dict[str, dict[str, str]],
        captured_at: str,
        pagination_complete: dict[str, bool] | None = None,
        raw_snapshot_reference: str | None = None,
    ) -> dict[str, Any]:
        """Run one deterministic read-only control-plane cycle from supplied DV360-shaped responses."""
        expected = copy.deepcopy(expected_state)
        supplied_responses = copy.deepcopy(responses)
        supplied_bindings = copy.deepcopy(bindings)

        if expected.get("schema_version") != "nexus-expected-state-v1":
            raise ValueError("expected_state must use nexus-expected-state-v1")
        if expected.get("platform") != self.platform:
            raise ValueError("DV360 control-plane slice accepts DV360 Expected State only")

        actual = self.actual_adapter.read_actual(
            account_context_id=expected["account_context_id"],
            responses=supplied_responses,
            bindings=supplied_bindings,
            captured_at=captured_at,
            pagination_complete=copy.deepcopy(pagination_complete),
            raw_snapshot_reference=raw_snapshot_reference,
        )
        drift = self.comparator.compare(expected, actual)
        health = self._health_summary(expected, actual, drift)

        return {
            "schema_version": "nexus-dv360-read-only-control-plane-run-v1",
            "platform": self.platform,
            "slice_version": self.slice_version,
            "expected_state_id": expected["expected_state_id"],
            "actual_state": actual,
            "drift": drift,
            "health": health,
        }
