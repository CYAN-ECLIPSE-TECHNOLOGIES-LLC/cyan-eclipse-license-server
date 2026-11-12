import unittest, threading, json, urllib.request
from helpers import make_core, issue, new_install, OWNER_C
from license_server.http_face import serve
from license_server.mcp_server import handle_request
from client.activation import ActivationClient
from client.state import ClientSession
from license_server.util import utcnow
from datetime import timedelta

def call_mcp(core, name, args, tenant="cet", principal="cet-owner"):
    a = dict(args); a["_tenant_id"] = tenant; a["_principal_id"] = principal
    resp = handle_request(core, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": name, "arguments": a}})
    return json.loads(resp["result"]["content"][0]["text"])

class TestFaces(unittest.TestCase):
    def setUp(self):
        self.core = make_core()
        self.mint = issue(self.core, seats=2)
        self.httpd = serve(self.core, "127.0.0.1", 0)
        self.port = self.httpd.server_address[1]
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.t.start()
        self.client = ActivationClient(f"http://127.0.0.1:{self.port}")

    def tearDown(self):
        self.httpd.shutdown()

    def test_verify_parity_http_vs_mcp(self):
        via_http = self.client.verify("cet", self.mint["artefact"], "parity")
        via_mcp = call_mcp(self.core, "license_verify", {"artefact": self.mint["artefact"], "product_id": "parity"})
        self.assertEqual(via_http["state"], via_mcp["state"])
        self.assertEqual(via_http["state"], "LICENSE_VALID")

    def test_activate_checkin_parity(self):
        # HTTP activate
        a_http = self.client.activate(self.mint["artefact"], new_install(), "http install")
        self.assertEqual(a_http["state"], "LICENSE_VALID")
        ci_http = self.client.checkin(a_http["activation_token"], self.mint["artefact_hash"])
        self.assertEqual(ci_http["state"], "LICENSE_VALID")
        # core activate (the handler the MCP-admin/HTTP faces share)
        a_core = self.core.activate_runtime({"artefact": self.mint["artefact"], "install_id": new_install(), "install_label": "core install"})
        self.assertEqual(a_core["state"], "LICENSE_VALID")
        ci_core = self.core.checkin_runtime({"activation_token": a_core["activation_token"], "artefact_hash": self.mint["artefact_hash"]})
        self.assertEqual(ci_core["state"], ci_http["state"])
        # third install exceeds seats=2 on BOTH faces identically
        a3_http = self.client.activate(self.mint["artefact"], new_install(), "third")
        self.assertEqual(a3_http["state"], "LICENSE_SEAT_LIMIT")

    def test_status_and_revocation_list_http(self):
        st = self.client.status("cet", self.mint["license_id"])
        self.assertEqual(st["state"], "LICENSE_VALID")
        rl = self.client.revocation_list("cet", "parity")
        self.assertEqual(rl["revoked"], [])
        self.assertIsNotNone(rl["signature"])

    def test_deactivate_http(self):
        a = self.client.activate(self.mint["artefact"], new_install(), "x")
        d = self.client.deactivate(a["activation_token"], self.mint["artefact_hash"])
        self.assertEqual(d["state"], "LICENSE_DEACTIVATED")
        ci = self.client.checkin(a["activation_token"], self.mint["artefact_hash"])
        self.assertEqual(ci["state"], "LICENSE_DEACTIVATED")

    def test_mcp_tools_list_and_denylist(self):
        resp = handle_request(self.core, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertEqual(len(names), 27)
        for denied in ("license_delete", "journal_append", "key_export_private", "activation_delete", "mandate_self_grant"):
            self.assertNotIn(denied, names)
        for name in ("license_delete", "journal_append", "journal_rewrite", "key_export_private",
                     "key_generate_for_tenant", "mandate_self_grant", "bulk_issue_unjournalled",
                     "status_override_silent", "activation_delete"):
            r = call_mcp(self.core, name, {})
            self.assertEqual(r.get("state"), "REFUSED", name)

class TestClientStateLogic(unittest.TestCase):
    def test_not_activated(self):
        s = ClientSession()
        self.assertEqual(s.evaluate(utcnow())["state"], "LICENSE_NOT_ACTIVATED")

    def test_unreachable_inside_window_then_suspended(self):
        s = ClientSession(offline_window_hours=72)
        t0 = utcnow()
        s.on_activation_result({"state": "LICENSE_VALID"}, t0)
        r = s.evaluate(t0 + timedelta(hours=10), checkin_reachable=False)
        self.assertEqual(r["state"], "LICENSE_SERVER_UNREACHABLE")
        self.assertTrue(r["paid_features"])
        r = s.evaluate(t0 + timedelta(hours=100), checkin_reachable=False)
        self.assertEqual(r["state"], "LICENSE_SUSPENDED_OFFLINE")
        self.assertFalse(r["paid_features"])
        self.assertTrue(r["read_export"])  # work stays readable/exportable
        # one successful check-in restores immediately
        s.on_checkin_result({"state": "LICENSE_VALID"}, t0 + timedelta(hours=101))
        r = s.evaluate(t0 + timedelta(hours=101), checkin_reachable=True)
        self.assertEqual(r["state"], "LICENSE_VALID")
        self.assertTrue(r["paid_features"])

    def test_seat_limit_and_deactivated_states(self):
        s = ClientSession()
        self.assertEqual(s.on_activation_result({"state": "LICENSE_SEAT_LIMIT"}, utcnow()), "LICENSE_SEAT_LIMIT")
        self.assertEqual(s.evaluate(utcnow())["state"], "LICENSE_SEAT_LIMIT")
        s2 = ClientSession()
        s2.on_activation_result({"state": "LICENSE_VALID"}, utcnow())
        s2.on_checkin_result({"state": "LICENSE_DEACTIVATED"}, utcnow())
        self.assertEqual(s2.evaluate(utcnow())["state"], "LICENSE_DEACTIVATED")

if __name__ == "__main__":
    unittest.main()
