#!/usr/bin/env python3
"""Deterministic DV360 Expected-vs-Actual comparator for Nexus control-plane v1.

Consumes nexus-expected-state-v1 plus nexus-actual-state-v1 produced by
DV360ActualStateAdapter and emits nexus-drift-v1.

No networking, OAuth, credentials, writes, or reconciliation actions exist here.
Only fields declared comparable by capabilities/dv360-read-v1.json may MATCH.
Deferred/undeclared fields fail closed.
"""
from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_CAPABILITY_PATH = ROOT / "capabilities" / "dv360-read-v1.json"
EXPECTED_SCHEMA = "nexus-expected-state-v1"
ACTUAL_SCHEMA = "nexus-actual-state-v1"
DRIFT_SCHEMA = "nexus-drift-v1"

RESOURCE_BY_OBJECT_TYPE = {
    "CAMPAIGN": "campaign",
    "INSERTION_ORDER": "insertion_order",
    "LINE_ITEM": "line_item",
}


def _stable_id(prefix: str, value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:12].upper()}"


def _numeric_equal(left: Any, right: Any) -> bool:
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, ValueError, TypeError):
        return False


def _field_equal(mode: str, expected: Any, actual: Any) -> bool:
    if mode == "EXACT":
        return expected == actual
    if mode == "NUMERIC_EXACT":
        return _numeric_equal(expected, actual)
    if mode == "SET_EXACT":
        try:
            return set(expected) == set(actual)
        except TypeError:
            return False
    if mode == "ORDERED_EXACT":
        return expected == actual
    raise ValueError(f"Unsupported comparison mode: {mode}")


class DV360ExpectedVsActualComparator:
    """Compare approved DV360 Expected State against read-only DV360 Actual State."""

    comparator_version = "dv360-expected-actual-v1"
    platform = "DV360"

    def __init__(self, capability_path: Path | str = DEFAULT_CAPABILITY_PATH) -> None:
        self.capability_path = Path(capability_path)
        self.capability = json.loads(self.capability_path.read_text(encoding="utf-8"))
        self._validate_capability()

    def _validate_capability(self) -> None:
        cap = self.capability
        if cap.get("schema_version") != "nexus-platform-capability-v1":
            raise ValueError("Unsupported platform capability schema")
        if cap.get("capability_id") != "dv360-read-v1" or cap.get("platform") != self.platform:
            raise ValueError("Comparator requires the approved dv360-read-v1 capability")
        if cap.get("mode") != "READ_ONLY" or cap.get("writes_allowed") is not False:
            raise ValueError("DV360 capability must remain read-only")

    def _capability_fields(self, object_type: str) -> tuple[dict[str, dict[str, Any]], set[str]]:
        resource_name = RESOURCE_BY_OBJECT_TYPE.get(object_type)
        if resource_name is None:
            return {}, set()
        declaration = self.capability["resources"][resource_name]
        comparable = {entry["path"]: entry for entry in declaration.get("comparable_fields", [])}
        deferred = set(declaration.get("deferred_fields", []))
        return comparable, deferred

    @staticmethod
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
        severity: str,
        blocking: bool,
        detail: str | None = None,
    ) -> dict[str, Any]:
        identity = {
            "state": state,
            "nexus_entity_id": nexus_entity_id,
            "platform_object_type": platform_object_type,
            "platform_object_id": platform_object_id,
            "canonical_field": canonical_field,
            "platform_field": platform_field,
            "expected": expected,
            "actual": actual,
            "comparison_rule": comparison_rule,
            "detail": detail,
        }
        return {
            "drift_id": _stable_id("DRIFT-DV360", identity),
            "state": state,
            "nexus_entity_id": nexus_entity_id,
            "platform_object_id": platform_object_id,
            "platform_object_type": platform_object_type,
            "canonical_field": canonical_field,
            "platform_field": platform_field,
            "expected": copy.deepcopy(expected),
            "actual": copy.deepcopy(actual),
            "comparison_rule": comparison_rule,
            "severity": severity,
            "blocking": blocking,
            "detail": detail,
        }

    def _find_actual(self, expected_object: dict[str, Any], actual_objects: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
        nexus_id = expected_object["nexus_entity_id"]
        object_type = expected_object["platform_object_type"]
        candidates = [
            obj for obj in actual_objects
            if obj.get("platform_object_type") == object_type and obj.get("nexus_binding") == nexus_id
        ]
        if len(candidates) == 0:
            return "MISSING", None
        if len(candidates) > 1:
            return "AMBIGUOUS_BINDING", None
        return "BOUND", candidates[0]

    def _compare_managed_field(
        self,
        *,
        expected_object: dict[str, Any],
        actual_object: dict[str, Any],
        managed_field: dict[str, Any],
    ) -> dict[str, Any]:
        object_type = expected_object["platform_object_type"]
        nexus_id = expected_object["nexus_entity_id"]
        platform_object_id = actual_object["platform_object_id"]
        platform_field = managed_field["platform_field"]
        canonical_field = managed_field["canonical_field"]
        expected_value = managed_field.get("expected")
        expected_mode = managed_field["comparison_mode"]

        comparable, deferred = self._capability_fields(object_type)
        declaration = comparable.get(platform_field)
        if declaration is None:
            detail = "DEFERRED_FIELD_REQUIRED_BY_INTENT" if platform_field in deferred or any(
                platform_field.startswith(f"{path}.") for path in deferred
            ) else "FIELD_NOT_DECLARED_COMPARABLE"
            return self._record(
                state="UNSUPPORTED",
                nexus_entity_id=nexus_id,
                platform_object_type=object_type,
                platform_object_id=platform_object_id,
                canonical_field=canonical_field,
                platform_field=platform_field,
                expected=expected_value,
                actual=None,
                comparison_rule=None,
                severity="EXECUTION_BLOCKER",
                blocking=True,
                detail=detail,
            )

        capability_mode = declaration["comparison"]
        allowed_mode = {
            "EXACT": "EXACT",
            "NUMERIC_EXACT": "NUMERIC_EXACT",
            "SET_EXACT": "SET_EXACT",
        }.get(capability_mode)
        if allowed_mode is None or expected_mode != allowed_mode:
            return self._record(
                state="UNSUPPORTED",
                nexus_entity_id=nexus_id,
                platform_object_type=object_type,
                platform_object_id=platform_object_id,
                canonical_field=canonical_field,
                platform_field=platform_field,
                expected=expected_value,
                actual=None,
                comparison_rule=capability_mode,
                severity="EXECUTION_BLOCKER",
                blocking=True,
                detail=f"EXPECTED_COMPARISON_MODE_NOT_APPROVED:{expected_mode}",
            )

        comparable_values = actual_object.get("values", {}).get("comparable", {})
        if platform_field not in comparable_values:
            return self._record(
                state="READ_ERROR",
                nexus_entity_id=nexus_id,
                platform_object_type=object_type,
                platform_object_id=platform_object_id,
                canonical_field=canonical_field,
                platform_field=platform_field,
                expected=expected_value,
                actual=None,
                comparison_rule=allowed_mode,
                severity="EXECUTION_BLOCKER",
                blocking=True,
                detail="DECLARED_FIELD_MISSING_FROM_ACTUAL_STATE",
            )

        actual_value = comparable_values[platform_field]
        matches = _field_equal(allowed_mode, expected_value, actual_value)
        return self._record(
            state="MATCH" if matches else "DRIFT",
            nexus_entity_id=nexus_id,
            platform_object_type=object_type,
            platform_object_id=platform_object_id,
            canonical_field=canonical_field,
            platform_field=platform_field,
            expected=expected_value,
            actual=actual_value,
            comparison_rule=allowed_mode,
            severity="INFO" if matches else "CRITICAL",
            blocking=False if matches else True,
            detail=None if matches else "MANAGED_FIELD_MISMATCH",
        )

    def _compare_relationships(
        self,
        *,
        expected_object: dict[str, Any],
        actual_object: dict[str, Any],
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        actual_relationships = actual_object.get("relationships", [])
        actual_pairs = {
            (str(rel.get("type")), str(rel.get("platform_object_id")))
            for rel in actual_relationships
        }
        for rel in expected_object.get("relationships", []):
            rel_type = str(rel.get("type"))
            expected_parent = rel.get("platform_object_id")
            if expected_parent is None:
                records.append(self._record(
                    state="UNSUPPORTED",
                    nexus_entity_id=expected_object["nexus_entity_id"],
                    platform_object_type=expected_object["platform_object_type"],
                    platform_object_id=actual_object["platform_object_id"],
                    canonical_field="relationship",
                    platform_field=rel_type,
                    expected=rel,
                    actual=actual_relationships,
                    comparison_rule="EXACT_RELATIONSHIP",
                    severity="EXECUTION_BLOCKER",
                    blocking=True,
                    detail="EXPECTED_RELATIONSHIP_MISSING_PLATFORM_OBJECT_ID",
                ))
                continue

            exact = (rel_type, str(expected_parent)) in actual_pairs
            same_type = [r for r in actual_relationships if str(r.get("type")) == rel_type]
            records.append(self._record(
                state="MATCH" if exact else "DRIFT",
                nexus_entity_id=expected_object["nexus_entity_id"],
                platform_object_type=expected_object["platform_object_type"],
                platform_object_id=actual_object["platform_object_id"],
                canonical_field="relationship",
                platform_field=rel_type,
                expected=str(expected_parent),
                actual=[str(r.get("platform_object_id")) for r in same_type],
                comparison_rule="EXACT_RELATIONSHIP",
                severity="INFO" if exact else "CRITICAL",
                blocking=False if exact else True,
                detail=None if exact else "PARENT_RELATIONSHIP_MISMATCH",
            ))
        return records

    def compare(self, expected_state: dict[str, Any], actual_state: dict[str, Any]) -> dict[str, Any]:
        expected = copy.deepcopy(expected_state)
        actual = copy.deepcopy(actual_state)

        if expected.get("schema_version") != EXPECTED_SCHEMA:
            raise ValueError("Expected State must use nexus-expected-state-v1")
        if actual.get("schema_version") != ACTUAL_SCHEMA:
            raise ValueError("Actual State must use nexus-actual-state-v1")
        if expected.get("platform") != self.platform or actual.get("platform") != self.platform:
            raise ValueError("Comparator accepts DV360 states only")
        if expected.get("account_context_id") != actual.get("account_context_id"):
            raise ValueError("Expected/Actual account context mismatch")

        records: list[dict[str, Any]] = []

        if expected.get("status") != "EXPECTED_READY":
            records.append(self._record(
                state="UNKNOWN",
                nexus_entity_id=None,
                platform_object_type="EXPECTED_STATE",
                severity="EXECUTION_BLOCKER",
                blocking=True,
                detail="EXPECTED_STATE_NOT_READY",
            ))
        if actual.get("completeness") != "COMPLETE":
            records.append(self._record(
                state="READ_ERROR",
                nexus_entity_id=None,
                platform_object_type="ACTUAL_STATE",
                severity="EXECUTION_BLOCKER",
                blocking=True,
                detail=f"ACTUAL_STATE_NOT_COMPLETE:{actual.get('completeness')}",
                actual=actual.get("read_failures", []),
            ))

        actual_objects = actual.get("objects", [])
        for expected_object in expected.get("objects", []):
            binding_state, actual_object = self._find_actual(expected_object, actual_objects)
            if binding_state == "MISSING":
                records.append(self._record(
                    state="MISSING",
                    nexus_entity_id=expected_object["nexus_entity_id"],
                    platform_object_type=expected_object["platform_object_type"],
                    expected=expected_object.get("expected_binding_id"),
                    severity="CRITICAL" if expected_object.get("required", True) else "WARNING",
                    blocking=bool(expected_object.get("required", True)),
                    detail="EXPECTED_OBJECT_NOT_FOUND_BY_NEXUS_BINDING",
                ))
                continue
            if binding_state == "AMBIGUOUS_BINDING":
                records.append(self._record(
                    state="AMBIGUOUS_BINDING",
                    nexus_entity_id=expected_object["nexus_entity_id"],
                    platform_object_type=expected_object["platform_object_type"],
                    severity="EXECUTION_BLOCKER",
                    blocking=True,
                    detail="MULTIPLE_ACTUAL_OBJECTS_CLAIM_NEXUS_IDENTITY",
                ))
                continue

            assert actual_object is not None
            for managed_field in expected_object.get("managed_fields", []):
                records.append(self._compare_managed_field(
                    expected_object=expected_object,
                    actual_object=actual_object,
                    managed_field=managed_field,
                ))
            records.extend(self._compare_relationships(
                expected_object=expected_object,
                actual_object=actual_object,
            ))

        blocker_states = {"AMBIGUOUS_BINDING", "READ_ERROR", "UNSUPPORTED", "UNKNOWN"}
        if any(record["state"] in blocker_states for record in records):
            status = "BLOCKED"
        elif any(record["state"] in {"DRIFT", "MISSING", "UNEXPECTED"} for record in records):
            status = "DRIFTED"
        else:
            status = "RECONCILED"

        comparison_identity = {
            "expected_state_id": expected["expected_state_id"],
            "actual_state_id": actual["actual_state_id"],
            "capability_id": self.capability["capability_id"],
            "records": records,
        }
        return {
            "schema_version": DRIFT_SCHEMA,
            "comparison_id": _stable_id("COMPARE-DV360", comparison_identity),
            "expected_state_id": expected["expected_state_id"],
            "actual_state_id": actual["actual_state_id"],
            "platform": self.platform,
            "status": status,
            "records": records,
        }
