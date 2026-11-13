"""Minimal MCP stdio client for the Cyan Eclipse License Server.

Speaks the server's line-delimited JSON-RPC stdio face (the Muster /
Monocle pattern the server implements): one persistent subprocess,
`python3 -m license_server`, initialised once, then tools/call per
request. Caller context rides in the tool arguments as _tenant_id /
_principal_id, exactly as the server's face defines it (transport auth
is a deployment concern, SPEC S1.6; authorisation — tier floors,
mandate scope, denylist — is enforced inside the core, not here).

The client is read-only by construction in this package: the admin app
only ever calls T0 tools, and this client refuses to dispatch any tool
outside the T0 read set it is configured with.
"""
import json
import os
import subprocess
import sys
import threading

READ_TOOLS = {
    "policy_show", "license_verify", "license_status", "license_list",
    "license_inspect", "revocation_list_get", "journal_info",
    "journal_list", "receipt_get", "chain_verify",
    "chain_verify_anchored", "seat_usage", "activation_list",
    "activation_inspect",
}


class McpError(Exception):
    """A tool call failed or the server returned an error result."""


class McpClient:
    def __init__(self, server_src=None, runtime_dir=None, python=None):
        here = os.path.dirname(os.path.abspath(__file__))
        repo = os.path.dirname(here)
        self.server_src = server_src or os.environ.get(
            "CETLIC_ADMIN_SERVER_SRC", os.path.join(repo, "src"))
        self.runtime_dir = runtime_dir or os.environ.get(
            "CETLIC_RUNTIME_DIR",
            "/home/witness/app-family/cyan-eclipse-license-server-runtime")
        self.python = python or sys.executable
        self._proc = None
        self._seq = 0
        self._lock = threading.Lock()

    # ---------- process plumbing ----------
    def _spawn(self):
        env = dict(os.environ,
                   PYTHONPATH=self.server_src,
                   CETLIC_RUNTIME_DIR=self.runtime_dir,
                   PYTHONDONTWRITEBYTECODE="1")
        self._proc = subprocess.Popen(
            [self.python, "-m", "license_server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1, env=env)
        self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "cyan-eclipse-license-server-web-admin",
                           "version": "0.1.0"}})

    def _rpc(self, method, params):
        self._seq += 1
        rid = self._seq
        line = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
                           "params": params}) + "\n"
        self._proc.stdin.write(line)
        self._proc.stdin.flush()
        while True:
            out = self._proc.stdout.readline()
            if not out:
                raise McpError("license server MCP face closed the stream")
            try:
                resp = json.loads(out)
            except ValueError:
                continue
            if resp.get("id") == rid:
                return resp

    def close(self):
        if self._proc is not None:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

    # ---------- tool surface ----------
    def tool(self, name, args=None, tenant=None, principal=None):
        """Call one T0 read tool; returns the parsed result dict.

        Raises McpError on transport failure, a JSON-RPC error, an
        isError result, or a core error payload — the admin renders the
        refusal rather than inventing data."""
        if name not in READ_TOOLS:
            raise McpError(f"refused: {name} is not a T0 read tool; the "
                           "web admin holds no write path")
        args = dict(args or {})
        if tenant is not None:
            args["_tenant_id"] = tenant
        if principal is not None:
            args["_principal_id"] = principal
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._proc is None or self._proc.poll() is not None:
                        self._spawn()
                    resp = self._rpc("tools/call",
                                     {"name": name, "arguments": args})
                    break
                except (BrokenPipeError, McpError):
                    self.close()
                    if attempt == 2:
                        raise
            else:  # pragma: no cover
                raise McpError("unreachable")
        if "error" in resp:
            raise McpError(f"{name}: {resp['error']}")
        result = resp.get("result") or {}
        try:
            text = result["content"][0]["text"]
            parsed = json.loads(text)
        except Exception:
            raise McpError(f"{name}: unparseable tool result")
        if result.get("isError") or (isinstance(parsed, dict)
                                     and "error" in parsed):
            msg = parsed.get("error") if isinstance(parsed, dict) else parsed
            state = parsed.get("state") if isinstance(parsed, dict) else None
            raise McpError(f"{name}: {msg}" + (f" ({state})" if state else ""))
        return parsed
