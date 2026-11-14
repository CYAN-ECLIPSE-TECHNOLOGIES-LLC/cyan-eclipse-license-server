import unittest
from helpers import make_core, issue, propose_and_run, OWNER_C, ISSUER_C
from license_server.util import utcnow
from datetime import timedelta

class TestLifecycle(unittest.TestCase):
    def setUp(self):
        self.core = make_core()

    def test_policy_show_identity_and_defaults(self):
        p = self.core.dispatch(OWNER_C, "policy_show", {})
        self.assertEqual(p["identity"]["product"], "Cyan Eclipse License Server")
        self.assertEqual(p["identity"]["tagline"], "Provenance. Governance. Proof.")
        self.assertEqual(p["policy"]["heartbeat_hours"], 4)
        self.assertEqual(p["policy"]["offline_window_hours"], 72)
        self.assertEqual(p["policy"]["reclaim_days"], 30)
        self.assertIn("cet-2026-01", p["kids_in_force"])
        self.assertEqual(len(p["tools"]), 29)

    def test_renew_creates_lineage_and_supersedes_old(self):
        m = issue(self.core, product="loom", tier="per-seat",
                  expires_at=(utcnow() + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"), perpetual=False)
        new_exp = (utcnow() + timedelta(days=395)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = propose_and_run(self.core, ISSUER_C, "license_renew_propose",
                            {"license_id": m["license_id"], "expires_at": new_exp},
                            "license_renew", "renew")
        self.assertIn("artefact", r)
        self.assertEqual(r["payload"]["prev_license_id"], m["license_id"])
        self.assertEqual(r["payload"]["expires_at"], new_exp)
        old = self.core.dispatch(OWNER_C, "license_status", {"license_id": m["license_id"]})
        self.assertEqual(old["state"], "LICENSE_SUPERSEDED")
        receipts = self.core.dispatch(OWNER_C, "journal_list", {"limit": 1000})["receipts"]
        self.assertIn("renew", [x["operation"] for x in receipts])

    def test_supersede_with_new_licensee_transfer(self):
        m = issue(self.core)
        r = propose_and_run(self.core, ISSUER_C, "license_renew_propose",
                            {"license_id": m["license_id"], "licensee": {"name": "New Holder", "email": "new@example.com"}},
                            "license_supersede", "supersede")
        # supersede handler rides the renew proposal; transfer flag off -> supersede op
        self.assertIn("artefact", r)
        self.assertEqual(r["payload"]["licensee"]["name"], "New Holder")

    def test_tier_versioning_no_edit_in_place(self):
        r1 = self.core.dispatch(OWNER_C, "tier_define", {"product_id": "parity", "tier_id": "pro",
                                                         "features": ["a"], "seats": 1, "perpetual": True})
        self.assertEqual(r1["version"], 2)
        t = self.core.store.get_tier("cet", "parity", "pro")
        self.assertEqual(t["version"], 2)
        rows = self.core.store.q("SELECT version FROM tiers WHERE tenant_id='cet' AND product_id='parity' AND tier_id='pro' ORDER BY version")
        self.assertEqual([x["version"] for x in rows], [1, 2])  # v1 preserved

    def test_support_masking(self):
        issue(self.core)
        from license_server.core import Caller
        sup = self.core.dispatch(Caller("cet", "cet-support"), "license_list", {})
        self.assertEqual(sup["surface"], "support")
        email = sup["licenses"][0]["licensee"]["email"]
        self.assertIn("***@", email)
        own = self.core.dispatch(OWNER_C, "license_list", {})
        self.assertEqual(own["licenses"][0]["licensee"]["email"], "test@example.com")

    def test_seed_products_and_tiers(self):
        for pid in ("parity", "loom", "plumb"):
            self.assertIsNotNone(self.core.store.get_product("cet", pid))
        free = self.core.store.get_tier("cet", "parity", "free")
        self.assertTrue(free["perpetual"])
        pro = self.core.store.get_tier("cet", "parity", "pro")
        self.assertIn("sftp_ftps", pro["features"])
        self.assertFalse(self.core.store.get_tier("cet", "loom", "per-seat")["perpetual"])

if __name__ == "__main__":
    unittest.main()
