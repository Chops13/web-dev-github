#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

EXPECTED=["inspect_campaign","resolve_mapping","request_compile","run_qa","prepare_package"]
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
assert first["build_rows"][0]["creative_id"]=="NS-Q4-300X250-A"
assert first["build_rows"][-1]["creative_id"]=="NS-Q4-1920X1080-A"

qa_call=rpc({"jsonrpc":"2.0","id":15,"method":"tools/call","params":{"name":"run_qa","arguments":{"run_id":"fixture-agentic-v0"}}})
qa=qa_call["result"]["structuredContent"]
assert qa_call["result"]["isError"] is True
assert qa["stub"] is False
assert qa["status"]=="BLOCKED"
assert qa["fail_closed"] is True
assert qa["override_allowed"] is False
assert qa["counts"]=={"checks_executed":1,"failures":1,"blocking_failures":1}
assert qa["failures"][0]["check_id"]=="QA-CREATIVE-SIZE-001"
assert qa["failures"][0]["creative_row_id"]=="CRT-004"
assert qa["failures"][0]["expected"]=="1920x1920"
assert qa["failures"][0]["actual"]==["1920x1080"]
assert qa["failures"][0]["affected_build_row_ids"]==["BLD-ACT-006"]

override_call=rpc({"jsonrpc":"2.0","id":16,"method":"tools/call","params":{"name":"run_qa","arguments":{"run_id":"fixture-agentic-v0","override":True}}})
override=override_call["result"]["structuredContent"]
assert override_call["result"]["isError"] is True
assert override["status"]=="REJECTED_ARGUMENTS"
assert override["rejected_arguments"]==["override"]
assert override["override_allowed"] is False

package_call=rpc({"jsonrpc":"2.0","id":17,"method":"tools/call","params":{"name":"prepare_package","arguments":{"run_id":"fixture-agentic-v0"}}})
assert package_call["result"]["structuredContent"]["stub"] is True
assert package_call["result"]["structuredContent"]["tool"]=="prepare_package"

print("PASS: MCP discovery surface is exactly 5/5 tools")
print("PASS: inspect_campaign returns frozen read-only counts 6/1/2/4/6")
print("PASS: resolve_mapping remains constrained to the frozen 2-candidate set")
print("PASS: request_compile deterministically returns 6 in-memory build rows")
print("PASS: run_qa returns BLOCKED on QA-CREATIVE-SIZE-001 for CRT-004")
print("PASS: run_qa rejects override=true and remains fail-closed")
print("PASS: prepare_package remains stubbed")
p.terminate()
p.wait(timeout=5)
