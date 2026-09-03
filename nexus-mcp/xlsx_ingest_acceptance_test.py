#!/usr/bin/env python3
import hashlib
from pathlib import Path

from xlsx_ingest import canonicalize_xlsx

HERE = Path(__file__).resolve().parent
WORKBOOK = HERE / "fixtures" / "Nexus_Parser_Test_Media_Plan.xlsx"

before = hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
first = canonicalize_xlsx(WORKBOOK)
second = canonicalize_xlsx(WORKBOOK)
after = hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()

assert before == after, "Parser modified the source XLSX"
assert first == second, "Canonicalization is not deterministic across identical runs"
assert first["source"]["read_only"] is True
assert first["counts"] == {
    "source_rows": 6,
    "campaigns": 1,
    "audiences": 5,
    "creatives": 6,
    "activations": 6,
}
assert first["relationships"]["plan_row_activation_counts"] == {
    "PLAN-001": 2,
    "PLAN-002": 1,
    "PLAN-003": 1,
    "PLAN-004": 1,
    "PLAN-005": 1,
}
assert first["relationships"]["one_to_many_plan_rows"] == ["PLAN-001"]
plan1 = [a for a in first["activations"] if a["plan_row_id"] == "PLAN-001"]
assert len(plan1) == 2
assert len({a["activation_id"] for a in plan1}) == 2
assert len({a["creative_row_id"] for a in plan1}) == 2
assert {a["source_ref"] for a in plan1} == {"Approved Media Plan!2", "Approved Media Plan!3"}
assert len(first["source_rows"]) == 6
assert [r["source_ref"] for r in first["source_rows"]] == [
    "Approved Media Plan!2", "Approved Media Plan!3", "Approved Media Plan!4",
    "Approved Media Plan!5", "Approved Media Plan!6", "Approved Media Plan!7",
]
assert first["validation_issues"] == []
assert first["canonical_status"] == "NEEDS_CONFIRMATION"
platform_ambiguity = next(x for x in first["ambiguities"] if x["field"] == "campaign.platform")
assert platform_ambiguity["candidates"] == ["CM360", "DV360"]
flight_ambiguity = next(x for x in first["ambiguities"] if x["field"] == "campaign.flight")
assert len(flight_ambiguity["candidates"]) == 4
assert first["campaign"]["platform"] is None
assert first["campaign"]["flight_scope"] == "source_envelope_only"
assert first["campaign"]["flight_start"] == "2026-10-01"
assert first["campaign"]["flight_end"] == "2026-11-15"
assert len({a["activation_id"] for a in first["activations"]}) == 6
assert len({a["creative_row_id"] for a in first["creatives"]}) == 6
assert len({a["audience_row_id"] for a in first["audiences"]}) == 5

print("PASS: real XLSX parsed read-only into canonical Campaign/Audience/Creative/Activation JSON")
print("PASS: 6 source rows -> 1 campaign / 5 audiences / 6 creatives / 6 activations")
print("PASS: PLAN-001 preserved as 1:N with two distinct activation and creative identities")
print("PASS: every source row retained with exact sheet/Excel-row evidence")
print("PASS: stable IDs and complete canonical JSON identical across repeat parse")
print("PASS: mixed platform and flight values surfaced as NEEDS_CONFIRMATION, not invented")
