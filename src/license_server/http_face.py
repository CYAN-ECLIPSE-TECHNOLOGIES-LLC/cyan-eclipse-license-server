"""Thin HTTP face (SPEC S4.2 as amended by S12.4).

Adapters only -- every route calls a core handler; no logic lives here.
v1 core: binds localhost in tests only; NO production deployment (fence).
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from .core import Caller

def make_handler(core):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            return json.loads(self.rfile.read(n).decode("utf-8"))

        def _code_for(self, result):
            state = (result or {}).get("state", "")
            if state == "LICENSE_SEAT_LIMIT":
                return 409
            if state in ("LICENSE_REVOKED", "LICENSE_EXPIRED", "LICENSE_DEACTIVATED"):
                return 403
            if state.startswith("LICENSE_") and state not in ("LICENSE_VALID", "LICENSE_GRACE"):
                return 400
            return 200

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                args = self._body()
            except Exception:
                return self._send(400, {"state": "LICENSE_MALFORMED"})
            if path == "/activate":
                r = core.activate_runtime(args)
                return self._send(self._code_for(r), r)
            if path == "/checkin":
                r = core.checkin_runtime(args)
                return self._send(200 if r.get("state") not in ("LICENSE_NOT_ACTIVATED",) else 404, r)
            if path == "/deactivate":
                r = core.deactivate_runtime(args)
                return self._send(200, r)
            if path == "/verify":
                caller = Caller(args.get("tenant_id"), args.get("_principal_id"))
                r = core.dispatch(caller, "license_verify", args)
                return self._send(200, r)
            return self._send(404, {"error": "not found"})

        def do_GET(self):
            u = urlparse(self.path)
            qs = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/status":
                caller = Caller(qs.get("tenant_id"), qs.get("_principal_id"))
                r = core.dispatch(caller, "license_status", {"license_id": qs.get("license_id")})
                return self._send(200, r)
            if u.path == "/revocation-list":
                caller = Caller(qs.get("tenant_id"), qs.get("_principal_id"))
                r = core.dispatch(caller, "revocation_list_get", {"product_id": qs.get("product_id")})
                return self._send(200, r)
            return self._send(404, {"error": "not found"})

    return Handler

def serve(core, host="127.0.0.1", port=0):
    httpd = HTTPServer((host, port), make_handler(core))
    return httpd
