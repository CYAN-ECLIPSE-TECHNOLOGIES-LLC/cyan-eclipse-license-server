import unittest
from helpers import make_core, issue, revoke, new_install, OWNER_C, ISSUER_C
from license_server.core import Caller

class TestSeats(unittest.TestCase):
    def setUp(self):
        self.core = make_core()
        self.mint = issue(self.core, seats=1)

    def activate(self, install=None):
        return self.core.activate_runtime({"artefact": self.mint["artefact"],
                                           "install_id": install or new_install(),
                                           "install_label": "test install"})

    def test_seat_cap_refuses_second(self):
        a1 = self.activate()
        self.assertEqual(a1["state"], "LICENSE_VALID")
        a2 = self.activate()
        self.assertEqual(a2["state"], "LICENSE_SEAT_LIMIT")

    def test_deactivate_frees_slot(self):
        a1 = self.activate()
        d = self.core.deactivate_runtime({"activation_token": a1["activation_token"],
                                          "artefact_hash": self.mint["artefact_hash"]})
        self.assertEqual(d["state"], "LICENSE_DEACTIVATED")
        a2 = self.activate()
        self.assertEqual(a2["state"], "LICENSE_VALID")

    def test_same_install_reactivation_idempotent(self):
        inst = new_install()
        a1 = self.activate(inst)
        a2 = self.activate(inst)
        self.assertEqual(a2["state"], "LICENSE_VALID")
        usage = self.core.dispatch(OWNER_C, "seat_usage", {"license_id": self.mint["license_id"]})
        self.assertEqual(usage["live_count"], 1)

    def test_admin_deactivate_via_propose_confirm(self):
        a1 = self.activate()
        prop = self.core.dispatch(ISSUER_C, "activation_deactivate_propose", {"activation_id": a1["activation_id"]})
        tok = f"confirm-deactivate-{prop['proposal_id']}-{prop['proposal_hash'][:12]}"
        r = self.core.dispatch(ISSUER_C, "activation_deactivate", {"proposal_id": prop["proposal_id"], "confirm_token": tok})
        self.assertEqual(r["state"], "LICENSE_DEACTIVATED")
        a2 = self.activate()
        self.assertEqual(a2["state"], "LICENSE_VALID")

    def test_checkin_happy_and_bad_hash(self):
        a1 = self.activate()
        ci = self.core.checkin_runtime({"activation_token": a1["activation_token"],
                                        "artefact_hash": self.mint["artefact_hash"]})
        self.assertEqual(ci["state"], "LICENSE_VALID")
        self.assertIn("server_time", ci)
        bad = self.core.checkin_runtime({"activation_token": a1["activation_token"], "artefact_hash": "0" * 64})
        self.assertEqual(bad["state"], "LICENSE_BAD_SIGNATURE")

    def test_revocation_propagation(self):
        a1 = self.activate()
        r = revoke(self.core, self.mint["license_id"])
        self.assertEqual(r["state"], "LICENSE_REVOKED")
        ci = self.core.checkin_runtime({"activation_token": a1["activation_token"],
                                        "artefact_hash": self.mint["artefact_hash"]})
        self.assertEqual(ci["state"], "LICENSE_REVOKED")
        a2 = self.activate()
        self.assertEqual(a2["state"], "LICENSE_REVOKED")
        st = self.core.dispatch(OWNER_C, "license_status", {"license_id": self.mint["license_id"]})
        self.assertEqual(st["state"], "LICENSE_REVOKED")
        rl = self.core.dispatch(OWNER_C, "revocation_list_get", {"product_id": "parity"})
        self.assertIn(self.mint["license_id"], [x["license_id"] for x in rl["revoked"]])

    def test_stale_reclaim(self):
        a1 = self.activate()
        old_install = None
        rows = self.core.store.q("SELECT install_id FROM activations WHERE activation_id=?", (a1["activation_id"],))
        old_install = rows[0]["install_id"]
        # backdate last_checkin past the 30-day reclaim window
        self.core.store.x("UPDATE activations SET last_checkin='2026-01-01T00:00:00Z' WHERE activation_id=?", (a1["activation_id"],))
        self.core.store.commit()
        usage = self.core.dispatch(OWNER_C, "seat_usage", {"license_id": self.mint["license_id"]})
        stale = [a for a in usage["activations"] if a["activation_id"] == a1["activation_id"]][0]
        self.assertTrue(stale["stale"])
        # new activation reclaims the stale slot
        a2 = self.activate()
        self.assertEqual(a2["state"], "LICENSE_VALID")
        # old install checking in later is told LICENSE_DEACTIVATED
        ci = self.core.checkin_runtime({"activation_token": a1["activation_token"],
                                        "artefact_hash": self.mint["artefact_hash"]})
        self.assertEqual(ci["state"], "LICENSE_DEACTIVATED")
        receipts = self.core.dispatch(OWNER_C, "journal_list", {"limit": 1000})["receipts"]
        self.assertIn("seat_reclaim", [r["operation"] for r in receipts])

    def test_admin_reclaim_stale_tool(self):
        a1 = self.activate()
        self.core.store.x("UPDATE activations SET last_checkin='2026-01-01T00:00:00Z' WHERE activation_id=?", (a1["activation_id"],))
        self.core.store.commit()
        r = self.core.dispatch(ISSUER_C, "activation_reclaim_stale", {"product_id": "parity"})
        self.assertEqual(r["count"], 1)
        a2 = self.activate()
        self.assertEqual(a2["state"], "LICENSE_VALID")

if __name__ == "__main__":
    unittest.main()
