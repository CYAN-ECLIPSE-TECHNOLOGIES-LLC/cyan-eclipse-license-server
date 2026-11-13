"""MCP server over stdio JSON-RPC (Muster/Monocle pattern).

Caller context rides in the tool arguments as _tenant_id / _principal_id
(transport auth is a deployment concern, SPEC S1.6); authorisation --
mandate scope, tier floors, denylist -- is enforced inside the core.
"""
import json, sys
from .core import Core, Caller, ALL_TOOLS, TIER_FLOORS, DENYLIST
from .tool_specs import TOOL_SPECS

TOOL_DESCRIPTIONS = {n: TOOL_SPECS[n]["description"] for n in ALL_TOOLS}

def handle_request(core: Core, req: dict) -> dict:
    rid = req.get("id")
    method = req.get("method", "")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "cyan-eclipse-license-server", "version": "0.1.0"},
            "capabilities": {"tools": {}}}}
    if method in ("ping", "notifications/initialized"):
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        params = req.get("params") or {}
        tools = []
        for t in core.tools_list(is_admin=bool(params.get("is_admin"))):
            spec = TOOL_SPECS[t["name"]]
            tools.append({"name": t["name"], "title": spec["title"],
                          "description": spec["description"],
                          "inputSchema": spec["inputSchema"],
                          "outputSchema": spec["outputSchema"],
                          "annotations": spec["annotations"]})
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": tools}}
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name", "")
        args = dict(params.get("arguments") or {})
        caller = Caller(args.pop("_tenant_id", None), args.pop("_principal_id", None))
        if name in DENYLIST:
            result = core.dispatch(caller, name, args)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(result)}], "isError": True}}
        result = core.dispatch(caller, name, args)
        is_err = isinstance(result, dict) and "error" in result
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": json.dumps(result, default=str)}], "isError": is_err}}
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown method: {method}"}}

def serve_stdio(core: Core, instream=None, outstream=None):
    instream = instream or sys.stdin
    outstream = outstream or sys.stdout
    for line in instream:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        resp = handle_request(core, req)
        if req.get("id") is not None:
            outstream.write(json.dumps(resp) + "\n")
            outstream.flush()
