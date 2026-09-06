#!/usr/bin/env python3
"""Deterministic fake adapter for Nexus Expected/Actual/Drift v1.

This is a read-only control-plane proof. It does not call any DSP, write files,
publish campaigns, or mutate Campaign Graph intent. Unsupported comparisons fail closed.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from typing import Any

EXPECTED_SCHEMA = "nexus-expected-state-v1"
ACTUAL_SCHEMA = "nexus-actual-state-v1"
DRIFT_SCHEMA = "nexus-drift-v1"
GRAPH_SCHEMA = "nexus-campaign-graph-v1"


def _stable_id(prefix: str, value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:12].upper()}"


def _record(
    *,
    state: str,
    nexus_entity_id: str | None,
    platform_object_type: str,
    platform_object_id: str | None = None,
    canonical_field: str | None = None,
    platform_field: str | None = None,
    expected: Any = None,
    actual: Any = None,
    comparison_rule: str | None = None,
    severity: str = "INFO",
    blocking: bool = False,
    detail: str | None = None,
) -> dict[str, Any]:
    identity = {
        "state": state,
        "nexus_entity_id": nexus_entity_id,
        "platform_object_id": platform_object_id,
        "platform_object_type": platform_object_type,
        "canonical_field": canonical_field,
        "platform_field": platform_field,
        "expected": expected,
        "actual": actual,
        "comparison_rule": comparison_rule,
    }
    return {
        "drift_id": _stable_id("DRIFT", identity),
        **identity,
        "severity": severity,
        "blocking": blocking,
        "detail": detail,
    }


class FakeControlPlaneAdapter:
    """Small deterministic adapter proving the v1 reconciliation contract."""

    adapter_version = "fake-control-plane-v1"

    def __init__(self, platform: str = "FAKE_DSP") -> None:
        self.platform = platform

    def build_expected(self, graph: dict[str, Any]) -> dict[str, Any]:
        source = copy.deepcopy(graph)
        if source.get("schema_version") != GRAPH_SCHEMA:
            raise ValueError("Unsupported campaign graph schema")
        if source.get("platform") != self.platform:
            raise ValueError("Campaign graph platform does not match adapter")
        required = ("revision_id", "graph_hash", "account_context_id", "execution_objects")
        missing = [key for key in required if not source.get(key)]
        if missing:
            raise ValueError(f"Campaign graph missing required fields: {', '.join(missing)}")

        objects = []
        seen = set()
        for obj in source["execution_objects"]:
            entity_id = obj.get("nexus_entity_id")
            object_type = obj.get("platform_object_type")
            fields = copy.deepcopy(obj.get("managed_fields", []))
            if not entity_id or not object_type:
                raise ValueError("Execution object missing identity/type")
            if entity_id in seen:
                raise ValueError(f"Duplicate Nexus entity identity: {entity_id}")
            seen.add(entity_id)
            for field in fields:
                if field.get("comparison_mode") not in {"EXACT", "NUMERIC_EXACT"}:
                    # The expected state may preserve it, but compare() will fail closed.
                    pass
            objects.append({
                "nexus_entity_id": entity_id,
                "platform_object_type": object_type,
                "expected_binding_id": obj.get("expected_binding_id"),
                "required": bool(obj.get("required", True)),
                "desired_state": copy.deepcopy(obj.get("desired_state", {})),
                "managed_fields": fields,
                "relationships": copy.deepcopy(obj.get("relationships", [])),
                "unmanaged_fields": copy.deepcopy(obj.get("unmanaged_fields", [])),
            })

        identity = {
            "revision": source["revision_id"],
            "graph_hash": source["graph_hash"],
            "platform": self.platform,
            "account": source["account_context_id"],
            "objects": objects,
        }
        return {
            "schema_version": EXPECTED_SCHEMA,
            "expected_state_id": _stable_id("EXPECTED", identity),
            "graph_revision_id": source["revision_id"],
            "graph_hash": source["graph_hash"],
            "platform": self.platform,
            "adapter_version": self.adapter_version,
            "account_context_id": source["account_context_id"],
            "generated_at": None,
            "status": "EXPECTED_READY",
            "objects": objects,
        }

    def read_actual(
        self,
        account_context_id: str,
        objects: list[dict[str, Any]],
        *,
        captured_at: str = "2026-09-06T00:00:00Z",
        completeness: str = "COMPLETE",
    ) -> dict[str, Any]:
        snapshot_objects = copy.deepcopy(objects)
        identity = {
            "platform": self.platform,
            "account": account_context_id,
            "captured_at": captured_at,
            "objects": snapshot_objects,
        }
        return {
            "schema_version": ACTUAL_SCHEMA,
            "actual_state_id": _stable_id("ACTUAL", identity),
            "platform": self.platform,
            "adapter_version": self.adapter_version,
            "account_context_id": account_context_id,
            "captured_at": captured_at,
            "completeness": completeness,
            "objects": snapshot_objects,
            "read_failures": [],
            "raw_snapshot_reference": None,
        }

    def compare(self, expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
        exp = copy.deepcopy(expected)
        act = copy.deepcopy(actual)
        if exp.get("schema_version") != EXPECTED_SCHEMA:
            raise ValueError("Unsupported expected-state schema")
        if act.get("schema_version") != ACTUAL_SCHEMA:
            raise ValueError("Unsupported actual-state schema")
        if exp.get("platform") != act.get("platform") or exp.get("account_context_id") != act.get("account_context_id"):
            raise ValueError("Expected and actual state contexts do not match")

        records: list[dict[str, Any]] = []
        if act.get("completeness") != "COMPLETE":
            records.append(_record(
                state="READ_ERROR",
                nexus_entity_id=None,
                platform_object_type="SNAPSHOT",
                severity="EXECUTION_BLOCKER",
                blocking=True,
                detail="Actual platform state is not a complete readable snapshot.",
            ))

        by_binding: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for obj in act.get("objects", []):
            binding = obj.get("nexus_binding")
            if binding:
                by_binding[binding].append(obj)

        expected_ids = {obj["nexus_entity_id"] for obj in exp.get("objects", [])}
        for obj in exp.get("objects", []):
            entity_id = obj["nexus_entity_id"]
            object_type = obj["platform_object_type"]
            matches = by_binding.get(entity_id, [])
            if len(matches) > 1:
                records.append(_record(
                    state="AMBIGUOUS_BINDING",
                    nexus_entity_id=entity_id,
                    platform_object_type=object_type,
                    severity="EXECUTION_BLOCKER",
                    blocking=True,
                    detail=f"{len(matches)} actual objects claim the same Nexus identity.",
                ))
                continue
            if not matches:
                if obj.get("required", True):
                    records.append(_record(
                        state="MISSING",
                        nexus_entity_id=entity_id,
                        platform_object_type=object_type,
                        severity="CRITICAL",
                        blocking=True,
                        detail="Required expected object is missing from actual platform state.",
                    ))
                continue

            actual_obj = matches[0]
            values = actual_obj.get("values", {})
            for field in obj.get("managed_fields", []):
                canonical_field = field["canonical_field"]
                platform_field = field["platform_field"]
                expected_value = field.get("expected")
                actual_value = values.get(platform_field)
                mode = field["comparison_mode"]
                if mode not in {"EXACT", "NUMERIC_EXACT"}:
                    records.append(_record(
                        state="UNSUPPORTED",
                        nexus_entity_id=entity_id,
                        platform_object_id=actual_obj.get("platform_object_id"),
                        platform_object_type=object_type,
                        canonical_field=canonical_field,
                        platform_field=platform_field,
                        expected=expected_value,
                        actual=actual_value,
                        comparison_rule=mode,
                        severity="EXECUTION_BLOCKER",
                        blocking=True,
                        detail="Fake adapter does not implement this comparison mode.",
                    ))
                    continue
                matches_value = expected_value == actual_value
                records.append(_record(
                    state="MATCH" if matches_value else "DRIFT",
                    nexus_entity_id=entity_id,
                    platform_object_id=actual_obj.get("platform_object_id"),
                    platform_object_type=object_type,
                    canonical_field=canonical_field,
                    platform_field=platform_field,
                    expected=expected_value,
                    actual=actual_value,
                    comparison_rule=mode,
                    severity="INFO" if matches_value else "CRITICAL",
                    blocking=not matches_value,
                    detail=None if matches_value else "Actual managed value differs from approved expected state.",
                ))

        for obj in act.get("objects", []):
            binding = obj.get("nexus_binding")
            if binding is None or binding not in expected_ids:
                records.append(_record(
                    state="UNEXPECTED",
                    nexus_entity_id=binding,
                    platform_object_id=obj.get("platform_object_id"),
                    platform_object_type=obj.get("platform_object_type", "UNKNOWN"),
                    severity="WARNING",
                    blocking=False,
                    detail="Actual platform object is not owned by this expected state.",
                ))

        unsafe = {"AMBIGUOUS_BINDING", "READ_ERROR", "UNSUPPORTED", "UNKNOWN"}
        known_drift = {"DRIFT", "MISSING", "UNEXPECTED"}
        states = {r["state"] for r in records}
        if states & unsafe:
            status = "BLOCKED"
        elif states & known_drift:
            status = "DRIFTED"
        else:
            status = "RECONCILED"

        identity = {
            "expected": exp["expected_state_id"],
            "actual": act["actual_state_id"],
            "records": records,
        }
        return {
            "schema_version": DRIFT_SCHEMA,
            "comparison_id": _stable_id("COMPARE", identity),
            "expected_state_id": exp["expected_state_id"],
            "actual_state_id": act["actual_state_id"],
            "platform": exp["platform"],
            "status": status,
            "records": records,
        }

    def propose_reconciliation(self, drift: dict[str, Any]) -> list[dict[str, Any]]:
        actions = []
        for record in drift.get("records", []):
            state = record.get("state")
            if state == "MISSING":
                action = "CREATE"
            elif state == "DRIFT":
                action = "UPDATE"
            else:
                action = "NO_ACTION"
            actions.append({
                "drift_id": record.get("drift_id"),
                "nexus_entity_id": record.get("nexus_entity_id"),
                "action": action,
                "requires_human_approval": action != "NO_ACTION",
            })
        return actions
