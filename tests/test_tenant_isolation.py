import unittest
from helpers import make_core, issue, OWNER_C
from license_server.core import Caller

class TestTenantIsolation(unittest.TestCase):
    def setUp(self):
        self.core = make_core()
        self.mint = issue(self.core)
        s = self.core.store
        # second tenant with its own owner, no objects
        s.x("INSERT INTO tenants(tenant_id,name,state) VALUES ('other','Other Org','active')")
        s.x("INSERT INTO principals(tenant_id,principal_id,principal_class,name) VALUES ('other','other-owner','tenant_owner','Other owner')")
        s.commit()
        self.other = Caller("other", "other-owner")
        self.cet_owner_as_other = Caller("other", "cet-owner")

    def test_cross_tenant_status_unknown(self):
        r = self.core.dispatch(self.other, "license_status", {"license_id": self.mint["license_id"]})
        self.assertEqual(r["state"], "LICENSE_UNKNOWN")

    def test_cross_tenant_inspect_unknown(self):
        r = self.core.dispatch(self.other, "license_inspect", {"license_id": self.mint["license_id"]})
        self.assertEqual(r["state"], "LICENSE_UNKNOWN")

    def test_cross_tenant_list_empty(self):
        r = self.core.dispatch(self.other, "license_list", {})
        self.assertEqual(r["count"], 0)

    def test_cross_tenant_journal_isolated(self):
        r = self.core.dispatch(self.other, "journal_info", {})
        self.assertEqual(r["count"], 0)
        v = self.core.dispatch(self.other, "chain_verify", {})
        self.assertTrue(v["ok"])
        self.assertEqual(v["count"], 0)

    def test_cet_principal_has_no_standing_in_other_tenant(self):
        r = self.core.dispatch(self.cet_owner_as_other, "license_list", {})
        self.assertIn("error", r)  # principal cet-owner does not exist under tenant 'other'

    def test_cross_tenant_mutation_refused(self):
        r = self.core.dispatch(self.other, "license_revoke_propose", {"license_id": self.mint["license_id"]})
        self.assertIn("error", r)
        st = self.core.dispatch(OWNER_C, "license_status", {"license_id": self.mint["license_id"]})
        self.assertEqual(st["state"], "LICENSE_VALID")

    def test_own_tenant_still_works(self):
        st = self.core.dispatch(OWNER_C, "license_status", {"license_id": self.mint["license_id"]})
        self.assertEqual(st["state"], "LICENSE_VALID")

if __name__ == "__main__":
    unittest.main()
