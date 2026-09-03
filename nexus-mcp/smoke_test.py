#!/usr/bin/env python3
import copy
import csv
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

EXPECTED=["inspect_campaign","resolve_mapping","request_compile","run_qa","prepare_package"]
EXPECTED_COLUMNS=[
    "Campaign_Key","Plan_Row_ID","Platform","Campaign_Name","Placement_Name","Ad_Format","Flight_Dates",
    "Audience_Targeting","Creative_ID","Landing_Page_URL","Final_Tracking_URL","Activation_ID","Audience_Row_ID","Creative_Row_ID"
]
server=Path(__file__).with_name("server.py")
p=subprocess.Popen([sys.executable,str(server)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)

def rpc(payload,expect_response=True):
    p.stdin.write(json.dumps(payload)+"\n")
    p.stdin.flush()
    if not expect_response:
        return None
    line=p.stdout.readline()
    if not line:
        raise RuntimeError("MCP server closed unexpectedly")
    return json.loads(line)

init=rpc({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"nexus-smoke-test","version":"0.0.1"}}})
assert init["result"]["capabilities"]=={"tools":{"listChanged":False}}
rpc({"jsonrpc":"2.0","method":"notifications/initialized","params":{}},expect_response=False)
listed=rpc({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
names=[tool["name"] for tool in listed["result"]["tools"]]
assert names==EXPECTED,f"Expected {EXPECTED}, got {names}"
assert len(names)==5

called=rpc({"jsonrpc":"2.0","id":10,"method":"tools/call","params":{"name":"inspect_campaign","arguments":{"run_id":"fixture-agentic-v0"}}})
inspect=called["result"]["structuredContent"]
assert inspect["stub"] is False
assert inspect["status"]=="OK"
assert inspect["read_only"] is True
assert inspect["counts"]=={"source_rows":6,"campaigns":1,"audiences":2,"creatives":4,"activations":6}

called=rpc({"jsonrpc":"2.0","id":11,"method":"tools/call","params":{"name":"resolve_mapping","arguments":{"run_id":"fixture-agentic-v0","mapping_id":"MAP-AUD-001","candidate_id":"candidate-a"}}})
resolved=called["result"]["structuredContent"]
assert called["result"]["isError"] is False
assert resolved["stub"] is False
assert resolved["status"]=="RESOLVED"
assert resolved["selected_candidate"]["candidate_id"]=="candidate-a"
assert resolved["selected_candidate"]["value"]=="AUD-001"
assert resolved["allowed_candidate_ids"]==["candidate-a","candidate-b"]

called=rpc({"jsonrpc":"2.0","id":12,"method":"tools/call","params":{"name":"resolve_mapping","arguments":{"run_id":"fixture-agentic-v0","mapping_id":"MAP-AUD-001","candidate_id":"candidate-c"}}})
rejected=called["result"]["structuredContent"]
assert called["result"]["isError"] is True
assert rejected["status"]=="REJECTED"
assert rejected["allowed_candidate_ids"]==["candidate-a","candidate-b"]
assert "selected_candidate" not in rejected

first=rpc({"jsonrpc":"2.0","id":13,"method":"tools/call","params":{"name":"request_compile","arguments":{"run_id":"fixture-agentic-v0"}}})["result"]["structuredContent"]
second=rpc({"jsonrpc":"2.0","id":14,"method":"tools/call","params":{"name":"request_compile","arguments":{"run_id":"fixture-agentic-v0"}}})["result"]["structuredContent"]
assert first==second
assert first["stub"] is False
assert first["status"]=="COMPILED_PREVIEW"
assert first["read_only"] is True
assert first["in_memory"] is True
assert first["writes_files"] is False
assert first["counts"]=={"build_rows":6}
assert first["stable_ids"]=={
    "campaign_key":"CMP-NORTHSTAR-Q4-ENT-001",
    "activation_ids":["ACT-001","ACT-002","ACT-003","ACT-004","ACT-005","ACT-006"],
    "build_row_ids":["BLD-ACT-001","BLD-ACT-002","BLD-ACT-003","BLD-ACT-004","BLD-ACT-005","BLD-ACT-006"]
}
assert [row["plan_row_id"] for row in first["build_rows"]].count("PLAN-001")==2
assert first["build_rows"][-1]["size"]=="1920x1920"

qa_call=rpc({"jsonrpc":"2.0","id":15,"method":"tools/call","params":{"name":"run_qa","arguments":{"run_id":"fixture-agentic-v0"}}})
qa=qa_call["result"]["structuredContent"]
assert qa_call["result"]["isError"] is False
assert qa["stub"] is False
assert qa["status"]=="PASS"
assert qa["fail_closed"] is True
assert qa["override_allowed"] is False
assert qa["counts"]=={"checks_executed":1,"failures":0,"blocking_failures":0}
assert qa["failures"]==[]

package_call=rpc({"jsonrpc":"2.0","id":16,"method":"tools/call","params":{"name":"prepare_package","arguments":{"run_id":"fixture-agentic-v0"}}})
package=package_call["result"]["structuredContent"]
assert package_call["result"]["isError"] is False
assert package["stub"] is False
assert package["status"]=="READY_FOR_APPROVAL"
assert package["qa_status"]=="PASS"
assert package["package_created"] is True
assert package["in_memory"] is True
assert package["writes_files"] is False
assert package["publishes"] is False
artifact=package["artifact"]
assert artifact["filename"]=="nexus_trafficking.csv"
assert artifact["media_type"]=="text/csv"
assert artifact["columns"]==EXPECTED_COLUMNS
assert artifact["row_count"]==6
reader=csv.DictReader(io.StringIO(artifact["content"]))
assert reader.fieldnames==EXPECTED_COLUMNS
rows=list(reader)
assert len(rows)==6
assert rows[0]["Activation_ID"]=="ACT-001"
assert rows[-1]["Activation_ID"]=="ACT-006"
assert rows[-1]["Creative_Row_ID"]=="CRT-004"

p.terminate()
p.wait(timeout=5)

# Exercise the non-PASS gate without changing the frozen repository fixture.
spec=importlib.util.spec_from_file_location("nexus_server_gate_test", server)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
bad_fixture=copy.deepcopy(module.load_canonical_fixture())
for creative in bad_fixture["creatives"]:
    if creative["creative_row_id"]=="CRT-004":
        creative["size"]="1920x1080"
module.load_canonical_fixture=lambda: copy.deepcopy(bad_fixture)
blocked=module.prepare_package({"run_id":"fixture-agentic-v0"})["structuredContent"]
assert blocked["status"]=="BLOCKED"
assert blocked["qa_status"]=="BLOCKED"
assert blocked["package_created"] is False
assert blocked["writes_files"] is False
assert blocked["publishes"] is False
assert "artifact" not in blocked

print("PASS: MCP discovery surface is exactly 5/5 tools")
print("PASS: compile remains 6 stable in-memory rows and corrected QA remains PASS")
print("PASS: prepare_package returns READY_FOR_APPROVAL only after QA PASS")
print("PASS: nexus_trafficking.csv is in memory with exactly 14 frozen columns and 6 rows")
print("PASS: non-PASS QA refuses package generation and returns no artifact")
