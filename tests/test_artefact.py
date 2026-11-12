import unittest, base64, json
from helpers import make_core, issue, OWNER_C
from license_server.artefact import verify_authenticity, parse_envelope
from license_server.util import canon, b64u, utcnow
from datetime import timedelta

def mutate(artefact, field, value):
    payload, body, sig = parse_envelope(artefact)
    payload[field] = value
    return b64u(canon(payload)) + "." + b64u(sig)  # original signature over mutated payload

class TestArtefact(unittest.TestCase):
    def setUp(self):
        self.core = make_core()
        self.mint = issue(self.core)
        self.keys = self.core.trusted_keys("cet")

    def verify(self, art, product="parity"):
        return verify_authenticity(art, self.keys, expected_tenant="cet", expected_product=product)

    def test_valid(self):
        self.assertEqual(self.verify(self.mint["artefact"])["state"], "LICENSE_VALID")

    def test_mutation_tier(self):
        self.assertEqual(self.verify(mutate(self.mint["artefact"], "tier_id", "free"))["state"], "LICENSE_BAD_SIGNATURE")

    def test_mutation_seats(self):
        self.assertEqual(self.verify(mutate(self.mint["artefact"], "seats", 99))["state"], "LICENSE_BAD_SIGNATURE")

    def test_mutation_expiry(self):
        self.assertEqual(self.verify(mutate(self.mint["artefact"], "expires_at", "2999-01-01T00:00:00Z"))["state"], "LICENSE_BAD_SIGNATURE")

    def test_mutation_licensee(self):
        bad = mutate(self.mint["artefact"], "licensee", {"name": "Eve", "email": "eve@example.com"})
        self.assertEqual(self.verify(bad)["state"], "LICENSE_BAD_SIGNATURE")

    def test_wrong_product(self):
        self.assertEqual(self.verify(self.mint["artefact"], product="loom")["state"], "LICENSE_WRONG_PRODUCT")

    def test_unknown_key(self):
        art = mutate(self.mint["artefact"], "kid", "cet-1999-99")
        # kid mutation also breaks signature order: key resolve runs BEFORE signature (S2.3)
        self.assertEqual(self.verify(art)["state"], "LICENSE_UNKNOWN_KEY")

    def test_malformed(self):
        self.assertEqual(self.verify("not-a-licence")["state"], "LICENSE_MALFORMED")
        self.assertEqual(self.verify("")["state"], "LICENSE_MALFORMED")

    def test_expired_and_grace(self):
        past = (utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        m = issue(self.core, product="loom", tier="per-seat", expires_at=past, perpetual=False)
        self.assertEqual(self.verify(m["artefact"], product="loom")["state"], "LICENSE_EXPIRED")
        recent = (utcnow() - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        m2 = issue(self.core, product="loom", tier="per-seat", expires_at=recent, perpetual=False)
        self.assertEqual(self.verify(m2["artefact"], product="loom")["state"], "LICENSE_GRACE")

    def test_server_verify_matches(self):
        r = self.core.dispatch(OWNER_C, "license_verify", {"artefact": self.mint["artefact"], "product_id": "parity"})
        self.assertEqual(r["state"], "LICENSE_VALID")

if __name__ == "__main__":
    unittest.main()
