#!/usr/bin/env python3
import copy
import csv
import importlib.util
import io
from pathlib import Path

SERVER = Path(__file__).with_name("server.py")
EXPECTED_COLUMNS = [
    "Campaign_Key",
    "Plan_Row_ID",
    "Platform",
    "Campaign_Name",
    "Placement_Name",
    "Ad_Format",
    "Flight_Dates",
    "Audience_Targeting",
    "Creative_ID",
    "Landing_Page_URL",
    "Final_Tracking_URL",
    "Activation_ID",
    "Audience_Row_ID",
    "Creative_Row_ID",
]
EXPECTED_ACTIVATION_IDS = [f"ACT-{i:03d}" for i in range(1, 7)]
EXPECTED_BUILD_ROW_IDS = [f"BLD-ACT-{i:03d}" for i in range(1, 7)]

spec = importlib.util.spec_from_file_location("nexus_server_e2e", SERVER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

corrected_fixture = copy.deepcopy(module.load_canonical_fixture())
bad_fixture = copy.deepcopy(corrected_fixture)

bad_creative = next(item for item in bad_fixture["creatives"] if item["creative_row_id"] == "CRT-004")
corrected_creative = next(item for item in corrected_fixture["creatives"] if item["creative_row_id"] == "CRT-004")
assert corrected_creative["size"] == "1920x1920"
bad_creative["size"] = "1920x1080"

# Prove the two fixture states differ by one value only.
comparison = copy.deepcopy(corrected_fixture)
next(item for item in comparison["creatives"] if item["creative_row_id"] == "CRT-004")["size"] = "1920x1080"
assert comparison == bad_fixture

# Run 1: original bad value must fail closed and emit no CSV artifact.
module.load_canonical_fixture = lambda: copy.deepcopy(bad_fixture)
bad_compile = module.request_compile({"run_id": "fixture-agentic-v0"})["structuredContent"]
bad_qa = module.run_qa({"run_id": "fixture-agentic-v0"})["structuredContent"]
bad_package = module.prepare_package({"run_id": "fixture-agentic-v0"})["structuredContent"]

assert bad_compile["status"] == "COMPILED_PREVIEW"
assert bad_compile["counts"] == {"build_rows": 6}
assert bad_compile["stable_ids"]["activation_ids"] == EXPECTED_ACTIVATION_IDS
assert bad_compile["stable_ids"]["build_row_ids"] == EXPECTED_BUILD_ROW_IDS
assert bad_compile["build_rows"][-1]["size"] == "1920x1080"
assert bad_qa["status"] == "BLOCKED"
assert bad_qa["counts"] == {"checks_executed": 1, "failures": 1, "blocking_failures": 1}
assert bad_qa["failures"][0]["creative_row_id"] == "CRT-004"
assert bad_package["status"] == "BLOCKED"
assert bad_package["package_created"] is False
assert "artifact" not in bad_package

# Run 2: correct only CRT-004.size; all identities must remain stable and package must pass.
module.load_canonical_fixture = lambda: copy.deepcopy(corrected_fixture)
good_compile = module.request_compile({"run_id": "fixture-agentic-v0"})["structuredContent"]
good_qa = module.run_qa({"run_id": "fixture-agentic-v0"})["structuredContent"]
good_package = module.prepare_package({"run_id": "fixture-agentic-v0"})["structuredContent"]

assert good_compile["status"] == "COMPILED_PREVIEW"
assert good_compile["counts"] == {"build_rows": 6}
assert good_compile["stable_ids"] == bad_compile["stable_ids"]
assert good_compile["stable_ids"]["activation_ids"] == EXPECTED_ACTIVATION_IDS
assert good_compile["stable_ids"]["build_row_ids"] == EXPECTED_BUILD_ROW_IDS
assert good_compile["build_rows"][-1]["size"] == "1920x1920"
assert good_qa["status"] == "PASS"
assert good_qa["counts"] == {"checks_executed": 1, "failures": 0, "blocking_failures": 0}
assert good_package["status"] == "READY_FOR_APPROVAL"
assert good_package["qa_status"] == "PASS"
assert good_package["package_created"] is True
assert good_package["in_memory"] is True
assert good_package["writes_files"] is False
assert good_package["publishes"] is False

artifact = good_package["artifact"]
assert artifact["filename"] == "nexus_trafficking.csv"
assert artifact["columns"] == EXPECTED_COLUMNS
assert artifact["row_count"] == 6
reader = csv.DictReader(io.StringIO(artifact["content"]))
assert reader.fieldnames == EXPECTED_COLUMNS
rows = list(reader)
assert len(rows) == 6
assert [row["Activation_ID"] for row in rows] == EXPECTED_ACTIVATION_IDS
assert not Path("nexus_trafficking.csv").exists()

print("PASS: run 1 original CRT-004 1920x1080 -> BLOCKED")
print("PASS: run 1 produced no nexus_trafficking.csv artifact")
print("PASS: corrected only CRT-004.size -> 1920x1920")
print("PASS: all six activation/build IDs unchanged across runs")
print("PASS: run 2 deterministic QA -> PASS")
print("PASS: run 2 -> READY_FOR_APPROVAL")
print("PASS: nexus_trafficking.csv is in memory with exactly 14 frozen columns and 6 rows")
