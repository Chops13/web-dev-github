#!/usr/bin/env python3
"""DV360 read-only Actual State adapter for Nexus control-plane v1.

Consumes caller-supplied DV360-shaped GET responses and projects them through
capabilities/dv360-read-v1.json into nexus-actual-state-v1.

No networking, OAuth, credentials, or write methods exist in this module.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_CAPABILITY_PATH = ROOT / "capabilities" / "dv360-read-v1.json"
ACTUAL_SCHEMA = "nexus-actual-state-v1"


def _stable_id(prefix: str, value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:12].upper()}"


def _get_path(payload: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _project_paths(payload: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for path in paths:
        present, value = _get_path(payload, path)
        if present:
            projected[path] = copy.deepcopy(value)
    return projected


def _deferred_leaf_paths(payload: dict[str, Any], declared_paths: list[str]) -> dict[str, Any]:
    """Project deferred top-level/nested paths when a concrete value is present.

    Collection wildcards such as campaignBudgets[].invoiceGroupingId are preserved
    only as declaration metadata for now; nested collections are handled separately.
    """
    concrete = [path for path in declared_paths if "[]" not in path]
    return _project_paths(payload, concrete)


class DV360ActualStateAdapter:
    """Deterministic, read-only projection of DV360 GET responses into Actual State."""

    adapter_version = "dv360-actual-state-v1"
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
            raise ValueError("Adapter requires the approved dv360-read-v1 capability")
        if cap.get("api_version") != "v4":
            raise ValueError("Adapter requires DV360 API v4 capability")
        if cap.get("mode") != "READ_ONLY" or cap.get("writes_allowed") is not False:
            raise ValueError("DV360 capability must be read-only")
        if cap.get("oauth_flow_in_scope") is not False or cap.get("other_platforms_in_scope") is not False:
            raise ValueError("OAuth and other platforms must remain out of scope")

    def _project_nested_collections(
        self,
        payload: dict[str, Any],
        resource_decl: dict[str, Any],
    ) -> dict[str, Any]:
        projected: dict[str, Any] = {}
        for collection_path, declaration in resource_decl.get("nested_collections", {}).items():
            present, collection = _get_path(payload, collection_path)
            if not present:
                continue
            if not isinstance(collection, list):
                raise ValueError(f"DV360 nested collection {collection_path} must be a list")
            child_paths = [entry["path"] for entry in declaration.get("comparable_fields", [])]
            platform_id_field = declaration.get("platform_id_field")
            items = []
            for child in collection:
                if not isinstance(child, dict):
                    raise ValueError(f"DV360 nested collection {collection_path} contains a non-object")
                item = {
                    "comparable": _project_paths(child, child_paths),
                }
                if platform_id_field and platform_id_field in child:
                    item["platform_object_id"] = str(child[platform_id_field])
                items.append(item)
            projected[collection_path] = items
        return projected

    def _relationships(self, resource_name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        relationships: list[dict[str, Any]] = []
        if resource_name in {"insertion_order", "line_item"} and payload.get("campaignId") is not None:
            relationships.append({
                "type": "PARENT_CAMPAIGN",
                "platform_object_id": str(payload["campaignId"]),
            })
        if resource_name == "line_item" and payload.get("insertionOrderId") is not None:
            relationships.append({
                "type": "PARENT_INSERTION_ORDER",
                "platform_object_id": str(payload["insertionOrderId"]),
            })
        return relationships

    def _project_object(
        self,
        resource_name: str,
        payload: dict[str, Any],
        *,
        account_context_id: str,
        bindings: dict[str, dict[str, str]],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        declaration = self.capability["resources"][resource_name]
        binding_decl = declaration["binding"]
        id_field = binding_decl["platform_id_field"]
        platform_object_id = payload.get(id_field)
        if platform_object_id is None:
            return None, {
                "resource": resource_name,
                "reason": "MISSING_PLATFORM_OBJECT_ID",
                "field": id_field,
            }

        advertiser_id = payload.get("advertiserId")
        if advertiser_id is not None and str(advertiser_id) != str(account_context_id):
            return None, {
                "resource": resource_name,
                "platform_object_id": str(platform_object_id),
                "reason": "ACCOUNT_CONTEXT_MISMATCH",
                "expected": str(account_context_id),
                "actual": str(advertiser_id),
            }

        comparable_paths = [entry["path"] for entry in declaration.get("comparable_fields", [])]
        observe_only_paths = list(declaration.get("observe_only_fields", []))
        deferred_paths = list(declaration.get("deferred_fields", []))

        values: dict[str, Any] = {
            "comparable": _project_paths(payload, comparable_paths),
            "observe_only": _project_paths(payload, observe_only_paths),
            "deferred": _deferred_leaf_paths(payload, deferred_paths),
        }
        nested = self._project_nested_collections(payload, declaration)
        if nested:
            values["nested_collections"] = nested

        object_type = declaration["object_type"]
        object_bindings = bindings.get(object_type, {})
        nexus_binding = object_bindings.get(str(platform_object_id))

        status = payload.get("entityStatus")
        return {
            "platform_object_id": str(platform_object_id),
            "platform_object_type": object_type,
            "nexus_binding": nexus_binding,
            "values": values,
            "relationships": self._relationships(resource_name, payload),
            "status": str(status) if status is not None else None,
        }, None

    def read_actual(
        self,
        *,
        account_context_id: str,
        responses: dict[str, list[dict[str, Any]]],
        bindings: dict[str, dict[str, str]] | None = None,
        captured_at: str,
        pagination_complete: dict[str, bool] | None = None,
        raw_snapshot_reference: str | None = None,
    ) -> dict[str, Any]:
        """Project supplied GET responses into nexus-actual-state-v1.

        Expected response keys are campaign, insertion_order, and line_item. The
        adapter performs no I/O. Pagination completeness is caller-supplied because
        networking is intentionally out of scope.
        """
        if not account_context_id:
            raise ValueError("account_context_id is required")
        if not captured_at:
            raise ValueError("captured_at is required")

        bindings = copy.deepcopy(bindings or {})
        pagination_complete = copy.deepcopy(pagination_complete or {})
        resources = ("campaign", "insertion_order", "line_item")

        objects: list[dict[str, Any]] = []
        read_failures: list[dict[str, Any]] = []

        for resource_name in resources:
            items = responses.get(resource_name, [])
            if not isinstance(items, list):
                raise ValueError(f"responses[{resource_name!r}] must be a list")
            for payload in items:
                if not isinstance(payload, dict):
                    raise ValueError(f"responses[{resource_name!r}] contains a non-object")
                projected, failure = self._project_object(
                    resource_name,
                    copy.deepcopy(payload),
                    account_context_id=str(account_context_id),
                    bindings=bindings,
                )
                if failure:
                    read_failures.append(failure)
                elif projected:
                    objects.append(projected)

        incomplete = [name for name in resources if pagination_complete.get(name, True) is not True]
        for resource_name in incomplete:
            read_failures.append({
                "resource": resource_name,
                "reason": "INCOMPLETE_PAGINATION",
            })

        if any(failure.get("reason") in {"MISSING_PLATFORM_OBJECT_ID", "ACCOUNT_CONTEXT_MISMATCH"} for failure in read_failures):
            completeness = "READ_ERROR"
        elif incomplete:
            completeness = "PARTIAL"
        else:
            completeness = "COMPLETE"

        identity = {
            "platform": self.platform,
            "adapter_version": self.adapter_version,
            "account_context_id": str(account_context_id),
            "captured_at": captured_at,
            "objects": objects,
            "completeness": completeness,
            "read_failures": read_failures,
            "raw_snapshot_reference": raw_snapshot_reference,
        }
        return {
            "schema_version": ACTUAL_SCHEMA,
            "actual_state_id": _stable_id("ACTUAL-DV360", identity),
            "platform": self.platform,
            "adapter_version": self.adapter_version,
            "account_context_id": str(account_context_id),
            "captured_at": captured_at,
            "completeness": completeness,
            "objects": objects,
            "read_failures": read_failures,
            "raw_snapshot_reference": raw_snapshot_reference,
        }
