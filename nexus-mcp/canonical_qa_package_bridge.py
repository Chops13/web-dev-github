#!/usr/bin/env python3
"""Deterministic QA/package bridge for one compiled Nexus canonical campaign.

This module connects a READY nexus-canonical-campaign-v0 payload to deterministic QA
and in-memory trafficking-package generation without changing Hermes, MCP, the frozen
fixture QA, or the frozen 14-column trafficking export contract.

It consumes the build rows emitted by canonical_compile_bridge.compile_ready_canonical.
Package generation is fail-closed: any integrity/provenance failure returns BLOCKED and
no trafficking CSV.
"""
from __future__ import annotations

import csv
import io
import re
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from canonical_compile_bridge import compile_ready_canonical
from server import TRAFFICKING_COLUMNS

REQUIRED_BUILD_FIELDS = (
    "build_row_id",
    "campaign_key",
    "plan_row_id",
    "platform",
    "campaign_name",
    "flight_start",
    "flight_end",
    "activation_id",
    "audience_row_id",
    "audience_name",
    "creative_row_id",
    "creative_id",
    "ad_format",
    "size",
)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_http_url(value: Any) -> bool:
    if not _nonempty(value):
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _failure(check_id: str, entity_id: str | None, field: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "severity": "BLOCKING",
        "entity_id": entity_id,
        "field": field,
        "expected": expected,
        "actual": actual,
    }


def run_canonical_qa(canonical: dict[str, Any], compiled: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic, fail-closed QA over one canonical compile result."""
    before_canonical = deepcopy(canonical)
    before_compiled = deepcopy(compiled)
    failures: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    compile_result = compiled.get("compile_result") if isinstance(compiled, dict) else None
    if not isinstance(compiled, dict) or compiled.get("status") != "COMPILED_PREVIEW" or not isinstance(compile_result, dict):
        failures.append(_failure("QA-COMPILE-STATE-001", None, "compile.status", "COMPILED_PREVIEW", compiled.get("status") if isinstance(compiled, dict) else type(compiled).__name__))
        return {
            "status": "BLOCKED",
            "fail_closed": True,
            "override_allowed": False,
            "counts": {"checks_executed": 1, "failures": 1, "blocking_failures": 1},
            "checks": [{"check_id": "QA-COMPILE-STATE-001", "severity": "BLOCKING", "passed": False}],
            "failures": failures,
        }

    activations = canonical.get("activations")
    audiences = canonical.get("audiences")
    creatives = canonical.get("creatives")
    campaign = canonical.get("campaign")
    build_rows = compile_result.get("build_rows")
    if not isinstance(activations, list) or not isinstance(audiences, list) or not isinstance(creatives, list) or not isinstance(campaign, dict) or not isinstance(build_rows, list):
        failures.append(_failure("QA-CANONICAL-SHAPE-001", None, "canonical", "campaign/audiences/creatives/activations/build_rows", "invalid shape"))
        return {
            "status": "BLOCKED",
            "fail_closed": True,
            "override_allowed": False,
            "counts": {"checks_executed": 1, "failures": 1, "blocking_failures": 1},
            "checks": [{"check_id": "QA-CANONICAL-SHAPE-001", "severity": "BLOCKING", "passed": False}],
            "failures": failures,
        }

    audience_by_id = {item.get("audience_row_id"): item for item in audiences if isinstance(item, dict)}
    creative_by_id = {item.get("creative_row_id"): item for item in creatives if isinstance(item, dict)}
    activation_by_id = {item.get("activation_id"): item for item in activations if isinstance(item, dict)}
    build_by_activation = {item.get("activation_id"): item for item in build_rows if isinstance(item, dict)}

    def record(check_id: str, passed: bool) -> None:
        checks.append({"check_id": check_id, "severity": "BLOCKING", "passed": passed})

    count_pass = len(build_rows) == len(activations) == len(build_by_activation) == len(activation_by_id)
    record("QA-ROW-COUNT-001", count_pass)
    if not count_pass:
        failures.append(_failure(
            "QA-ROW-COUNT-001", None, "build_rows",
            {"activations": len(activations), "unique_activations": len(activation_by_id)},
            {"build_rows": len(build_rows), "unique_build_activation_ids": len(build_by_activation)},
        ))

    for build in build_rows:
        if not isinstance(build, dict):
            record("QA-BUILD-SHAPE-001", False)
            failures.append(_failure("QA-BUILD-SHAPE-001", None, "build_row", "object", type(build).__name__))
            continue
        activation_id = build.get("activation_id")
        missing = [field for field in REQUIRED_BUILD_FIELDS if not _nonempty(build.get(field))]
        passed_required = not missing
        record("QA-BUILD-REQUIRED-001", passed_required)
        if missing:
            failures.append(_failure("QA-BUILD-REQUIRED-001", activation_id, "build_row.required", "all required", missing))
            continue

        activation = activation_by_id.get(activation_id)
        passed_activation = isinstance(activation, dict)
        record("QA-ACTIVATION-LINK-001", passed_activation)
        if not passed_activation:
            failures.append(_failure("QA-ACTIVATION-LINK-001", activation_id, "activation_id", "known canonical activation", activation_id))
            continue

        audience = audience_by_id.get(activation.get("audience_row_id"))
        creative = creative_by_id.get(activation.get("creative_row_id"))
        link_pass = isinstance(audience, dict) and isinstance(creative, dict)
        record("QA-REFERENTIAL-001", link_pass)
        if not link_pass:
            failures.append(_failure(
                "QA-REFERENTIAL-001", activation_id, "activation.references", "known audience and creative",
                {"audience_row_id": activation.get("audience_row_id"), "creative_row_id": activation.get("creative_row_id")},
            ))
            continue

        expected_build = {
            "build_row_id": f"BLD-{activation_id}",
            "campaign_key": campaign.get("campaign_key"),
            "plan_row_id": activation.get("plan_row_id"),
            "platform": campaign.get("platform"),
            "campaign_name": campaign.get("campaign_name"),
            "flight_start": campaign.get("flight_start"),
            "flight_end": campaign.get("flight_end"),
            "activation_id": activation_id,
            "audience_row_id": activation.get("audience_row_id"),
            "audience_name": audience.get("audience_name"),
            "creative_row_id": activation.get("creative_row_id"),
            "creative_id": creative.get("creative_id"),
            "ad_format": creative.get("ad_format"),
            "size": creative.get("size"),
        }
        semantics_pass = all(build.get(key) == value for key, value in expected_build.items())
        record("QA-BUILD-SEMANTICS-001", semantics_pass)
        if not semantics_pass:
            mismatches = {
                key: {"expected": value, "actual": build.get(key)}
                for key, value in expected_build.items()
                if build.get(key) != value
            }
            failures.append(_failure("QA-BUILD-SEMANTICS-001", activation_id, "build_row", expected_build, mismatches))

        size_pass = bool(re.fullmatch(r"\d+x\d+", str(build.get("size") or "")))
        record("QA-CREATIVE-SIZE-FORMAT-001", size_pass)
        if not size_pass:
            failures.append(_failure("QA-CREATIVE-SIZE-FORMAT-001", activation_id, "size", "<width>x<height>", build.get("size")))

        placement_pass = _nonempty(activation.get("placement_name"))
        record("QA-PLACEMENT-001", placement_pass)
        if not placement_pass:
            failures.append(_failure("QA-PLACEMENT-001", activation_id, "placement_name", "source-backed value", activation.get("placement_name")))

        landing_pass = _valid_http_url(activation.get("landing_page_url"))
        record("QA-LANDING-URL-001", landing_pass)
        if not landing_pass:
            failures.append(_failure("QA-LANDING-URL-001", activation_id, "landing_page_url", "valid http(s) URL", activation.get("landing_page_url")))

        tracking_pass = _valid_http_url(activation.get("final_tracking_url"))
        record("QA-TRACKING-URL-001", tracking_pass)
        if not tracking_pass:
            failures.append(_failure("QA-TRACKING-URL-001", activation_id, "final_tracking_url", "valid http(s) URL", activation.get("final_tracking_url")))

    status = "BLOCKED" if failures else "PASS"
    if canonical != before_canonical or compiled != before_compiled:
        raise AssertionError("canonical QA mutated input")
    return {
        "status": status,
        "fail_closed": True,
        "override_allowed": False,
        "counts": {
            "checks_executed": len(checks),
            "failures": len(failures),
            "blocking_failures": len(failures),
        },
        "checks": checks,
        "failures": failures,
    }


def prepare_canonical_package(canonical: dict[str, Any], compiled: dict[str, Any]) -> dict[str, Any]:
    """Generate the frozen 14-column in-memory CSV only after canonical QA PASS."""
    qa = run_canonical_qa(canonical, compiled)
    if qa.get("status") != "PASS":
        return {
            "status": "BLOCKED",
            "qa_status": qa.get("status"),
            "package_created": False,
            "writes_files": False,
            "publishes": False,
            "qa": qa,
            "artifact": None,
        }

    compile_result = compiled["compile_result"]
    activations = {item["activation_id"]: item for item in canonical["activations"]}
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=TRAFFICKING_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for build in compile_result["build_rows"]:
        activation = activations[build["activation_id"]]
        writer.writerow({
            "Campaign_Key": build["campaign_key"],
            "Plan_Row_ID": build["plan_row_id"],
            "Platform": build["platform"],
            "Campaign_Name": build["campaign_name"],
            "Placement_Name": activation["placement_name"],
            "Ad_Format": build["ad_format"],
            "Flight_Dates": f"{build['flight_start']} to {build['flight_end']}",
            "Audience_Targeting": build["audience_name"],
            "Creative_ID": build["creative_id"],
            "Landing_Page_URL": activation["landing_page_url"],
            "Final_Tracking_URL": activation["final_tracking_url"],
            "Activation_ID": build["activation_id"],
            "Audience_Row_ID": build["audience_row_id"],
            "Creative_Row_ID": build["creative_row_id"],
        })

    return {
        "status": "READY_FOR_APPROVAL",
        "qa_status": "PASS",
        "package_created": True,
        "in_memory": True,
        "writes_files": False,
        "publishes": False,
        "qa": qa,
        "artifact": {
            "filename": "nexus_trafficking.csv",
            "media_type": "text/csv",
            "columns": TRAFFICKING_COLUMNS,
            "row_count": len(compile_result["build_rows"]),
            "content": output.getvalue(),
        },
    }


def compile_qa_package(canonical: dict[str, Any]) -> dict[str, Any]:
    """Convenience bridge: compile, deterministic QA, then package if and only if QA passes."""
    compiled = compile_ready_canonical(canonical)
    if compiled.get("status") != "COMPILED_PREVIEW":
        return {
            "status": "BLOCKED",
            "compiled": compiled,
            "qa": None,
            "package": None,
        }
    package = prepare_canonical_package(canonical, compiled)
    return {
        "status": package["status"],
        "compiled": compiled,
        "qa": package["qa"],
        "package": package,
    }
