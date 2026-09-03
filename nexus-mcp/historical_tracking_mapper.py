#!/usr/bin/env python3
"""Read-only structural mapper for the historical tracking-code generator workbook.

It emits Campaign/Audience/Creative/Activation candidates with source-row evidence.
It never edits the workbook or calls the frozen Nexus compiler. Missing/conflicting
facts remain explicit blockers.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from xlsx_ingest import read_sheet

SHEET = "tracking code generator"
MAX_BYTES = 5 * 1024 * 1024
INPUT_HEADERS = [
    "target URL", "placement (medium)", "paid link", "vendor (source)",
    "campaign year", "campaign team", "campaign (short) name", "country",
    "device", "Format Type", "Ad Name", "ad width", "ad height", "include UTM codes",
]
DERIVED_FIELDS = {
    15: "strategy_type", 16: "campaign", 17: "campaign_name", 18: "reserved_s",
    19: "campaign_period", 20: "activity_name", 21: "package_name", 22: "targeting",
    23: "placement_name", 24: "generate_tracking_code", 25: "target_url_clean",
    26: "channel", 27: "source", 28: "normalized_campaign_year",
    29: "normalized_campaign_team", 30: "normalized_campaign_name",
    31: "normalized_country", 32: "creative_elements", 33: "normalized_format_type",
    34: "normalized_ad_name", 35: "cid_code", 36: "utm_medium", 37: "utm_source",
    38: "utm_content", 39: "utm_campaign", 40: "utm_term", 41: "utm_code",
    42: "tracking_code", 43: "target_url_plus_tracking_code",
}


def stable_id(prefix: str, *parts: Any) -> str:
    value = "\x1f".join("" if p is None else str(p).strip().casefold() for p in parts)
    return f"{prefix}-{hashlib.sha256(value.encode()).hexdigest()[:12].upper()}"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _one(values: set[str]) -> str | None:
    return next(iter(values)) if len(values) == 1 else None


def map_tracking_rows(rows: list[list[Any]], filename: str) -> dict[str, Any]:
    if len(rows) < 3:
        raise ValueError("Tracking workbook has no campaign rows")
    headers = ["" if v is None else str(v).strip() for v in rows[1][:14]]
    if headers != INPUT_HEADERS:
        raise ValueError(f"Unexpected tracking input headers: {headers!r}")

    populated: list[tuple[int, list[Any]]] = []
    for excel_row, row in enumerate(rows[2:], start=3):
        row = (list(row) + [None] * 44)[:44]
        if any(v not in (None, "") for v in row[:14]):
            populated.append((excel_row, row))
    if not populated:
        raise ValueError("Tracking workbook has no populated campaign rows")

    source_rows = []
    sets = {k: set() for k in ("short_names", "campaigns", "objectives", "countries", "years", "teams", "periods", "platforms")}
    audience_refs: dict[str, list[str]] = defaultdict(list)
    creative_refs: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    creative_data: dict[tuple[Any, ...], dict[str, Any]] = {}
    semantic_activations: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    activations = []

    for excel_row, row in populated:
        ref = f"{SHEET}!{excel_row}"
        inputs = {name: row[i] for i, name in enumerate(INPUT_HEADERS)}
        derived = {name: row[i] for i, name in DERIVED_FIELDS.items()}
        source_rows.append({"source_ref": ref, "sheet": SHEET, "excel_row": excel_row, "input_values": inputs, "derived_values": derived})

        values = {
            "short_names": _text(row[6]), "campaigns": _text(row[16]), "objectives": _text(row[15]),
            "countries": _text(row[7]), "years": _text(row[4]), "teams": _text(row[5]),
            "periods": _text(row[19]), "platforms": _text(row[3]),
        }
        for key, value in values.items():
            if value:
                sets[key].add(value)

        targeting = _text(row[22])
        if targeting:
            audience_refs[targeting].append(ref)

        platform = _text(row[3])
        size = f"{row[11]}x{row[12]}" if row[11] not in (None, "") and row[12] not in (None, "") else None
        creative_key = (platform, _text(row[10]), size, _text(row[9]), _text(row[0]))
        creative_id = stable_id("CRECAND", *creative_key)
        creative_refs[creative_key].append(ref)
        creative_data.setdefault(creative_key, {
            "platform": platform, "creative_name": _text(row[10]), "size": size,
            "ad_format": _text(row[9]), "landing_page_url": _text(row[0]),
            "placement_medium": _text(row[1]), "normalized_ad_name": _text(row[34]),
            "utm_code": _text(row[41]), "tracking_code": _text(row[42]),
            "final_tracking_url": _text(row[43]),
        })

        semantic_key = (platform, targeting, creative_id, _text(row[23]), _text(row[19]), _text(row[0]))
        semantic_activations[semantic_key].append(ref)
        activations.append({
            "activation_candidate_id": stable_id("ACTCAND", ref, *semantic_key),
            "source_ref": ref, "platform": platform,
            "audience_candidate_id": stable_id("AUDCAND", targeting) if targeting else None,
            "creative_candidate_id": creative_id, "campaign_period": _text(row[19]),
            "placement_name": _text(row[23]), "device": _text(row[8]), "paid_link": row[2],
            "landing_page_url": _text(row[0]), "final_tracking_url": _text(row[43]),
        })

    audiences = [{"audience_candidate_id": stable_id("AUDCAND", name), "audience_name": name, "source_evidence": refs} for name, refs in sorted(audience_refs.items())]
    creatives = [{"creative_candidate_id": stable_id("CRECAND", *key), **creative_data[key], "source_evidence": creative_refs[key]} for key in sorted(creative_data, key=lambda x: tuple("" if v is None else str(v) for v in x))]

    names = sorted(sets["short_names"] | sets["campaigns"])
    campaign = {
        "campaign_candidate_id": stable_id("CMPCAND", *sorted(sets["years"]), *sorted(sets["teams"]), *names, *sorted(sets["countries"]), *sorted(sets["objectives"])),
        "client": None, "campaign_name": names[0] if len(names) == 1 else None,
        "campaign_name_candidates": names, "objective": _one(sets["objectives"]),
        "market": _one(sets["countries"]), "currency": None, "campaign_year": _one(sets["years"]),
        "campaign_team": _one(sets["teams"]), "campaign_period": _one(sets["periods"]),
        "platform": _one(sets["platforms"]), "platform_candidates": sorted(sets["platforms"]),
        "flight_start": None, "flight_end": None, "source_evidence": [r["source_ref"] for r in source_rows],
    }

    ambiguities = [
        {"field": "campaign.client", "reason": "MISSING_SOURCE_FIELD", "candidates": [], "resolution_required": True},
        {"field": "campaign.currency", "reason": "MISSING_SOURCE_FIELD", "candidates": [], "resolution_required": True},
        {"field": "campaign.flight_start", "reason": "EXACT_DATE_MISSING", "candidates": sorted(sets["periods"]), "resolution_required": True},
        {"field": "campaign.flight_end", "reason": "EXACT_DATE_MISSING", "candidates": sorted(sets["periods"]), "resolution_required": True},
    ]
    if len(names) != 1:
        ambiguities.append({"field": "campaign.campaign_name", "reason": "MULTIPLE_SOURCE_VALUES", "candidates": names, "resolution_required": True})
    if len(sets["platforms"]) != 1:
        ambiguities.append({"field": "campaign.platform", "reason": "MULTIPLE_SOURCE_VALUES", "candidates": sorted(sets["platforms"]), "resolution_required": True})

    issues = []
    for key, refs in semantic_activations.items():
        if len(refs) > 1:
            issues.append({
                "type": "DUPLICATE_ACTIVATION_CANDIDATE", "source_refs": refs, "platform": key[0],
                "audience_candidate_id": stable_id("AUDCAND", key[1]) if key[1] else None,
                "creative_candidate_id": key[2], "placement_name": key[3], "campaign_period": key[4],
                "landing_page_url": key[5], "blocking": True,
            })

    blocked = bool(ambiguities or issues)
    return {
        "schema": "nexus-structural-candidates-v0", "mapper_status": "NEEDS_CONFIRMATION" if blocked else "READY_CANDIDATES",
        "compiler_allowed": not blocked, "source": {"filename": filename, "sheet": SHEET, "read_only": True},
        "counts": {"source_rows": len(source_rows), "campaign_candidates": 1, "audience_candidates": len(audiences), "creative_candidates": len(creatives), "activation_candidates": len(activations)},
        "campaigns": [campaign], "audiences": audiences, "creatives": creatives, "activations": activations,
        "source_rows": source_rows, "ambiguities": ambiguities, "validation_issues": issues,
    }


def map_tracking_workbook(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.suffix.lower() != ".xlsx" or path.stat().st_size > MAX_BYTES:
        raise ValueError("Expected one .xlsx workbook <= 5 MiB")
    return map_tracking_rows(read_sheet(path, SHEET), path.name)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(json.dumps({"error": "usage: historical_tracking_mapper.py workbook.xlsx"}))
        return 2
    try:
        print(json.dumps(map_tracking_workbook(argv[1]), indent=2, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))