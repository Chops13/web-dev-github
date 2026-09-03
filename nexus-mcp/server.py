#!/usr/bin/env python3
import json
import sys
from pathlib import Path

SERVER_NAME = "nexus-agentic-compile"
SERVER_VERSION = "0.0.5"
PROTOCOL_VERSION = "2025-06-18"
FIXTURE_PATH = Path(__file__).with_name("canonical_fixture.json")
MAPPING_FIXTURE_PATH = Path(__file__).with_name("mapping_fixture.json")
QA_FIXTURE_PATH = Path(__file__).with_name("qa_fixture.json")

TOOLS = [
    {"name":"inspect_campaign","description":"Read the frozen canonical Nexus Campaign, Audience, Creative, and Activation entities for one fixture run. Read-only.","inputSchema":{"type":"object","properties":{"run_id":{"type":"string","minLength":1}},"required":["run_id"],"additionalProperties":False}},
    {"name":"resolve_mapping","description":"Select exactly one candidate from one frozen deterministic mapping ambiguity. Rejects values not present in the candidate set.","inputSchema":{"type":"object","properties":{"run_id":{"type":"string","minLength":1},"mapping_id":{"type":"string","minLength":1},"candidate_id":{"type":"string","minLength":1}},"required":["run_id","mapping_id","candidate_id"],"additionalProperties":False}},
    {"name":"request_compile","description":"Produce a deterministic in-memory compile preview for the frozen canonical fixture. Creates stable build rows only; writes no files.","inputSchema":{"type":"object","properties":{"run_id":{"type":"string","minLength":1}},"required":["run_id"],"additionalProperties":False}},
    {"name":"run_qa","description":"Run deterministic fail-closed QA over the frozen compiled preview. Returns BLOCKED on any blocking failure and accepts no override arguments.","inputSchema":{"type":"object","properties":{"run_id":{"type":"string","minLength":1}},"required":["run_id"],"additionalProperties":False}},
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

def tool_result(payload, is_error=False):
    return {"content":[{"type":"text","text":json.dumps(payload,separators=(",",":"))}],"structuredContent":payload,"isError":is_error}

def stub_call(name, arguments):
    payload={"stub":True,"tool":name,"status":"STUB","run_id":arguments.get("run_id"),"message":"Nexus MCP skeleton only. This tool remains intentionally stubbed."}
    return tool_result(payload)

def load_canonical_fixture():
    with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)

def inspect_campaign(arguments):
    fixture = load_canonical_fixture()
    requested_run_id = arguments.get("run_id")
    if requested_run_id != fixture["run_id"]:
        payload={
            "stub":False,
            "tool":"inspect_campaign",
            "status":"NOT_FOUND",
            "run_id":requested_run_id,
            "fixture_id":fixture["fixture_id"],
            "message":"inspect_campaign is currently frozen to one canonical fixture run."
        }
        return tool_result(payload, True)
    payload={
        "stub":False,
        "tool":"inspect_campaign",
        "status":"OK",
        "read_only":True,
        "fixture_id":fixture["fixture_id"],
        "run_id":fixture["run_id"],
        "counts":{
            "source_rows":fixture["source_row_count"],
            "campaigns":1,
            "audiences":len(fixture["audiences"]),
            "creatives":len(fixture["creatives"]),
            "activations":len(fixture["activations"])
        },
        "campaign":fixture["campaign"],
        "audiences":fixture["audiences"],
        "creatives":fixture["creatives"],
        "activations":fixture["activations"]
    }
    return tool_result(payload)

def resolve_mapping(arguments):
    with MAPPING_FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        fixture = json.load(handle)
    requested_run_id = arguments.get("run_id")
    requested_mapping_id = arguments.get("mapping_id")
    requested_candidate_id = arguments.get("candidate_id")
    if requested_run_id != fixture["run_id"] or requested_mapping_id != fixture["mapping_id"]:
        payload={
            "stub":False,
            "tool":"resolve_mapping",
            "status":"NOT_FOUND",
            "run_id":requested_run_id,
            "mapping_id":requested_mapping_id,
            "fixture_id":fixture["fixture_id"],
            "message":"resolve_mapping is currently frozen to one deterministic ambiguity."
        }
        return tool_result(payload, True)
    candidates = fixture["candidates"]
    selected = next((candidate for candidate in candidates if candidate["candidate_id"] == requested_candidate_id), None)
    if selected is None:
        payload={
            "stub":False,
            "tool":"resolve_mapping",
            "status":"REJECTED",
            "run_id":fixture["run_id"],
            "mapping_id":fixture["mapping_id"],
            "candidate_id":requested_candidate_id,
            "allowed_candidate_ids":[candidate["candidate_id"] for candidate in candidates],
            "message":"Candidate is not in the frozen deterministic candidate set; no value was selected."
        }
        return tool_result(payload, True)
    payload={
        "stub":False,
        "tool":"resolve_mapping",
        "status":"RESOLVED",
        "run_id":fixture["run_id"],
        "mapping_id":fixture["mapping_id"],
        "source":fixture["ambiguity"],
        "selected_candidate":selected,
        "allowed_candidate_ids":[candidate["candidate_id"] for candidate in candidates]
    }
    return tool_result(payload)

def request_compile(arguments):
    fixture = load_canonical_fixture()
    requested_run_id = arguments.get("run_id")
    if requested_run_id != fixture["run_id"]:
        payload={
            "stub":False,
            "tool":"request_compile",
            "status":"NOT_FOUND",
            "run_id":requested_run_id,
            "fixture_id":fixture["fixture_id"],
            "message":"request_compile is currently frozen to one canonical fixture run."
        }
        return tool_result(payload, True)

    campaign = fixture["campaign"]
    audiences = {item["audience_row_id"]: item for item in fixture["audiences"]}
    creatives = {item["creative_row_id"]: item for item in fixture["creatives"]}
    build_rows = []

    for activation in fixture["activations"]:
        audience = audiences[activation["audience_row_id"]]
        creative = creatives[activation["creative_row_id"]]
        build_rows.append({
            "build_row_id":f"BLD-{activation['activation_id']}",
            "campaign_key":campaign["campaign_key"],
            "plan_row_id":activation["plan_row_id"],
            "platform":campaign["platform"],
            "campaign_name":campaign["campaign_name"],
            "flight_start":campaign["flight_start"],
            "flight_end":campaign["flight_end"],
            "activation_id":activation["activation_id"],
            "audience_row_id":activation["audience_row_id"],
            "audience_name":audience["audience_name"],
            "creative_row_id":activation["creative_row_id"],
            "creative_id":creative["creative_id"],
            "ad_format":creative["ad_format"],
            "size":creative["size"]
        })

    payload={
        "stub":False,
        "tool":"request_compile",
        "status":"COMPILED_PREVIEW",
        "read_only":True,
        "in_memory":True,
        "writes_files":False,
        "fixture_id":fixture["fixture_id"],
        "run_id":fixture["run_id"],
        "counts":{"build_rows":len(build_rows)},
        "stable_ids":{
            "campaign_key":campaign["campaign_key"],
            "activation_ids":[row["activation_id"] for row in build_rows],
            "build_row_ids":[row["build_row_id"] for row in build_rows]
        },
        "build_rows":build_rows
    }
    return tool_result(payload)

def run_qa(arguments):
    allowed_keys = {"run_id"}
    extra_keys = sorted(set(arguments) - allowed_keys)
    if extra_keys:
        payload={
            "stub":False,
            "tool":"run_qa",
            "status":"REJECTED_ARGUMENTS",
            "run_id":arguments.get("run_id"),
            "rejected_arguments":extra_keys,
            "override_allowed":False,
            "message":"run_qa accepts only run_id; QA status cannot be overridden by the agent."
        }
        return tool_result(payload, True)

    with QA_FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        qa_fixture = json.load(handle)
    requested_run_id = arguments.get("run_id")
    if requested_run_id != qa_fixture["run_id"]:
        payload={
            "stub":False,
            "tool":"run_qa",
            "status":"NOT_FOUND",
            "run_id":requested_run_id,
            "fixture_id":qa_fixture["fixture_id"],
            "message":"run_qa is currently frozen to one canonical fixture run."
        }
        return tool_result(payload, True)

    compiled = request_compile({"run_id": requested_run_id})["structuredContent"]
    rows_by_creative = {}
    for row in compiled["build_rows"]:
        rows_by_creative.setdefault(row["creative_row_id"], []).append(row)

    failures = []
    checks_executed = []
    for check in qa_fixture["checks"]:
        matches = rows_by_creative.get(check["creative_row_id"], [])
        actual_values = sorted({row.get(check["field"]) for row in matches})
        passed = len(matches) > 0 and actual_values == [check["expected"]]
        checks_executed.append({
            "check_id":check["check_id"],
            "severity":check["severity"],
            "passed":passed
        })
        if not passed:
            failures.append({
                "check_id":check["check_id"],
                "severity":check["severity"],
                "entity_type":check["entity_type"],
                "creative_row_id":check["creative_row_id"],
                "field":check["field"],
                "expected":check["expected"],
                "actual":actual_values,
                "affected_build_row_ids":[row["build_row_id"] for row in matches],
                "message":check["message"]
            })

    blocking_failures = [item for item in failures if item["severity"] == "BLOCKING"]
    status = "BLOCKED" if blocking_failures else "PASS"
    payload={
        "stub":False,
        "tool":"run_qa",
        "status":status,
        "fail_closed":True,
        "override_allowed":False,
        "run_id":requested_run_id,
        "fixture_id":qa_fixture["fixture_id"],
        "compiled_preview_status":compiled["status"],
        "counts":{
            "checks_executed":len(checks_executed),
            "failures":len(failures),
            "blocking_failures":len(blocking_failures)
        },
        "checks":checks_executed,
        "failures":failures
    }
    return tool_result(payload, bool(blocking_failures))

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
        if name=="inspect_campaign":
            result(req_id,inspect_campaign(args))
        elif name=="resolve_mapping":
            result(req_id,resolve_mapping(args))
        elif name=="request_compile":
            result(req_id,request_compile(args))
        elif name=="run_qa":
            result(req_id,run_qa(args))
        else:
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
