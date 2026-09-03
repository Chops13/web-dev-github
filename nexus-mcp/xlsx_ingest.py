#!/usr/bin/env python3
"""Nexus narrow XLSX ingestion: one real media-plan workbook -> canonical campaign JSON.

Scope is intentionally narrow and read-only. It parses exactly the two frozen input
sheets used by the Nexus parser fixture and does not change agent/compiler/QA/package
logic.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

PLAN_SHEET = "Approved Media Plan"
CREATIVE_SHEET = "Creative Specs"

PLAN_HEADERS = [
    "Client", "Campaign Name", "Campaign Objective", "Market", "Platform", "Currency",
    "Planned Budget", "Flight Start", "Flight End", "Audience Name", "Creative / Asset ID",
    "Ad Format", "Serving Location", "Size", "Landing Page URL", "Plan Row ID", "Buying Method",
    "Operator Notes",
]
CREATIVE_HEADERS = [
    "Creative ID", "Asset Name", "Format", "Ratio", "Width", "Height", "File Type",
    "Destination URL", "Version", "Status",
]


def _stable_id(prefix: str, *parts: Any, length: int = 12) -> str:
    normalized = "\x1f".join("" if p is None else str(p).strip().casefold() for p in parts)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:length].upper()
    return f"{prefix}-{digest}"


def _col_index(cell_ref: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_ref).group(1)
    result = 0
    for char in letters:
        result = result * 26 + (ord(char) - 64)
    return result - 1


def _excel_date(value: Any) -> str:
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    try:
        serial = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected Excel date serial, got {value!r}") from exc
    return (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values = []
    for si in root.findall(f"{{{NS_MAIN}}}si"):
        text = "".join(node.text or "" for node in si.iter(f"{{{NS_MAIN}}}t"))
        values.append(text)
    return values


def _sheet_targets(zf: zipfile.ZipFile) -> dict[str, str]:
    wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
    rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rels = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rel_root.findall(f"{{{NS_PKG_REL}}}Relationship")
    }
    targets = {}
    for sheet in wb_root.findall(f".//{{{NS_MAIN}}}sheet"):
        name = sheet.attrib["name"]
        rid = sheet.attrib[f"{{{NS_REL}}}id"]
        target = rels[rid].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        targets[name] = target
    return targets


def _cell_value(cell: ET.Element, shared: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{NS_MAIN}}}is")
        if inline is None:
            return ""
        return "".join(node.text or "" for node in inline.iter(f"{{{NS_MAIN}}}t"))
    value_node = cell.find(f"{{{NS_MAIN}}}v")
    if value_node is None:
        return None
    raw = value_node.text or ""
    if cell_type == "s":
        return shared[int(raw)]
    if cell_type == "b":
        return raw == "1"
    if cell_type in {"str", "e"}:
        return raw
    try:
        num = float(raw)
        return int(num) if num.is_integer() else num
    except ValueError:
        return raw


def read_sheet(path: str | Path, sheet_name: str) -> list[list[Any]]:
    with zipfile.ZipFile(path) as zf:
        shared = _read_shared_strings(zf)
        targets = _sheet_targets(zf)
        if sheet_name not in targets:
            raise ValueError(f"Missing required sheet: {sheet_name}")
        root = ET.fromstring(zf.read(targets[sheet_name]))
        rows: list[list[Any]] = []
        max_col = -1
        staged: list[dict[int, Any]] = []
        for row in root.findall(f".//{{{NS_MAIN}}}row"):
            values: dict[int, Any] = {}
            for cell in row.findall(f"{{{NS_MAIN}}}c"):
                idx = _col_index(cell.attrib["r"])
                values[idx] = _cell_value(cell, shared)
                max_col = max(max_col, idx)
            staged.append(values)
        width = max_col + 1
        for values in staged:
            rows.append([values.get(i) for i in range(width)])
        return rows


def _records(rows: list[list[Any]], expected_headers: list[str], sheet_name: str) -> list[dict[str, Any]]:
    if not rows:
        raise ValueError(f"Sheet {sheet_name} is empty")
    headers = ["" if v is None else str(v).strip() for v in rows[0][: len(expected_headers)]]
    if headers != expected_headers:
        raise ValueError(f"Unexpected headers in {sheet_name}: {headers!r}")
    output = []
    for excel_row, row in enumerate(rows[1:], start=2):
        values = list(row[: len(expected_headers)]) + [None] * max(0, len(expected_headers) - len(row))
        if all(v in (None, "") for v in values):
            continue
        record = dict(zip(expected_headers, values))
        record["_excel_row"] = excel_row
        output.append(record)
    return output


def canonicalize_xlsx(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    plan_rows = _records(read_sheet(path, PLAN_SHEET), PLAN_HEADERS, PLAN_SHEET)
    creative_rows = _records(read_sheet(path, CREATIVE_SHEET), CREATIVE_HEADERS, CREATIVE_SHEET)
    if not plan_rows:
        raise ValueError("Approved Media Plan contains no data rows")

    campaign_fields = ["Client", "Campaign Name", "Campaign Objective", "Market", "Currency"]
    campaign_values: dict[str, Any] = {}
    for field in campaign_fields:
        unique = {row[field] for row in plan_rows if row[field] not in (None, "")}
        if len(unique) != 1:
            raise ValueError(f"Expected exactly one campaign-level {field}, got {sorted(map(str, unique))}")
        campaign_values[field] = next(iter(unique))

    campaign_key = _stable_id(
        "CMP",
        campaign_values["Client"],
        campaign_values["Campaign Name"],
        campaign_values["Campaign Objective"],
        campaign_values["Market"],
        campaign_values["Currency"],
    )

    source_rows = []
    evidence_by_audience: dict[str, list[str]] = defaultdict(list)
    evidence_by_creative: dict[str, list[str]] = defaultdict(list)
    plan_row_counts: dict[str, int] = defaultdict(int)

    specs_by_id = {str(row["Creative ID"]): row for row in creative_rows}
    if len(specs_by_id) != len(creative_rows):
        raise ValueError("Creative Specs contains duplicate Creative ID values")

    audiences_by_name: dict[str, dict[str, Any]] = {}
    creatives_by_id: dict[str, dict[str, Any]] = {}
    activations = []
    validation_issues = []

    for row in plan_rows:
        source_ref = f"{PLAN_SHEET}!{row['_excel_row']}"
        plan_row_id = str(row["Plan Row ID"]).strip()
        audience_name = str(row["Audience Name"]).strip()
        creative_id = str(row["Creative / Asset ID"]).strip()
        platform = str(row["Platform"]).strip()
        flight_start = _excel_date(row["Flight Start"])
        flight_end = _excel_date(row["Flight End"])

        source_values = {k: row[k] for k in PLAN_HEADERS}
        source_values["Flight Start"] = flight_start
        source_values["Flight End"] = flight_end
        source_rows.append({"source_ref": source_ref, "sheet": PLAN_SHEET, "excel_row": row["_excel_row"], "values": source_values})
        plan_row_counts[plan_row_id] += 1

        audience_row_id = _stable_id("AUD", campaign_key, audience_name)
        evidence_by_audience[audience_name].append(source_ref)
        audiences_by_name.setdefault(
            audience_name,
            {"audience_row_id": audience_row_id, "audience_name": audience_name, "source_evidence": []},
        )

        spec = specs_by_id.get(creative_id)
        if spec is None:
            raise ValueError(f"Creative {creative_id} from {source_ref} not found in Creative Specs")
        creative_row_id = _stable_id("CRE", campaign_key, creative_id)
        evidence_by_creative[creative_id].append(source_ref)
        spec_size = f"{spec['Width']}x{spec['Height']}"
        plan_size = str(row["Size"]).strip()
        if spec_size != plan_size:
            validation_issues.append({
                "type": "CREATIVE_SIZE_MISMATCH",
                "creative_id": creative_id,
                "source_ref": source_ref,
                "plan_size": plan_size,
                "spec_size": spec_size,
            })
        if str(spec["Format"]).strip() != str(row["Ad Format"]).strip():
            validation_issues.append({
                "type": "CREATIVE_FORMAT_MISMATCH",
                "creative_id": creative_id,
                "source_ref": source_ref,
                "plan_format": row["Ad Format"],
                "spec_format": spec["Format"],
            })
        if str(spec["Destination URL"]).strip() != str(row["Landing Page URL"]).strip():
            validation_issues.append({
                "type": "CREATIVE_DESTINATION_MISMATCH",
                "creative_id": creative_id,
                "source_ref": source_ref,
                "plan_url": row["Landing Page URL"],
                "spec_url": spec["Destination URL"],
            })

        creatives_by_id.setdefault(
            creative_id,
            {
                "creative_row_id": creative_row_id,
                "creative_id": creative_id,
                "ad_format": str(spec["Format"]).strip(),
                "size": spec_size,
                "ratio": str(spec["Ratio"]).strip(),
                "asset_name": spec["Asset Name"],
                "file_type": spec["File Type"],
                "destination_url": spec["Destination URL"],
                "version": spec["Version"],
                "status": spec["Status"],
                "source_evidence": [],
            },
        )

        activation_id = _stable_id(
            "ACT",
            campaign_key,
            plan_row_id,
            audience_name,
            creative_id,
            platform,
            flight_start,
            flight_end,
        )
        activations.append({
            "activation_id": activation_id,
            "plan_row_id": plan_row_id,
            "audience_row_id": audience_row_id,
            "creative_row_id": creative_row_id,
            "source_ref": source_ref,
            "platform": platform,
            "flight_start": flight_start,
            "flight_end": flight_end,
            "planned_budget": row["Planned Budget"],
            "buying_method": row["Buying Method"],
            "serving_location": row["Serving Location"],
            "size": plan_size,
            "landing_page_url": row["Landing Page URL"],
            "operator_notes": row["Operator Notes"],
        })

    for audience_name, entity in audiences_by_name.items():
        entity["source_evidence"] = evidence_by_audience[audience_name]
    for creative_id, entity in creatives_by_id.items():
        entity["source_evidence"] = evidence_by_creative[creative_id] + [
            f"{CREATIVE_SHEET}!{specs_by_id[creative_id]['_excel_row']}"
        ]

    platform_values = sorted({str(row["Platform"]).strip() for row in plan_rows})
    flight_pairs = sorted({(_excel_date(row["Flight Start"]), _excel_date(row["Flight End"])) for row in plan_rows})
    all_starts = [pair[0] for pair in flight_pairs]
    all_ends = [pair[1] for pair in flight_pairs]
    ambiguities = []
    if len(platform_values) > 1:
        ambiguities.append({
            "field": "campaign.platform",
            "reason": "MULTIPLE_SOURCE_VALUES",
            "candidates": platform_values,
            "resolution_required": True,
        })
    if len(flight_pairs) > 1:
        ambiguities.append({
            "field": "campaign.flight",
            "reason": "MULTIPLE_SOURCE_VALUES",
            "candidates": [{"flight_start": a, "flight_end": b} for a, b in flight_pairs],
            "resolution_required": True,
        })

    canonical_status = "NEEDS_CONFIRMATION" if ambiguities or validation_issues else "READY"
    campaign = {
        "campaign_key": campaign_key,
        "client": campaign_values["Client"],
        "campaign_name": campaign_values["Campaign Name"],
        "objective": campaign_values["Campaign Objective"],
        "market": campaign_values["Market"],
        "currency": campaign_values["Currency"],
        "platform": platform_values[0] if len(platform_values) == 1 else None,
        "flight_start": min(all_starts),
        "flight_end": max(all_ends),
        "flight_scope": "exact" if len(flight_pairs) == 1 else "source_envelope_only",
        "source_evidence": [item["source_ref"] for item in source_rows],
    }

    return {
        "schema": "nexus-canonical-campaign-v0",
        "canonical_status": canonical_status,
        "source": {
            "filename": path.name,
            "sheets": [PLAN_SHEET, CREATIVE_SHEET],
            "read_only": True,
        },
        "counts": {
            "source_rows": len(source_rows),
            "campaigns": 1,
            "audiences": len(audiences_by_name),
            "creatives": len(creatives_by_id),
            "activations": len(activations),
        },
        "campaign": campaign,
        "audiences": sorted(audiences_by_name.values(), key=lambda x: x["audience_row_id"]),
        "creatives": sorted(creatives_by_id.values(), key=lambda x: x["creative_row_id"]),
        "activations": sorted(activations, key=lambda x: x["source_ref"]),
        "source_rows": source_rows,
        "relationships": {
            "plan_row_activation_counts": dict(sorted(plan_row_counts.items())),
            "one_to_many_plan_rows": sorted([key for key, count in plan_row_counts.items() if count > 1]),
        },
        "ambiguities": ambiguities,
        "validation_issues": validation_issues,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Usage: {Path(argv[0]).name} <media-plan.xlsx>", file=sys.stderr)
        return 2
    payload = canonicalize_xlsx(argv[1])
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
