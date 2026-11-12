import unittest
from helpers import make_core, OWNER_C, ISSUER_C, LICENSEE
from license_server.core import Caller

class TestMandateGate(unittest.TestCase):
    def setUp(self):
        self.core = make_core()

    def _propose(self, caller=ISSUER_C):
        return self.core.dispatch(caller, "license_issue_propose",
                                  {"product_id": "parity", "tier_id": "pro", "licensee": LICENSEE})

    def _run(self, caller, prop, token=None):
        tok = token if token is not None else f"confirm-issue-{prop['proposal_id']}-{prop['proposal_hash'][:12]}"
        return self.core.dispatch(caller, "license_issue", {"proposal_id": prop["proposal_id"], "confirm_token": tok})

    def test_valid_mandate_mints(self):
        m = self._run(ISSUER_C, self._propose())
        self.assertIn("artefact", m)

    def test_no_mandate_refused_and_receipted(self):
        # support_reader has no mandate (and cannot even propose->execute as issuer)
        self.core.dispatch(OWNER_C, "principal_manage",
                           {"action": "create_principal", "principal_id": "nomand", "principal_class": "issuer"})
        caller = Caller("cet", "nomand")
        prop = self._propose(caller)
        before = len(self.core.refusal_list("cet"))
        r = self._run(caller, prop)
        self.assertNotIn("artefact", r)
        self.assertEqual(r.get("state"), "REFUSED")
        after = self.core.refusal_list("cet")
        self.assertEqual(len(after), before + 1)
        self.assertEqual(after[-1]["reason"], "no mandate")

    def test_wrong_scope_refused(self):
        self.core.dispatch(OWNER_C, "principal_manage",
                           {"action": "create_principal", "principal_id": "loomonly", "principal_class": "issuer"})
        self.core.dispatch(OWNER_C, "principal_manage",
                           {"action": "grant_mandate", "principal_id": "loomonly", "products": ["loom"],
                            "op_classes": ["issue"], "expires_at": "2027-01-01T00:00:00Z"})
        caller = Caller("cet", "loomonly")
        prop = self._propose(caller)  # parity proposal
        r = self._run(caller, prop)
        self.assertNotIn("artefact", r)
        self.assertEqual(self.core.refusal_list("cet")[-1]["reason"], "mandate wrong scope")

    def test_expired_mandate_refused(self):
        self.core.dispatch(OWNER_C, "principal_manage",
                           {"action": "create_principal", "principal_id": "oldmand", "principal_class": "issuer"})
        self.core.dispatch(OWNER_C, "principal_manage",
                           {"action": "grant_mandate", "principal_id": "oldmand", "products": ["parity"],
                            "op_classes": ["issue"], "expires_at": "2020-01-01T00:00:00Z"})
        caller = Caller("cet", "oldmand")
        prop = self._propose(caller)
        r = self._run(caller, prop)
        self.assertNotIn("artefact", r)
        self.assertEqual(self.core.refusal_list("cet")[-1]["reason"], "mandate expired")

    def test_wrong_token_refused_and_receipted(self):
        prop = self._propose()
        before = len(self.core.refusal_list("cet"))
        r = self._run(ISSUER_C, prop, token=f"confirm-issue-{prop['proposal_id']}-000000000000")
        self.assertNotIn("artefact", r)
        self.assertEqual(len(self.core.refusal_list("cet")), before + 1)
        # and the real token still works afterwards (proposal not consumed)
        m = self._run(ISSUER_C, prop)
        self.assertIn("artefact", m)

    def test_wrong_hash_token_refused(self):
        prop = self._propose()
        other = self._propose()
        r = self._run(ISSUER_C, prop, token=f"confirm-issue-{other['proposal_id']}-{other['proposal_hash'][:12]}")
        self.assertNotIn("artefact", r)

    def test_unknown_principal_refused(self):
        prop = self._propose()
        r = self._run(Caller("cet", "ghost"), prop)
        self.assertNotIn("artefact", r)

    def test_propose_changes_nothing(self):
        before = self.core.dispatch(OWNER_C, "journal_info", {})["count"]
        self._propose()
        after = self.core.dispatch(OWNER_C, "journal_info", {})["count"]
        self.assertEqual(before, after)
        lst = self.core.dispatch(OWNER_C, "license_list", {})
        self.assertEqual(lst["count"], 0)

if __name__ == "__main__":
    unittest.main()
