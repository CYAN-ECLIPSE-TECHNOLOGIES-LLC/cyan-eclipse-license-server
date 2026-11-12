import unittest
from helpers import make_core, issue
from client.verify import verify_offline
from license_server.artefact import parse_envelope
from license_server.util import canon, b64u, utcnow
from datetime import timedelta

class TestClientOffline(unittest.TestCase):
    """Offline authenticity battery: zero network (functions are pure)."""
    def setUp(self):
        self.core = make_core()
        self.mint = issue(self.core)
        self.keys = self.core.trusted_keys("cet")

    def test_valid(self):
        r = verify_offline(self.mint["artefact"], self.keys, "cet", "parity")
        self.assertEqual(r["state"], "LICENSE_VALID")

    def test_expired(self):
        past = (utcnow() - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        m = issue(self.core, product="loom", tier="per-seat", expires_at=past, perpetual=False)
        r = verify_offline(m["artefact"], self.keys, "cet", "loom")
        self.assertEqual(r["state"], "LICENSE_EXPIRED")

    def test_wrong_product(self):
        r = verify_offline(self.mint["artefact"], self.keys, "cet", "loom")
        self.assertEqual(r["state"], "LICENSE_WRONG_PRODUCT")
        self.assertEqual(r["actual_product"], "parity")

    def test_bad_signature(self):
        payload, body, sig = parse_envelope(self.mint["artefact"])
        payload["seats"] = 50
        forged = b64u(canon(payload)) + "." + b64u(sig)
        r = verify_offline(forged, self.keys, "cet", "parity")
        self.assertEqual(r["state"], "LICENSE_BAD_SIGNATURE")

    def test_unknown_key_and_malformed(self):
        r = verify_offline(self.mint["artefact"], {}, "cet", "parity")
        self.assertEqual(r["state"], "LICENSE_UNKNOWN_KEY")
        r = verify_offline("garbage", self.keys, "cet", "parity")
        self.assertEqual(r["state"], "LICENSE_MALFORMED")

    def test_clock_suspect(self):
        # device clock 3 days before issuance
        payload, _, _ = parse_envelope(self.mint["artefact"])
        from license_server.util import parse_iso
        before = parse_iso(payload["issued_at"]) - timedelta(days=3)
        r = verify_offline(self.mint["artefact"], self.keys, "cet", "parity", now=before)
        self.assertEqual(r["state"], "LICENSE_CLOCK_SUSPECT")

    def test_key_rotation_old_kid_still_trusted(self):
        from helpers import OWNER_C
        from license_server.core import Caller
        res = self.core.rotate_key(OWNER_C, "cet-2026-02")
        self.assertEqual(res["kid"], "cet-2026-02")
        keys2 = self.core.trusted_keys("cet")
        self.assertIn("cet-2026-01", keys2)
        self.assertIn("cet-2026-02", keys2)
        # old artefact still verifies under the rotated set
        r = verify_offline(self.mint["artefact"], keys2, "cet", "parity")
        self.assertEqual(r["state"], "LICENSE_VALID")
        # new issuances use the new kid
        m2 = issue(self.core)
        payload, _, _ = parse_envelope(m2["artefact"])
        self.assertEqual(payload["kid"], "cet-2026-02")
        receipts = self.core.dispatch(OWNER_C, "journal_list", {"limit": 1000})["receipts"]
        self.assertIn("key_rotate", [x["operation"] for x in receipts])

if __name__ == "__main__":
    unittest.main()
