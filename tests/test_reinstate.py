"""Reinstatement (Standard C): license_reinstate_propose -> license_reinstate.

A licence revoked under the refund/chargeback standard whose payment is
later reversed in the firm's favour is reinstated -- the SAME licence back
to active, never a re-issue (license_renew is the re-issue path and is
expressly not used here).
"""
import unittest
from datetime import timedelta
from helpers import make_core, issue, propose_and_run, revoke, new_install, OWNER_C, ISSUER_C
from license_server.util import utcnow


def reinstate(core, license_id, reason="payment reversed in firm's favour"):
    return propose_and_run(core, ISSUER_C, "license_reinstate_propose",
                           {"license_id": license_id, "reason": reason},
                           "license_reinstate", "reinstate")


class TestReinstate(unittest.TestCase):
    def setUp(self):
        self.core = make_core()

    def test_roundtrip_same_licence_same_artefact(self):
        m = issue(self.core)
        lic = m["license_id"]
        rv = revoke(self.core, lic)
        self.assertEqual(rv["state"], "LICENSE_REVOKED")
        st = self.core.dispatch(OWNER_C, "license_status", {"license_id": lic})
        self.assertEqual(st["state"], "LICENSE_REVOKED")
        out = reinstate(self.core, lic)
        self.assertEqual(out["license_id"], lic)
        self.assertEqual(out["state"], "LICENSE_VALID")
        self.assertEqual(out["revocation_sequence"], rv["receipt"]["sequence"])
        st = self.core.dispatch(OWNER_C, "license_status", {"license_id": lic})
        self.assertEqual(st["state"], "LICENSE_VALID")
        insp = self.core.dispatch(OWNER_C, "license_inspect", {"license_id": lic})
        self.assertEqual(insp["license"]["artefact_hash"], m["artefact_hash"])
        receipts = self.core.dispatch(OWNER_C, "journal_list", {"limit": 1000})["receipts"]
        rein = [x for x in receipts if x["operation"] == "reinstate"]
        self.assertEqual(len(rein), 1)
        self.assertEqual(rein[0]["license_id"], lic)
        self.assertEqual(rein[0]["extra"]["revocation_sequence"], rv["receipt"]["sequence"])
        self.assertEqual(rein[0]["extra"]["revocation_receipt_hash"], rv["receipt"]["receipt_hash"])
        v = self.core.dispatch(OWNER_C, "chain_verify", {})
        self.assertTrue(v["ok"])

    def test_activation_resumes_on_same_binding(self):
        m = issue(self.core)
        lic = m["license_id"]
        act = self.core.activate_runtime({"artefact": m["artefact"], "install_id": new_install()})
        self.assertEqual(act["state"], "LICENSE_VALID")
        chk = {"activation_token": act["activation_token"], "artefact_hash": m["artefact_hash"]}
        self.assertEqual(self.core.checkin_runtime(chk)["state"], "LICENSE_VALID")
        revoke(self.core, lic)
        self.assertEqual(self.core.checkin_runtime(chk)["state"], "LICENSE_REVOKED")
        reinstate(self.core, lic)
        out = self.core.checkin_runtime(chk)
        self.assertEqual(out["state"], "LICENSE_VALID")
        self.assertEqual(out["activation_id"], act["activation_id"])

    def test_refuses_never_revoked(self):
        m = issue(self.core)
        r = self.core.dispatch(ISSUER_C, "license_reinstate_propose", {"license_id": m["license_id"]})
        self.assertIn("error", r)
        self.assertEqual(r["state"], "LICENSE_VALID")

    def test_refuses_unknown_licence(self):
        r = self.core.dispatch(ISSUER_C, "license_reinstate_propose",
                               {"license_id": "00000000-0000-0000-0000-000000000000"})
        self.assertIn("error", r)
        self.assertEqual(r["state"], "LICENSE_UNKNOWN")

    def test_refuses_expired_beyond_grace(self):
        past = (utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        m = issue(self.core, product="loom", tier="per-seat", expires_at=past, perpetual=False)
        revoke(self.core, m["license_id"])
        r = self.core.dispatch(ISSUER_C, "license_reinstate_propose", {"license_id": m["license_id"]})
        self.assertIn("error", r)
        self.assertEqual(r["state"], "LICENSE_EXPIRED")

    def test_refuses_second_reinstate(self):
        m = issue(self.core)
        revoke(self.core, m["license_id"])
        reinstate(self.core, m["license_id"])
        r = self.core.dispatch(ISSUER_C, "license_reinstate_propose", {"license_id": m["license_id"]})
        self.assertIn("error", r)
        self.assertEqual(r["state"], "LICENSE_VALID")

    def test_execute_revalidates_state(self):
        # Propose while revoked, reinstate via a second proposal, then the
        # first proposal's execution must refuse (licence no longer revoked).
        m = issue(self.core)
        revoke(self.core, m["license_id"])
        p1 = self.core.dispatch(ISSUER_C, "license_reinstate_propose", {"license_id": m["license_id"]})
        reinstate(self.core, m["license_id"])
        tok = f"confirm-reinstate-{p1['proposal_id']}-{p1['proposal_hash'][:12]}"
        r = self.core.dispatch(ISSUER_C, "license_reinstate",
                               {"proposal_id": p1["proposal_id"], "confirm_token": tok})
        self.assertIn("error", r)
        self.assertEqual(r["state"], "REFUSED")

    def test_bad_token_refused(self):
        m = issue(self.core)
        revoke(self.core, m["license_id"])
        p = self.core.dispatch(ISSUER_C, "license_reinstate_propose", {"license_id": m["license_id"]})
        r = self.core.dispatch(ISSUER_C, "license_reinstate",
                               {"proposal_id": p["proposal_id"], "confirm_token": "confirm-reinstate-x-y"})
        self.assertIn("error", r)
        self.assertEqual(r["state"], "REFUSED")


if __name__ == "__main__":
    unittest.main()
