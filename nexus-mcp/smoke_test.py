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

for i,name in enumerate(EXPECTED[2:],start=13):
    called=rpc({"jsonrpc":"2.0","id":i,"method":"tools/call","params":{"name":name,"arguments":{"run_id":"demo-run"}}})
    assert called["result"]["structuredContent"]["stub"] is True
    assert called["result"]["structuredContent"]["tool"]==name
print("PASS: MCP discovery surface is exactly 5/5 tools")
print("PASS: inspect_campaign returns frozen read-only counts 6/1/2/4/6")
print("PASS: resolve_mapping accepts candidate-a from the 2-candidate frozen set")
print("PASS: resolve_mapping rejects invented candidate-c and selects no value")
print("PASS: remaining 3 tools still return stub JSON")
p.terminate()
p.wait(timeout=5)
