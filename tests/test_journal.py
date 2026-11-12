import unittest
from helpers import make_core, issue, OWNER_C, ISSUER_C
from license_server.util import now_iso

class TestJournal(unittest.TestCase):
    def setUp(self):
        self.core = make_core()
        self.mint = issue(self.core)

    def test_chain_verify_ok(self):
        v = self.core.dispatch(OWNER_C, "chain_verify", {})
        self.assertTrue(v["ok"], v)
        self.assertGreaterEqual(v["count"], 9)

    def test_tamper_detection_at_tampered_link(self):
        s = self.core.store
        s.x("UPDATE journal SET operation='renew' WHERE tenant_id='cet' AND sequence=3")
        s.commit()
        v = self.core.dispatch(OWNER_C, "chain_verify", {})
        self.assertFalse(v["ok"])
        self.assertEqual(v["failed_at"], 3)
        self.assertEqual(v["reason"], "receipt_hash_mismatch")

    def test_anchored_verify_match(self):
        v = self.core.dispatch(OWNER_C, "chain_verify", {})
        a = self.core.dispatch(OWNER_C, "chain_verify_anchored",
                               {"anchor_hash": v["head_hash"], "anchor_sequence": v["count"]})
        self.assertTrue(a["anchored"])
        self.assertEqual(a["label"], "ANCHORED_MATCH")

    def test_truncated_prefix_label(self):
        v = self.core.dispatch(OWNER_C, "chain_verify", {})
        # simulate truncation: caller anchors a head 5 entries beyond ours
        a = self.core.dispatch(OWNER_C, "chain_verify_anchored",
                               {"anchor_hash": "f" * 64, "anchor_sequence": v["count"] + 5})
        self.assertFalse(a["anchored"])
        self.assertEqual(a["label"], "TRUNCATED_PREFIX_POSSIBLE")

    def test_anchor_mismatch_label(self):
        a = self.core.dispatch(OWNER_C, "chain_verify_anchored",
                               {"anchor_hash": "f" * 64, "anchor_sequence": 1})
        self.assertEqual(a["label"], "ANCHOR_MISMATCH")

    def test_receipt_get_and_journal_info(self):
        info = self.core.dispatch(OWNER_C, "journal_info", {})
        self.assertGreater(info["count"], 0)
        r = self.core.dispatch(OWNER_C, "receipt_get", {"sequence": info["count"]})
        self.assertIsNotNone(r["receipt"])
        self.assertEqual(r["receipt"]["operation"], "issue")

    def test_journal_before_release(self):
        # a licence in the store always has its issue receipt in the journal
        receipts = self.core.dispatch(OWNER_C, "journal_list", {"limit": 1000})["receipts"]
        ops = [r["operation"] for r in receipts if r["license_id"] == self.mint["license_id"]]
        self.assertIn("issue", ops)
        issue_receipt = [r for r in receipts if r["license_id"] == self.mint["license_id"] and r["operation"] == "issue"][0]
        self.assertEqual(issue_receipt["payload_hash"], self.mint["artefact_hash"])

if __name__ == "__main__":
    unittest.main()
