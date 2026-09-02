#!/usr/bin/env python3
import json
import sys

SERVER_NAME = "nexus-agentic-compile"
SERVER_VERSION = "0.0.1"
PROTOCOL_VERSION = "2025-06-18"

TOOLS = [
    {"name":"inspect_campaign","description":"Read the canonical Nexus Campaign, Audience, Creative, and Activation entities for one run. Read-only stub.","inputSchema":{"type":"object","properties":{"run_id":{"type":"string","minLength":1}},"required":["run_id"],"additionalProperties":False}},
    {"name":"resolve_mapping","description":"Select one deterministic candidate for an already-surfaced mapping ambiguity. Stub only; cannot invent source values.","inputSchema":{"type":"object","properties":{"run_id":{"type":"string","minLength":1},"mapping_id":{"type":"string","minLength":1},"candidate_id":{"type":"string","minLength":1}},"required":["run_id","mapping_id","candidate_id"],"additionalProperties":False}},
    {"name":"request_compile","description":"Request deterministic Nexus compilation for a run. Stub only; no compiler logic is executed.","inputSchema":{"type":"object","properties":{"run_id":{"type":"string","minLength":1}},"required":["run_id"],"additionalProperties":False}},
    {"name":"run_qa","description":"Request deterministic Nexus QA for a run. Stub only; no QA logic is executed.","inputSchema":{"type":"object","properties":{"run_id":{"type":"string","minLength":1}},"required":["run_id"],"additionalProperties":False}},
    {"name":"prepare_package","description":"Prepare final Nexus run artefacts after deterministic QA PASS. Stub only; creates nothing and publishes nowhere.","inputSchema":{"type":"object","properties":{"run_id":{"type":"string","minLength":1}},"required":["run_id"],"additionalProperties":False}}
]

TOOL_NAMES = {tool["name"] for tool in TOOLS}

def send(payload):
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()

def result(req_id, value):
    send({"jsonrpc":"2.0","id":req_id,"result":value})

def error(req_id, code, message):
    send({"jsonrpc":"2.0","id":req_id,"error":{"code":code,"message":message}})

def stub_call(name, arguments):
    payload={"stub":True,"tool":name,"status":"STUB","run_id":arguments.get("run_id"),"message":"Nexus MCP skeleton only. No compiler logic executed."}
    if name=="resolve_mapping":
        payload.update({"mapping_id":arguments.get("mapping_id"),"candidate_id":arguments.get("candidate_id")})
    return {"content":[{"type":"text","text":json.dumps(payload,separators=(",",":"))}],"structuredContent":payload,"isError":False}

def handle(msg):
    method=msg.get("method")
    req_id=msg.get("id")
    if method=="initialize":
        requested=(msg.get("params") or {}).get("protocolVersion")
        result(req_id,{"protocolVersion":requested or PROTOCOL_VERSION,"capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":SERVER_NAME,"version":SERVER_VERSION}})
        return
    if method=="notifications/initialized":
        return
    if method=="ping":
        result(req_id,{})
        return
    if method=="tools/list":
        result(req_id,{"tools":TOOLS})
        return
    if method=="tools/call":
        params=msg.get("params") or {}
        name=params.get("name")
        args=params.get("arguments") or {}
        if name not in TOOL_NAMES:
            error(req_id,-32602,f"Unknown tool: {name}")
            return
        result(req_id,stub_call(name,args))
        return
    if req_id is not None:
        error(req_id,-32601,f"Method not found: {method}")

def main():
    for raw in sys.stdin:
        raw=raw.strip()
        if not raw:
            continue
        try:
            handle(json.loads(raw))
        except Exception as exc:
            send({"jsonrpc":"2.0","id":None,"error":{"code":-32603,"message":str(exc)}})

if __name__=="__main__":
    main()
