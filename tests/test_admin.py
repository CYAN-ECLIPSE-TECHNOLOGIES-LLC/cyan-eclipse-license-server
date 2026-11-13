"""Web admin (SPEC S1.7) tests.

Three layers:
- render tests against a fake MCP client (canned T0 tool results):
  every view renders the tool data, escaping holds, search filters;
- HTTP tests: routing, 405 on any write method, 404 on unknown views,
  and the MCP client's read-only guard (a write tool is refused by the
  client itself, before any subprocess work);
- one integration test: a real MCP stdio server over a temp seeded
  runtime, driven through the real HTTP surface end to end.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from admin.app import AdminData, make_handler, render_journal, \
    render_licence_detail, render_licences, render_overview, \
    render_revocations
from admin.mcp_client import McpClient, McpError

LIC_ACTIVE = {
    "license_id": "lic-active-0001", "tenant_id": "cet",
    "product_id": "parity", "tier_id": "pro",
    "features": ["merge_apply"], "licensee": {
        "name": "Fixture <script>alert(1)</script> User",
        "email": "fixture@cetech.ai"},
    "seats": 3, "issued_at": "2026-11-12T00:00:00Z", "expires_at": None,
    "perpetual": True, "kid": "cet-2026-01", "order_ref": "TEST-ORDER-1",
    "sandbox": 0, "prev_license_id": None, "status": "active",
    "state": "LICENSE_VALID", "artefact": "CETLIC.fixture.artefact",
    "artefact_hash": "ab12cd34"}
LIC_REVOKED = dict(LIC_ACTIVE, license_id="lic-revoked-0002",
                   status="revoked", state="LICENSE_REVOKED",
                   order_ref="TEST-ORDER-2")
RECEIPTS = [
    {"sequence": 1, "timestamp": "2026-11-12T00:00:01Z",
     "operation": "license_issue", "license_id": "lic-active-0001",
     "actor": "cet-issuer", "mandate_ref": "mand-1",
     "receipt_hash": "ff" * 32},
    {"sequence": 2, "timestamp": "2026-11-12T00:05:01Z",
     "operation": "license_revoke", "license_id": "lic-revoked-0002",
     "actor": "cet-issuer", "mandate_ref": "mand-1",
     "receipt_hash": "ee" * 32},
]


class FakeClient:
    def tool(self, name, args=None, tenant=None, principal=None):
        args = args or {}
        if name == "policy_show":
            return {"identity": {"product": "Cyan Eclipse License Server",
                                 "activation_model": "B"},
                    "policy": {"grace_days": 14}, "kids_in_force":
                    ["cet-2026-01"], "journal_head": {"sequence": 2},
                    "tenant": tenant}
        if name == "license_list":
            rows = [LIC_ACTIVE, LIC_REVOKED]
            if args.get("product_id"):
                rows = [r for r in rows
                        if r["product_id"] == args["product_id"]]
            if args.get("state"):
                rows = [r for r in rows if r["state"] == args["state"]]
            return {"licenses": rows, "count": len(rows),
                    "surface": "owner"}
        if name == "license_inspect":
            lic = {"lic-active-0001": LIC_ACTIVE,
                   "lic-revoked-0002": LIC_REVOKED}.get(
                       args.get("license_id"))
            if lic is None:
                return {"state": "LICENSE_UNKNOWN",
                        "license_id": args.get("license_id")}
            return {"license": lic, "receipts": RECEIPTS}
        if name == "license_status":
            return {"state": "LICENSE_VALID",
                    "license_id": args.get("license_id")}
        if name == "seat_usage":
            return {"license_id": args.get("license_id"), "seats_cap": 3,
                    "live_count": 1, "activations": [
                        {"install_id": "inst-1", "install_label": "desk",
                         "status": "live",
                         "activated_at": "2026-11-12T00:01:00Z",
                         "last_checkin": "2026-11-12T04:01:00Z"}]}
        if name == "activation_list":
            return {"activations": [{"status": "live"}], "count": 1,
                    "surface": "owner"}
        if name == "journal_info":
            return {"tenant_id": tenant, "count": 2, "sequence": 2,
                    "head_hash": "ee" * 32, "genesis_hash": "00" * 32}
        if name == "chain_verify":
            return {"ok": True, "count": 2, "head_hash": "ee" * 32}
        if name == "journal_list":
            off = int(args.get("offset", 0))
            lim = int(args.get("limit", 100))
            return {"receipts": RECEIPTS[off:off + lim]}
        if name == "revocation_list_get":
            return {"tenant_id": tenant, "generated_at":
                    "2026-11-12T01:00:00Z", "kid": "cet-2026-01",
                    "signature": "c2ln", "revoked": [
                        {"license_id": "lic-revoked-0002",
                         "product_id": "parity"}]}
        raise McpError(f"unexpected tool {name}")


def fake_data():
    return AdminData(FakeClient(), tenants=["cet"], principal="cet-owner")


class RenderTests(unittest.TestCase):
    def test_overview_renders_tool_data(self):
        out = render_overview(fake_data())
        self.assertIn("Tenant cet", out)
        self.assertIn("CHAIN VERIFIED", out)
        self.assertIn("cet-2026-01", out)
        self.assertIn("Cyan Eclipse License Server", out)
        self.assertIn("Provenance. Governance. Proof.", out)

    def test_licence_search_and_escaping(self):
        out = render_licences(fake_data(), "cet")
        self.assertIn("lic-active-0001", out)
        self.assertIn("lic-revoked-0002", out)
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;", out)
        only = render_licences(fake_data(), "cet", q="TEST-ORDER-2")
        self.assertIn("lic-revoked-0002", only)
        self.assertNotIn("lic-active-0001", only)

    def test_licence_detail(self):
        out = render_licence_detail(fake_data(), "cet", "lic-active-0001")
        self.assertIn("CETLIC.fixture.artefact", out)
        self.assertIn("license_issue", out)
        self.assertIn("1 live of", out)

    def test_journal_view(self):
        out = render_journal(fake_data(), "cet")
        self.assertIn("CHAIN VERIFIED", out)
        self.assertIn("license_revoke", out)

    def test_revocations_view(self):
        out = render_revocations(fake_data(), "cet")
        self.assertIn("SIGNED", out)
        self.assertIn("lic-revoked-0002", out)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                        make_handler(fake_data()))
        cls.port = cls.httpd.server_address[1]
        cls.th = threading.Thread(target=cls.httpd.serve_forever,
                                  daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path, method="GET"):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_all_views_200(self):
        for path in ("/", "/licenses", "/license/lic-active-0001",
                     "/journal", "/revocations", "/healthz"):
            code, _ = self.get(path)
            self.assertEqual(code, 200, path)

    def test_writes_refused_405(self):
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            code, body = self.get("/licenses", method=method)
            self.assertEqual(code, 405, method)
            self.assertIn("read-only", body)

    def test_unknown_view_404(self):
        code, _ = self.get("/nope")
        self.assertEqual(code, 404)

    def test_client_refuses_write_tools(self):
        client = McpClient()
        with self.assertRaises(McpError):
            client.tool("license_revoke", {"license_id": "x"},
                        tenant="cet", principal="cet-owner")
        with self.assertRaises(McpError):
            client.tool("product_register", {}, tenant="cet",
                        principal="cet-owner")


class IntegrationTests(unittest.TestCase):
    def test_real_server_end_to_end(self):
        runtime = tempfile.mkdtemp(prefix="cetlic-admin-it-")
        env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"),
                   CETLIC_RUNTIME_DIR=runtime, PYTHONDONTWRITEBYTECODE="1")
        seed = subprocess.run([sys.executable, "-m", "license_server",
                               "--seed"], env=env, capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(seed.returncode, 0, seed.stderr)
        client = McpClient(runtime_dir=runtime)
        data = AdminData(client, tenants=["cet"], principal="cet-owner")
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(data))
        port = httpd.server_address[1]
        th = threading.Thread(target=httpd.serve_forever, daemon=True)
        th.start()
        try:
            for path, marker in (("/", "Tenant cet"),
                                 ("/", "CHAIN VERIFIED"),
                                 ("/", "cet-2026-01"),
                                 ("/licenses", "Licence search"),
                                 ("/journal", "Journal"),
                                 ("/revocations", "Revocation list")):
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}{path}",
                        timeout=15) as r:
                    body = r.read().decode()
                self.assertEqual(r.status, 200, path)
                self.assertIn(marker, body, path)
        finally:
            httpd.shutdown()
            client.close()


if __name__ == "__main__":
    unittest.main()
