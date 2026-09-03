#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from canonical_gate import assess_canonical_compatibility, execute_if_compatible
from xlsx_ingest import canonicalize_xlsx

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "Nexus_Parser_Test_Media_Plan.xlsx"


def _compatible_subset(source: dict) -> dict:
    ready = deepcopy(source)
    selected = [
        activation
        for activation in ready["activations"]
        if activation["platform"] == "DV360"
        and activation["flight_start"] == "2026-10-01"
        and activation["flight_end"] == "2026-10-31"
    ]
    ready["activations"] = selected
    ready["canonical_status"] = "READY"
    ready["ambiguities"] = []
    ready["validation_issues"] = []
    ready["campaign"]["platform"] = "DV360"
    ready["campaign"]["flight_start"] = "2026-10-01"
    ready["campaign"]["flight_end"] = "2026-10-31"
    ready["campaign"]["flight_scope"] = "exact"
    ready["counts"]["activations"] = len(selected)
    return ready


def main() -> None:
    mixed = canonicalize_xlsx(FIXTURE)
    before = deepcopy(mixed)
    calls: list[str] = []

    blocked = execute_if_compatible(mixed, lambda: calls.append("CALLED"))
    assert blocked["gate"]["status"] == "BLOCKED"
    assert blocked["gate"]["reason"] == "NEEDS_CONFIRMATION"
    assert blocked["gate"]["compiler_allowed"] is False
    assert blocked["compiler_called"] is False
    assert blocked["compile_result"] is None
    assert calls == []
    assert blocked["gate"]["unresolved"] == mixed["ambiguities"]
    assert blocked["gate"]["unresolved"] == [
        {
            "field": "campaign.platform",
            "reason": "MULTIPLE_SOURCE_VALUES",
            "candidates": ["CM360", "DV360"],
            "resolution_required": True,
        },
        {
            "field": "campaign.flight",
            "reason": "MULTIPLE_SOURCE_VALUES",
            "candidates": [
                {"flight_start": "2026-10-01", "flight_end": "2026-10-31"},
                {"flight_start": "2026-10-05", "flight_end": "2026-10-31"},
                {"flight_start": "2026-10-10", "flight_end": "2026-11-15"},
                {"flight_start": "2026-10-15", "flight_end": "2026-11-15"},
            ],
            "resolution_required": True,
        },
    ]
    assert mixed == before

    ready = _compatible_subset(mixed)
    assert ready["counts"]["activations"] == 3
    ready_before = deepcopy(ready)
    ready_calls: list[str] = []
    passed = execute_if_compatible(
        ready,
        lambda: ready_calls.append("CALLED") or {"status": "COMPILE_STUB_OK"},
    )
    assert passed["gate"] == {
        "status": "READY_FOR_COMPILE",
        "reason": "COMPATIBLE",
        "compiler_allowed": True,
        "failures": [],
        "unresolved": [],
        "validation_issues": [],
    }
    assert passed["compiler_called"] is True
    assert passed["compile_result"] == {"status": "COMPILE_STUB_OK"}
    assert ready_calls == ["CALLED"]
    assert ready == ready_before

    unknown = deepcopy(ready)
    unknown["canonical_status"] = "MYSTERY"
    rejected = assess_canonical_compatibility(unknown)
    assert rejected["status"] == "BLOCKED"
    assert rejected["compiler_allowed"] is False

    print("PASS: mixed-platform/multi-flight XLSX canonical is BLOCKED before compiler invocation")
    print("PASS: exact unresolved campaign.platform + campaign.flight evidence preserved")
    print("PASS: compatible READY canonical reaches unchanged compiler callback without mutation")
    print("PASS: unknown canonical status fails closed")


if __name__ == "__main__":
    main()
