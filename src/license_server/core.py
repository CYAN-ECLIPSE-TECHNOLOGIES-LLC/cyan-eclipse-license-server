"""Cyan Eclipse License Server core (SPEC S1 + Amendment S12, model (B)).

Single implementation of all licensing logic. The MCP server and the thin
HTTP face are adapters onto these handlers -- no logic lives in a face.
BENCH-PENDING: nothing here is certified or live.
"""
import json, secrets, uuid
from datetime import timedelta
from .util import canon, hash_obj, sha256_hex, now_iso, parse_iso, utcnow
from .store import Store
from .journal import Journal, GENESIS
from .artefact import make_envelope, verify_authenticity, artefact_hash
from .keys import KeyStore

IDENTITY = {"product": "Cyan Eclipse License Server",
            "vendor": "Cyan Eclipse Technologies LLC",
            "powered_by": "Cyan Eclipse Technologies",
            "tagline": "Provenance. Governance. Proof.",
            "status": "BENCH-PENDING",
            "activation_model": "B (online activation + real-time seat control, owner ruling 2026-11-12)"}

POLICY_DEFAULTS = {"heartbeat_hours": 4, "offline_window_hours": 72,
                   "reclaim_days": 30, "grace_days": 14,
                   "clock_behind_tolerance_hours": 48, "clock_ahead_tolerance_hours": 24}

TIER_FLOORS = {
    "policy_show": 0, "license_verify": 0, "license_status": 0, "license_list": 0,
    "license_inspect": 0, "revocation_list_get": 0, "journal_info": 0, "journal_list": 0,
    "receipt_get": 0, "chain_verify": 0, "chain_verify_anchored": 0,
    "seat_usage": 0, "activation_list": 0, "activation_inspect": 0,
    "license_issue_propose": 1, "license_renew_propose": 1, "license_revoke_propose": 1,
    "license_reinstate_propose": 1,
    "activation_deactivate_propose": 1,
    "license_issue": 2, "license_renew": 2, "license_revoke": 2, "license_reinstate": 2,
    "license_supersede": 2,
    "product_register": 2, "tier_define": 2, "principal_manage": 2,
    "activation_deactivate": 2, "activation_reclaim_stale": 2}

DENYLIST = ["license_delete", "journal_append", "journal_rewrite", "key_export_private",
            "key_generate_for_tenant", "mandate_self_grant", "bulk_issue_unjournalled",
            "status_override_silent", "activation_delete"]

READ_TOOLS = ["policy_show", "license_verify", "license_status", "license_list", "license_inspect",
              "revocation_list_get", "journal_info", "journal_list", "receipt_get",
              "chain_verify", "chain_verify_anchored", "seat_usage", "activation_list", "activation_inspect"]
PROPOSE_TOOLS = ["license_issue_propose", "license_renew_propose", "license_revoke_propose",
                 "license_reinstate_propose", "activation_deactivate_propose"]
EXECUTE_TOOLS = ["license_issue", "license_renew", "license_revoke", "license_reinstate", "license_supersede",
                 "product_register", "tier_define", "principal_manage",
                 "activation_deactivate", "activation_reclaim_stale"]
ALL_TOOLS = READ_TOOLS + PROPOSE_TOOLS + EXECUTE_TOOLS

class ToolError(Exception):
    def __init__(self, message, state=None):
        super().__init__(message)
        self.message = message
        self.state = state

class Caller:
    def __init__(self, tenant_id, principal_id=None):
        self.tenant_id = tenant_id
        self.principal_id = principal_id

    def __repr__(self):
        return f"Caller({self.tenant_id},{self.principal_id})"

def mask_licensee(licensee, surface):
    if surface != "support":
        return licensee
    out = dict(licensee or {})
    email = out.get("email", "")
    if "@" in email:
        local, domain = email.split("@", 1)
        out["email"] = (local[:1] + "***@" + domain) if local else "***@" + domain
    if out.get("name"):
        parts = out["name"].split()
        out["name"] = " ".join(p[:1] + "." for p in parts)
    return out

class Core:
    def __init__(self, db_path, key_dir=None, current_kids=None, policy=None):
        self.store = Store(db_path)
        self.journal = Journal(self.store)
        self.keystore = KeyStore(key_dir) if key_dir else None
        # current_kids: {tenant_id: kid} used for new issuances
        self.current_kids = current_kids or {}
        self.policy = {**POLICY_DEFAULTS, **(policy or {})}
        self.handlers = {name: getattr(self, "tool_" + name) for name in ALL_TOOLS}

    # ---------- plumbing ----------
    def principal(self, caller):
        return self.store.get_principal(caller.tenant_id, caller.principal_id)

    def principal_class(self, caller):
        p = self.principal(caller)
        return p["principal_class"] if p else None

    def require_tenant(self, caller):
        if not caller.tenant_id or not self.store.get_tenant(caller.tenant_id):
            raise ToolError(f"unknown tenant: {caller.tenant_id}", state="LICENSE_UNKNOWN")

    def require_principal(self, caller, classes=None):
        self.require_tenant(caller)
        p = self.principal(caller)
        if not p:
            self.refuse(caller, "auth", "unknown principal")
        if classes and p["principal_class"] not in classes:
            self.refuse(caller, "auth", f"principal class {p['principal_class']} not in {classes}")
        return p

    def refuse(self, caller, operation, reason, proposal_hash=None):
        """Refused attempts produce a receipted record (refusal log), never a licence."""
        prev = self.store.q1("SELECT entry_hash FROM refusals ORDER BY id DESC LIMIT 1")
        prev_hash = prev["entry_hash"] if prev else GENESIS
        entry = {"tenant_id": caller.tenant_id if caller else None, "operation": operation,
                 "actor": caller.principal_id if caller else None, "reason": reason,
                 "proposal_hash": proposal_hash, "timestamp": now_iso(), "prev_hash": prev_hash}
        entry_hash = hash_obj(entry)
        self.store.x("INSERT INTO refusals(tenant_id,operation,actor,reason,proposal_hash,timestamp,entry_hash) VALUES (?,?,?,?,?,?,?)",
                     (entry["tenant_id"], operation, entry["actor"], reason, proposal_hash, entry["timestamp"], entry_hash))
        self.store.commit()
        raise ToolError(reason, state="REFUSED")

    def refusal_list(self, tenant_id=None):
        rows = self.store.q("SELECT * FROM refusals WHERE (? IS NULL OR tenant_id=?) ORDER BY id", (tenant_id, tenant_id))
        return [dict(r) for r in rows]

    def check_mandate(self, caller, operation, product_id, op_class):
        """Returns mandate row or refuses (receipted). Scope = tenant+products+op class+expiry."""
        p = self.require_principal(caller)
        rows = self.store.q("SELECT * FROM mandates WHERE tenant_id=? AND principal_id=? AND revoked=0",
                            (caller.tenant_id, caller.principal_id))
        now = utcnow()
        saw = False
        for r in rows:
            products = json.loads(r["products"]); ops = json.loads(r["op_classes"])
            if parse_iso(r["expires_at"]) <= now:
                continue
            saw = True
            if ("*" in products or product_id in products) and ("*" in ops or op_class in ops):
                return dict(r)
        reason = "mandate expired" if rows and not saw else "no mandate covering scope"
        if rows and saw:
            reason = "mandate wrong scope"
        if not rows:
            reason = "no mandate"
        self.refuse(caller, operation, reason)
        return None  # unreachable

    def trusted_keys(self, tenant_id):
        return {r["kid"]: r["public_key_pem"] for r in self.store.public_keys(tenant_id) if r["status"] != "compromised"}

    def license_state(self, lic, now=None):
        now = now or utcnow()
        if lic is None:
            return "LICENSE_UNKNOWN"
        if lic["status"] == "revoked":
            return "LICENSE_REVOKED"
        if lic["status"] == "superseded":
            return "LICENSE_SUPERSEDED"
        if not lic["perpetual"] and lic["expires_at"]:
            exp = parse_iso(lic["expires_at"])
            if now > exp:
                if now <= exp + timedelta(days=self.policy["grace_days"]):
                    return "LICENSE_GRACE"
                return "LICENSE_EXPIRED"
        return "LICENSE_VALID"

    # ---------- T0 tools ----------
    def tool_policy_show(self, caller, args):
        kids = []
        if caller.tenant_id and self.store.get_tenant(caller.tenant_id):
            kids = [r["kid"] for r in self.store.public_keys(caller.tenant_id)]
            head = self.journal.head(caller.tenant_id)
        else:
            head = {"sequence": 0, "head_hash": GENESIS}
        return {"identity": IDENTITY, "policy": self.policy, "tier_floors": TIER_FLOORS,
                "denylist": DENYLIST, "tools": ALL_TOOLS, "kids_in_force": kids,
                "journal_head": head, "tenant": caller.tenant_id}

    def tool_license_verify(self, caller, args):
        artefact = args.get("artefact", "")
        # tenant for key resolution comes from the payload if parseable, else caller tenant
        tenant_id = caller.tenant_id
        try:
            from .artefact import parse_envelope
            payload, _, _ = parse_envelope(artefact)
            tenant_id = payload.get("tenant_id", tenant_id)
        except Exception:
            pass
        res = verify_authenticity(artefact, self.trusted_keys(tenant_id),
                                  expected_tenant=args.get("expected_tenant"),
                                  expected_product=args.get("product_id"))
        if res["payload"]:
            lic = self.store.get_license(res["payload"].get("tenant_id"), res["payload"].get("license_id"))
            if lic is None:
                if res["state"] == "LICENSE_VALID":
                    res = {**res, "state": "LICENSE_UNKNOWN"}
            else:
                st = self.license_state(lic)
                if st != "LICENSE_VALID":
                    res = {**res, "state": st}
                res["license_id"] = lic["license_id"]
        return res

    def tool_license_status(self, caller, args):
        self.require_tenant(caller)
        lic = self.store.get_license(caller.tenant_id, args.get("license_id"))
        if lic is None:
            return {"state": "LICENSE_UNKNOWN", "license_id": args.get("license_id")}
        return {"state": self.license_state(lic), "license_id": lic["license_id"],
                "product_id": lic["product_id"], "tier_id": lic["tier_id"],
                "expires_at": lic["expires_at"], "perpetual": lic["perpetual"], "seats": lic["seats"]}

    def _license_view(self, lic, surface):
        return {"license_id": lic["license_id"], "tenant_id": lic["tenant_id"],
                "product_id": lic["product_id"], "tier_id": lic["tier_id"], "features": lic["features"],
                "licensee": mask_licensee(lic["licensee"], surface), "seats": lic["seats"],
                "issued_at": lic["issued_at"], "expires_at": lic["expires_at"],
                "perpetual": lic["perpetual"], "kid": lic["kid"], "order_ref": lic["order_ref"],
                "sandbox": lic["sandbox"], "prev_license_id": lic["prev_license_id"],
                "status": lic["status"], "state": self.license_state(lic),
                "artefact": lic["artefact"], "artefact_hash": lic["artefact_hash"]}

    def tool_license_list(self, caller, args):
        self.require_principal(caller, ["tenant_owner", "issuer", "support_reader", "auditor"])
        surface = "support" if self.principal_class(caller) == "support_reader" else "owner"
        rows = self.store.q("SELECT * FROM licenses WHERE tenant_id=?", (caller.tenant_id,))
        out = []
        for r in rows:
            lic = self.store._license_dict(r)
            if args.get("product_id") and lic["product_id"] != args["product_id"]:
                continue
            if args.get("state") and self.license_state(lic) != args["state"]:
                continue
            out.append(self._license_view(lic, surface))
        return {"licenses": out, "count": len(out), "surface": surface}

    def tool_license_inspect(self, caller, args):
        self.require_principal(caller, ["tenant_owner", "issuer", "support_reader", "auditor"])
        surface = "support" if self.principal_class(caller) == "support_reader" else "owner"
        lic = self.store.get_license(caller.tenant_id, args.get("license_id"))
        if lic is None:
            return {"state": "LICENSE_UNKNOWN", "license_id": args.get("license_id")}
        receipts = [r for r in self.journal.list_receipts(caller.tenant_id, limit=10000)
                    if r["license_id"] == lic["license_id"] or (lic["prev_license_id"] and r["license_id"] == lic["prev_license_id"])]
        return {"license": self._license_view(lic, surface), "receipts": receipts}

    def tool_revocation_list_get(self, caller, args):
        self.require_tenant(caller)
        rows = self.store.q("SELECT license_id, product_id FROM licenses WHERE tenant_id=? AND status='revoked'", (caller.tenant_id,))
        revoked = [dict(r) for r in rows if not args.get("product_id") or r["product_id"] == args["product_id"]]
        body = {"tenant_id": caller.tenant_id, "product_id": args.get("product_id"),
                "generated_at": now_iso(), "revoked": revoked}
        kid = self.current_kids.get(caller.tenant_id)
        sig = None
        if kid and self.keystore:
            from .util import b64u
            sig = b64u(self.keystore.sign(kid, canon(body)))
        return {**body, "kid": kid, "signature": sig}

    def tool_journal_info(self, caller, args):
        self.require_principal(caller, ["tenant_owner", "issuer", "support_reader", "auditor"])
        h = self.journal.head(caller.tenant_id)
        return {"tenant_id": caller.tenant_id, "count": self.journal.count(caller.tenant_id),
                "head_hash": h["head_hash"], "genesis_hash": h["genesis_hash"], "sequence": h["sequence"]}

    def tool_journal_list(self, caller, args):
        self.require_principal(caller, ["tenant_owner", "issuer", "support_reader", "auditor"])
        return {"receipts": self.journal.list_receipts(caller.tenant_id, int(args.get("limit", 100)), int(args.get("offset", 0)))}

    def tool_receipt_get(self, caller, args):
        self.require_principal(caller, ["tenant_owner", "issuer", "support_reader", "auditor"])
        r = self.journal.get_receipt(caller.tenant_id, int(args["sequence"]))
        return {"receipt": r} if r else {"receipt": None, "state": "LICENSE_UNKNOWN"}

    def tool_chain_verify(self, caller, args):
        self.require_principal(caller, ["tenant_owner", "issuer", "support_reader", "auditor"])
        return self.journal.verify(caller.tenant_id)

    def tool_chain_verify_anchored(self, caller, args):
        self.require_principal(caller, ["tenant_owner", "issuer", "support_reader", "auditor"])
        return self.journal.verify_anchored(caller.tenant_id, args["anchor_hash"], args.get("anchor_sequence"))

    # ---------- proposals (T1) ----------
    def _make_proposal(self, caller, kind, payload):
        payload = {**payload, "tenant_id": caller.tenant_id, "kind": kind}
        phash = hash_obj(payload)
        pid = f"prop-{uuid.uuid4().hex[:16]}"
        self.store.x("INSERT INTO proposals(proposal_id,tenant_id,kind,payload,proposal_hash,status,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (pid, caller.tenant_id, kind, json.dumps(payload, sort_keys=True), phash, "proposed", caller.principal_id, now_iso()))
        self.store.commit()
        return {"proposal_id": pid, "proposal_hash": phash, "kind": kind, "payload": payload,
                "confirm_token_shape": f"confirm-{kind}-<proposal_id>-<hash12>"}

    def _get_proposal(self, caller, operation, args, kind):
        pid = args.get("proposal_id")
        r = self.store.q1("SELECT * FROM proposals WHERE proposal_id=? AND tenant_id=?", (pid, caller.tenant_id))
        if not r:
            self.refuse(caller, operation, f"unknown proposal: {pid}")
        if r["kind"] != kind:
            self.refuse(caller, operation, f"proposal kind {r['kind']} != {kind}", r["proposal_hash"])
        if r["status"] != "proposed":
            self.refuse(caller, operation, f"proposal is {r['status']}, not proposed", r["proposal_hash"])
        return dict(r)

    def _validate_token(self, caller, operation, proposal, kind, args):
        expected = f"confirm-{kind}-{proposal['proposal_id']}-{proposal['proposal_hash'][:12]}"
        if args.get("confirm_token") != expected:
            self.refuse(caller, operation, "confirm token not bound to proposal hash", proposal["proposal_hash"])
        return expected

    def tool_license_issue_propose(self, caller, args):
        self.require_principal(caller, ["tenant_owner", "issuer"])
        product = self.store.get_product(caller.tenant_id, args.get("product_id"))
        if not product:
            raise ToolError(f"unknown product: {args.get('product_id')}")
        tier = self.store.get_tier(caller.tenant_id, args["product_id"], args.get("tier_id"))
        if not tier:
            raise ToolError(f"unknown tier: {args.get('tier_id')}")
        seats = int(args.get("seats", tier["seats"]))
        if seats < 1:
            raise ToolError("seats must be >= 1")
        licensee = args.get("licensee") or {}
        if not licensee.get("name") or not licensee.get("email"):
            raise ToolError("licensee.name and licensee.email required")
        payload = {"product_id": args["product_id"], "tier_id": args["tier_id"],
                   "features": args.get("features", tier["features"]), "licensee": licensee,
                   "seats": seats, "expires_at": args.get("expires_at"),
                   "perpetual": bool(args.get("perpetual", tier["perpetual"])),
                   "order_ref": args.get("order_ref"), "sandbox": bool(args.get("sandbox", False)),
                   "prev_license_id": args.get("prev_license_id")}
        if not payload["perpetual"] and not payload["expires_at"]:
            if tier["term_days"]:
                payload["expires_at"] = now_iso(utcnow() + timedelta(days=tier["term_days"]))
            else:
                raise ToolError("term licence requires expires_at")
        return self._make_proposal(caller, "issue", payload)

    def tool_license_renew_propose(self, caller, args):
        self.require_principal(caller, ["tenant_owner", "issuer"])
        lic = self.store.get_license(caller.tenant_id, args.get("license_id"))
        if lic is None:
            raise ToolError("unknown licence", state="LICENSE_UNKNOWN")
        if not args.get("expires_at") and not lic["perpetual"]:
            raise ToolError("renewal requires expires_at for term licences")
        payload = {"license_id": lic["license_id"], "product_id": lic["product_id"],
                   "tier_id": args.get("tier_id", lic["tier_id"]), "expires_at": args.get("expires_at"),
                   "licensee": args.get("licensee"), "seats": args.get("seats")}
        return self._make_proposal(caller, "renew", payload)

    def tool_license_revoke_propose(self, caller, args):
        self.require_principal(caller, ["tenant_owner", "issuer"])
        lic = self.store.get_license(caller.tenant_id, args.get("license_id"))
        if lic is None:
            raise ToolError("unknown licence", state="LICENSE_UNKNOWN")
        payload = {"license_id": lic["license_id"], "product_id": lic["product_id"],
                   "reason": args.get("reason", "")}
        return self._make_proposal(caller, "revoke", payload)

    # ---------- issuance internals ----------
    def _mint(self, caller, payload, prev_license_id, actor_op, proposal, mandate):
        kid = self.current_kids.get(caller.tenant_id)
        if not kid or not self.keystore:
            raise ToolError("no signing key configured for tenant")
        tier = self.store.get_tier(caller.tenant_id, payload["product_id"], payload["tier_id"])
        license_id = str(uuid.uuid4())
        art_payload = {"v": 1, "license_id": license_id, "tenant_id": caller.tenant_id,
                       "product_id": payload["product_id"], "tier_id": payload["tier_id"],
                       "features": payload.get("features") or (tier["features"] if tier else []),
                       "licensee": payload["licensee"], "seats": int(payload.get("seats") or (tier["seats"] if tier else 1)),
                       "issued_at": now_iso(), "expires_at": payload.get("expires_at"),
                       "perpetual": bool(payload.get("perpetual", False)), "kid": kid,
                       "order_ref": payload.get("order_ref"), "sandbox": bool(payload.get("sandbox", False)),
                       "prev_license_id": prev_license_id}
        if art_payload["perpetual"]:
            art_payload["expires_at"] = None
        artefact = make_envelope(art_payload, lambda b: self.keystore.sign(kid, b))
        ahash = artefact_hash(artefact)
        # Journal-before-release: journal + licence land in ONE transaction;
        # a journal failure rolls both back and nothing is issued (S1.5).
        try:
            receipt = self.journal.append(caller.tenant_id, actor_op, actor=caller.principal_id,
                                          license_id=license_id, mandate_ref=mandate["mandate_id"] if mandate else None,
                                          proposal_hash=proposal["proposal_hash"] if proposal else None,
                                          payload_hash=ahash,
                                          extra={"prev_license_id": prev_license_id})
            self.store.x("INSERT INTO licenses(license_id,tenant_id,product_id,tier_id,features,licensee,seats,issued_at,expires_at,perpetual,kid,order_ref,sandbox,prev_license_id,status,artefact,artefact_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (license_id, caller.tenant_id, art_payload["product_id"], art_payload["tier_id"],
                          json.dumps(art_payload["features"]), json.dumps(art_payload["licensee"]),
                          art_payload["seats"], art_payload["issued_at"], art_payload["expires_at"],
                          1 if art_payload["perpetual"] else 0, kid, art_payload["order_ref"],
                          1 if art_payload["sandbox"] else 0, prev_license_id, "active", artefact, ahash))
            if prev_license_id:
                self.store.x("UPDATE licenses SET status='superseded' WHERE tenant_id=? AND license_id=?",
                             (caller.tenant_id, prev_license_id))
            if proposal:
                self.store.x("UPDATE proposals SET status='executed' WHERE proposal_id=?", (proposal["proposal_id"],))
            self.store.commit()
        except Exception:
            self.store.rollback()
            raise
        return {"license_id": license_id, "artefact": artefact, "artefact_hash": ahash,
                "receipt": receipt, "payload": art_payload}

    def tool_license_issue(self, caller, args):
        proposal = self._get_proposal(caller, "license_issue", args, "issue")
        self._validate_token(caller, "license_issue", proposal, "issue", args)
        payload = json.loads(proposal["payload"])
        mandate = self.check_mandate(caller, "license_issue", payload["product_id"], "issue")
        return self._mint(caller, payload, payload.get("prev_license_id"), "issue", proposal, mandate)

    def tool_license_renew(self, caller, args):
        proposal = self._get_proposal(caller, "license_renew", args, "renew")
        self._validate_token(caller, "license_renew", proposal, "renew", args)
        payload = json.loads(proposal["payload"])
        mandate = self.check_mandate(caller, "license_renew", payload["product_id"], "renew")
        old = self.store.get_license(caller.tenant_id, payload["license_id"])
        new_payload = {"product_id": old["product_id"], "tier_id": payload.get("tier_id") or old["tier_id"],
                       "features": old["features"], "licensee": payload.get("licensee") or old["licensee"],
                       "seats": payload.get("seats") or old["seats"],
                       "expires_at": payload.get("expires_at") or old["expires_at"],
                       "perpetual": old["perpetual"], "order_ref": old["order_ref"], "sandbox": old["sandbox"]}
        return self._mint(caller, new_payload, old["license_id"], "renew", proposal, mandate)

    def tool_license_supersede(self, caller, args):
        # Supersede/transfer rides a renew-kind proposal with its own token verb.
        proposal = self._get_proposal(caller, "license_supersede", args, "renew")
        self._validate_token(caller, "license_supersede", proposal, "supersede", args)
        payload = json.loads(proposal["payload"])
        transfer = bool(args.get("transfer"))
        mandate = self.check_mandate(caller, "license_supersede", payload["product_id"], "transfer" if transfer else "supersede")
        old = self.store.get_license(caller.tenant_id, payload["license_id"])
        new_payload = {"product_id": old["product_id"], "tier_id": payload.get("tier_id") or old["tier_id"],
                       "features": old["features"], "licensee": payload.get("licensee") or old["licensee"],
                       "seats": payload.get("seats") or old["seats"],
                       "expires_at": payload.get("expires_at") or old["expires_at"],
                       "perpetual": old["perpetual"], "order_ref": old["order_ref"], "sandbox": old["sandbox"]}
        return self._mint(caller, new_payload, old["license_id"], "transfer" if transfer else "supersede", proposal, mandate)

    def tool_license_revoke(self, caller, args):
        proposal = self._get_proposal(caller, "license_revoke", args, "revoke")
        self._validate_token(caller, "license_revoke", proposal, "revoke", args)
        payload = json.loads(proposal["payload"])
        mandate = self.check_mandate(caller, "license_revoke", payload["product_id"], "revoke")
        lic = self.store.get_license(caller.tenant_id, payload["license_id"])
        try:
            receipt = self.journal.append(caller.tenant_id, "revoke", actor=caller.principal_id,
                                          license_id=lic["license_id"], mandate_ref=mandate["mandate_id"],
                                          proposal_hash=proposal["proposal_hash"],
                                          payload_hash=lic["artefact_hash"],
                                          extra={"reason": payload.get("reason", "")})
            self.store.x("UPDATE licenses SET status='revoked' WHERE tenant_id=? AND license_id=?",
                         (caller.tenant_id, lic["license_id"]))
            self.store.x("UPDATE proposals SET status='executed' WHERE proposal_id=?", (proposal["proposal_id"],))
            self.store.commit()
        except Exception:
            self.store.rollback()
            raise
        return {"license_id": lic["license_id"], "state": "LICENSE_REVOKED", "receipt": receipt}

    # ---------- reinstatement (Standard C, adopted 2026-11-14) ----------
    # A licence revoked under the refund/chargeback standard whose payment
    # is later reversed in the firm's favour is REINSTATED: the SAME licence
    # returns to active service -- same license_id, same artefact, same
    # seats, same install bindings (revocation never touched activations,
    # so a live activation resumes at its next check-in). Reinstatement is
    # NOT license_renew: renew mints a new licence and supersedes the old,
    # which the standard expressly forbids for this leg.
    def _latest_revocation(self, tenant_id, license_id):
        r = self.store.q1("SELECT * FROM journal WHERE tenant_id=? AND license_id=? AND operation='revoke' ORDER BY sequence DESC LIMIT 1",
                          (tenant_id, license_id))
        return dict(r) if r else None

    def _reinstate_blocker(self, lic):
        """(message, state) if lic cannot be reinstated, else None. The
        server's licence model records no revocation cause on the licence
        row -- the cause lives in the revocation's journal entry (extra.
        reason) -- so the only state distinctions available are revoked /
        not-revoked / expired-beyond-grace, and those are what is enforced
        here; cause review stays with the caller (the Standard C wiring
        only calls this for its own revocations)."""
        if lic["status"] != "revoked":
            return (f"reinstate requires a revoked licence (state {self.license_state(lic)})",
                    self.license_state(lic))
        if not lic["perpetual"] and lic["expires_at"]:
            exp = parse_iso(lic["expires_at"])
            if utcnow() > exp + timedelta(days=self.policy["grace_days"]):
                return ("licence expired beyond its grace window; reinstatement refused",
                        "LICENSE_EXPIRED")
        return None

    def tool_license_reinstate_propose(self, caller, args):
        self.require_principal(caller, ["tenant_owner", "issuer"])
        lic = self.store.get_license(caller.tenant_id, args.get("license_id"))
        if lic is None:
            raise ToolError("unknown licence", state="LICENSE_UNKNOWN")
        blocker = self._reinstate_blocker(lic)
        if blocker:
            raise ToolError(blocker[0], state=blocker[1])
        rev = self._latest_revocation(caller.tenant_id, lic["license_id"])
        if rev is None:
            raise ToolError("licence is revoked but no revocation receipt exists in the journal; reinstatement refused")
        payload = {"license_id": lic["license_id"], "product_id": lic["product_id"],
                   "reason": args.get("reason", ""),
                   "revocation_sequence": rev["sequence"],
                   "revocation_receipt_hash": rev["receipt_hash"]}
        return self._make_proposal(caller, "reinstate", payload)

    def tool_license_reinstate(self, caller, args):
        proposal = self._get_proposal(caller, "license_reinstate", args, "reinstate")
        self._validate_token(caller, "license_reinstate", proposal, "reinstate", args)
        payload = json.loads(proposal["payload"])
        mandate = self.check_mandate(caller, "license_reinstate", payload["product_id"], "reinstate")
        lic = self.store.get_license(caller.tenant_id, payload["license_id"])
        blocker = self._reinstate_blocker(lic)
        if blocker:
            self.refuse(caller, "license_reinstate", blocker[0], proposal["proposal_hash"])
        try:
            receipt = self.journal.append(caller.tenant_id, "reinstate", actor=caller.principal_id,
                                          license_id=lic["license_id"], mandate_ref=mandate["mandate_id"],
                                          proposal_hash=proposal["proposal_hash"],
                                          payload_hash=lic["artefact_hash"],
                                          extra={"reason": payload.get("reason", ""),
                                                 "revocation_sequence": payload.get("revocation_sequence"),
                                                 "revocation_receipt_hash": payload.get("revocation_receipt_hash")})
            self.store.x("UPDATE licenses SET status='active' WHERE tenant_id=? AND license_id=?",
                         (caller.tenant_id, lic["license_id"]))
            self.store.x("UPDATE proposals SET status='executed' WHERE proposal_id=?", (proposal["proposal_id"],))
            self.store.commit()
        except Exception:
            self.store.rollback()
            raise
        return {"license_id": lic["license_id"], "state": "LICENSE_VALID", "receipt": receipt,
                "revocation_sequence": payload.get("revocation_sequence")}

    # ---------- T2 admin: products / tiers / principals ----------
    def tool_product_register(self, caller, args):
        self.require_principal(caller, ["tenant_owner"])
        pid = args["product_id"]
        try:
            receipt = self.journal.append(caller.tenant_id, "product_register", actor=caller.principal_id,
                                          extra={"product_id": pid})
            self.store.x("INSERT INTO products(tenant_id,product_id,name,custody) VALUES (?,?,?,?)",
                         (caller.tenant_id, pid, args.get("name", pid), args.get("custody", "witness")))
            self.store.commit()
        except Exception:
            self.store.rollback()
            raise
        return {"product_id": pid, "receipt": receipt}

    def tool_tier_define(self, caller, args):
        self.require_principal(caller, ["tenant_owner"])
        if not self.store.get_product(caller.tenant_id, args["product_id"]):
            raise ToolError(f"unknown product: {args['product_id']}")
        r = self.store.q1("SELECT COALESCE(MAX(version),0) AS v FROM tiers WHERE tenant_id=? AND product_id=? AND tier_id=?",
                          (caller.tenant_id, args["product_id"], args["tier_id"]))
        version = r["v"] + 1  # versioned, never edit-in-place
        try:
            receipt = self.journal.append(caller.tenant_id, "tier_define", actor=caller.principal_id,
                                          extra={"product_id": args["product_id"], "tier_id": args["tier_id"], "version": version})
            self.store.x("INSERT INTO tiers(tenant_id,product_id,tier_id,version,features,seats,perpetual,term_days) VALUES (?,?,?,?,?,?,?,?)",
                         (caller.tenant_id, args["product_id"], args["tier_id"], version,
                          json.dumps(args.get("features", [])), int(args.get("seats", 1)),
                          1 if args.get("perpetual") else 0, args.get("term_days")))
            self.store.commit()
        except Exception:
            self.store.rollback()
            raise
        return {"product_id": args["product_id"], "tier_id": args["tier_id"], "version": version, "receipt": receipt}

    def tool_principal_manage(self, caller, args):
        self.require_principal(caller, ["tenant_owner"])
        action = args.get("action")
        if action == "create_principal":
            self.store.x("INSERT OR REPLACE INTO principals(tenant_id,principal_id,principal_class,name) VALUES (?,?,?,?)",
                         (caller.tenant_id, args["principal_id"], args["principal_class"], args.get("name", "")))
            self.store.commit()
            return {"principal_id": args["principal_id"], "principal_class": args["principal_class"]}
        if action == "grant_mandate":
            if args["principal_id"] == caller.principal_id and args.get("self_grant") is not True:
                # a tenant_owner granting its own first mandate is the tenant's own
                # journalled act (S1.6 step 4); mandate_self_grant as a denylisted
                # tool means an issuer minting its own mandate, which never happens here
                pass
            mid = f"mand-{uuid.uuid4().hex[:16]}"
            try:
                receipt = self.journal.append(caller.tenant_id, "mandate_grant", actor=caller.principal_id,
                                              extra={"principal_id": args["principal_id"], "mandate_id": mid})
                self.store.x("INSERT INTO mandates(mandate_id,tenant_id,principal_id,products,op_classes,expires_at,revoked) VALUES (?,?,?,?,?,?,0)",
                             (mid, caller.tenant_id, args["principal_id"], json.dumps(args["products"]),
                              json.dumps(args["op_classes"]), args["expires_at"]))
                self.store.commit()
            except Exception:
                self.store.rollback()
                raise
            return {"mandate_id": mid, "receipt": receipt}
        if action == "revoke_mandate":
            mid = args["mandate_id"]
            try:
                receipt = self.journal.append(caller.tenant_id, "mandate_revoke", actor=caller.principal_id,
                                              extra={"mandate_id": mid})
                self.store.x("UPDATE mandates SET revoked=1 WHERE tenant_id=? AND mandate_id=?", (caller.tenant_id, mid))
                self.store.commit()
            except Exception:
                self.store.rollback()
                raise
            return {"mandate_id": mid, "receipt": receipt}
        raise ToolError(f"unknown principal_manage action: {action}")

    # ---------- key management entry points (not MCP tools) ----------
    def register_public_key(self, tenant_id, kid, public_pem):
        self.store.x("INSERT OR REPLACE INTO key_registry(tenant_id,kid,public_key_pem,status,created_at) VALUES (?,?,?,'active',?)",
                     (tenant_id, kid, public_pem, now_iso()))
        self.store.commit()

    def rotate_key(self, caller, new_kid):
        """Generate a successor key in the locked key store, register its public
        key, journal key_rotate, and make it current. Old kid stays trusted."""
        self.require_principal(caller, ["tenant_owner"])
        if not self.keystore:
            raise ToolError("no key store configured")
        pub = self.keystore.generate(new_kid)
        try:
            receipt = self.journal.append(caller.tenant_id, "key_rotate", actor=caller.principal_id,
                                          extra={"kid": new_kid})
            self.store.x("INSERT OR REPLACE INTO key_registry(tenant_id,kid,public_key_pem,status,created_at) VALUES (?,?,?,'active',?)",
                         (caller.tenant_id, new_kid, pub, now_iso()))
            self.store.commit()
        except Exception:
            self.store.rollback()
            raise
        self.current_kids[caller.tenant_id] = new_kid
        return {"kid": new_kid, "receipt": receipt}

    def compromise_key(self, caller, kid, window_note=""):
        self.require_principal(caller, ["tenant_owner"])
        try:
            receipt = self.journal.append(caller.tenant_id, "key_compromise", actor=caller.principal_id,
                                          extra={"kid": kid, "note": window_note})
            self.store.x("UPDATE key_registry SET status='compromised' WHERE tenant_id=? AND kid=?",
                         (caller.tenant_id, kid))
            self.store.commit()
        except Exception:
            self.store.rollback()
            raise
        return {"kid": kid, "status": "compromised", "receipt": receipt}

    # ---------- dispatch ----------
    def dispatch(self, caller, tool, args):
        args = args or {}
        if tool in DENYLIST:
            if caller and caller.tenant_id and self.store.get_tenant(caller.tenant_id):
                try:
                    self.refuse(caller, tool, "denylisted tool: excluded, not gated")
                except ToolError as e:
                    return {"error": e.message, "state": "REFUSED", "denylisted": True}
            return {"error": f"denylisted tool: {tool}", "state": "REFUSED", "denylisted": True}
        if tool not in self.handlers:
            return {"error": f"unknown tool: {tool}", "state": "REFUSED"}
        try:
            return self.handlers[tool](caller, args)
        except ToolError as e:
            return {"error": e.message, "state": e.state or "ERROR"}

    def tools_list(self, is_admin=False):
        # Denylisted tools are never listed (excluded, not gated); for
        # non-admin callers they are absent by construction.
        return [{"name": n, "tier": TIER_FLOORS[n]} for n in ALL_TOOLS]

# ---------- Activation / seat service (S12.2) ----------
# Appended as Core methods via class extension for a single implementation
# shared by the HTTP face and the MCP admin tools.

def _is_stale(self, act, now=None):
    now = now or utcnow()
    return parse_iso(act["last_checkin"]) < now - timedelta(days=self.policy["reclaim_days"])

def _live_activations(self, tenant_id, license_id):
    rows = self.store.q("SELECT * FROM activations WHERE tenant_id=? AND license_id=? AND status='live'",
                        (tenant_id, license_id))
    return [dict(r) for r in rows]

def _reclaim_stale(self, tenant_id, license_id, actor, mandate_ref=None):
    """Mark stale live activations reclaimed, journal seat_reclaim per slot.
    Runs inside the caller's transaction (caller commits/rolls back)."""
    reclaimed = []
    for act in self._live_activations(tenant_id, license_id):
        if _is_stale(self, act):
            self.journal.append(tenant_id, "seat_reclaim", actor=actor, license_id=license_id,
                                mandate_ref=mandate_ref, extra={"activation_id": act["activation_id"],
                                                                "install_id": act["install_id"]})
            self.store.x("UPDATE activations SET status='reclaimed' WHERE activation_id=?", (act["activation_id"],))
            reclaimed.append(act["activation_id"])
    return reclaimed

def activate_runtime(self, args):
    """Runtime activation (HTTP face). NOT an MCP admin tool (S12.4)."""
    artefact = args.get("artefact", "")
    install_id = args.get("install_id")
    install_label = args.get("install_label", "")
    if not install_id:
        return {"state": "LICENSE_MALFORMED", "error": "install_id required (client-generated UUID)"}
    try:
        uuid.UUID(str(install_id))
    except Exception:
        return {"state": "LICENSE_MALFORMED", "error": "install_id must be a UUID"}
    # key resolution tenant comes from the artefact payload
    from .artefact import parse_envelope
    try:
        payload, _, _ = parse_envelope(artefact)
    except Exception:
        return {"state": "LICENSE_MALFORMED"}
    tenant_id = payload.get("tenant_id")
    caller = Caller(tenant_id, "runtime")
    res = verify_authenticity(artefact, self.trusted_keys(tenant_id),
                              expected_tenant=tenant_id, expected_product=payload.get("product_id"))
    if res["state"] not in ("LICENSE_VALID", "LICENSE_GRACE"):
        return {"state": res["state"]}
    lic = self.store.get_license(tenant_id, payload.get("license_id"))
    if lic is None:
        return {"state": "LICENSE_UNKNOWN"}
    state = self.license_state(lic)
    if state == "LICENSE_REVOKED":
        self._runtime_refusal(tenant_id, "activate", "licence revoked")
        return {"state": "LICENSE_REVOKED"}
    if state == "LICENSE_EXPIRED":
        return {"state": "LICENSE_EXPIRED"}
    if state == "LICENSE_SUPERSEDED":
        return {"state": "LICENSE_SUPERSEDED"}
    ahash = artefact_hash(artefact)
    try:
        # an existing live activation for this install is idempotent: refresh token
        existing = [a for a in self._live_activations(tenant_id, lic["license_id"]) if a["install_id"] == install_id]
        token = secrets.token_urlsafe(32)
        thash = sha256_hex(token.encode())
        if existing:
            act = existing[0]
            self.store.x("UPDATE activations SET token_hash=?, last_checkin=? WHERE activation_id=?",
                         (thash, now_iso(), act["activation_id"]))
            self.store.commit()
            return {"state": "LICENSE_VALID", "activation_id": act["activation_id"],
                    "activation_token": token, "license_id": lic["license_id"],
                    "server_time": now_iso(), "existing": True}
        _reclaim_stale(self, tenant_id, lic["license_id"], actor="system")
        live = self._live_activations(tenant_id, lic["license_id"])
        if len(live) >= lic["seats"]:
            self.store.commit()
            self._runtime_refusal(tenant_id, "activate", "seat limit")
            return {"state": "LICENSE_SEAT_LIMIT", "license_id": lic["license_id"],
                    "seats": lic["seats"], "live": len(live)}
        activation_id = f"act-{uuid.uuid4().hex[:16]}"
        receipt = self.journal.append(tenant_id, "activate", actor="runtime",
                                      license_id=lic["license_id"], payload_hash=ahash,
                                      extra={"activation_id": activation_id, "install_id": install_id,
                                             "install_label": install_label})
        self.store.x("INSERT INTO activations(activation_id,tenant_id,license_id,install_id,install_label,token_hash,artefact_hash,status,activated_at,last_checkin) VALUES (?,?,?,?,?,?,?,'live',?,?)",
                     (activation_id, tenant_id, lic["license_id"], install_id, install_label,
                      thash, ahash, now_iso(), now_iso()))
        self.store.commit()
    except Exception:
        self.store.rollback()
        raise
    return {"state": "LICENSE_VALID", "activation_id": activation_id, "activation_token": token,
            "license_id": lic["license_id"], "server_time": now_iso(), "receipt_seq": receipt["sequence"]}

def _runtime_refusal(self, tenant_id, operation, reason):
    prev = self.store.q1("SELECT entry_hash FROM refusals ORDER BY id DESC LIMIT 1")
    prev_hash = prev["entry_hash"] if prev else GENESIS
    entry = {"tenant_id": tenant_id, "operation": operation, "actor": "runtime",
             "reason": reason, "proposal_hash": None, "timestamp": now_iso(), "prev_hash": prev_hash}
    self.store.x("INSERT INTO refusals(tenant_id,operation,actor,reason,proposal_hash,timestamp,entry_hash) VALUES (?,?,?,?,?,?,?)",
                 (tenant_id, operation, "runtime", reason, None, entry["timestamp"], hash_obj(entry)))
    self.store.commit()

def _activation_by_token(self, token):
    if not token:
        return None
    thash = sha256_hex(str(token).encode())
    r = self.store.q1("SELECT * FROM activations WHERE token_hash=?", (thash,))
    return dict(r) if r else None

def checkin_runtime(self, args):
    """Heartbeat: activation token + artefact hash ONLY (no usage telemetry, S12.2)."""
    act = self._activation_by_token(args.get("activation_token"))
    if act is None:
        return {"state": "LICENSE_NOT_ACTIVATED"}
    if args.get("artefact_hash") != act["artefact_hash"]:
        return {"state": "LICENSE_BAD_SIGNATURE", "error": "artefact hash mismatch"}
    if act["status"] != "live":
        return {"state": "LICENSE_DEACTIVATED", "activation_id": act["activation_id"]}
    lic = self.store.get_license(act["tenant_id"], act["license_id"])
    state = self.license_state(lic)
    self.store.x("UPDATE activations SET last_checkin=? WHERE activation_id=?", (now_iso(), act["activation_id"]))
    self.store.commit()
    return {"state": state, "activation_id": act["activation_id"], "license_id": act["license_id"],
            "seat_state": "live", "server_time": now_iso(),
            "policy": {"heartbeat_hours": self.policy["heartbeat_hours"],
                       "offline_window_hours": self.policy["offline_window_hours"]},
            "kids_in_force": [r["kid"] for r in self.store.public_keys(act["tenant_id"]) if r["status"] == "active"],
            "revoked": lic["status"] == "revoked"}

def deactivate_runtime(self, args):
    act = self._activation_by_token(args.get("activation_token"))
    if act is None:
        return {"state": "LICENSE_NOT_ACTIVATED"}
    if args.get("artefact_hash") and args["artefact_hash"] != act["artefact_hash"]:
        return {"state": "LICENSE_BAD_SIGNATURE", "error": "artefact hash mismatch"}
    if act["status"] != "live":
        return {"state": "LICENSE_DEACTIVATED", "activation_id": act["activation_id"]}
    caller = Caller(act["tenant_id"], "runtime")
    try:
        receipt = self.journal.append(act["tenant_id"], "deactivate", actor="runtime",
                                      license_id=act["license_id"],
                                      extra={"activation_id": act["activation_id"], "route": "app"})
        self.store.x("UPDATE activations SET status='deactivated' WHERE activation_id=?", (act["activation_id"],))
        self.store.commit()
    except Exception:
        self.store.rollback()
        raise
    return {"state": "LICENSE_DEACTIVATED", "activation_id": act["activation_id"], "receipt_seq": receipt["sequence"]}

def _activation_view(self, act, surface="owner"):
    iid = act["install_id"]
    return {"activation_id": act["activation_id"], "tenant_id": act["tenant_id"],
            "license_id": act["license_id"],
            "install_id": iid if surface == "owner" else iid[:8] + "...",
            "install_label": act["install_label"], "status": act["status"],
            "activated_at": act["activated_at"], "last_checkin": act["last_checkin"],
            "stale": act["status"] == "live" and _is_stale(self, act),
            "artefact_hash": act["artefact_hash"]}

def tool_seat_usage(self, caller, args):
    self.require_principal(caller, ["tenant_owner", "issuer", "support_reader"])
    lic = self.store.get_license(caller.tenant_id, args.get("license_id"))
    if lic is None:
        return {"state": "LICENSE_UNKNOWN", "license_id": args.get("license_id")}
    acts = [self._activation_view(a) for a in
            [dict(r) for r in self.store.q("SELECT * FROM activations WHERE tenant_id=? AND license_id=?", (caller.tenant_id, lic["license_id"]))]]
    live = [a for a in acts if a["status"] == "live"]
    return {"license_id": lic["license_id"], "seats_cap": lic["seats"], "live_count": len(live),
            "activations": acts}

def tool_activation_list(self, caller, args):
    self.require_principal(caller, ["tenant_owner", "issuer", "support_reader"])
    surface = "support" if self.principal_class(caller) == "support_reader" else "owner"
    rows = self.store.q("SELECT * FROM activations WHERE tenant_id=?", (caller.tenant_id,))
    out = []
    for r in rows:
        a = dict(r)
        if args.get("license_id") and a["license_id"] != args["license_id"]:
            continue
        if args.get("status") and a["status"] != args["status"]:
            continue
        out.append(self._activation_view(a, surface))
    return {"activations": out, "count": len(out), "surface": surface}

def tool_activation_inspect(self, caller, args):
    self.require_principal(caller, ["tenant_owner", "issuer", "support_reader"])
    surface = "support" if self.principal_class(caller) == "support_reader" else "owner"
    r = self.store.q1("SELECT * FROM activations WHERE tenant_id=? AND activation_id=?",
                      (caller.tenant_id, args.get("activation_id")))
    if not r:
        return {"state": "LICENSE_UNKNOWN", "activation_id": args.get("activation_id")}
    act = dict(r)
    receipts = [x for x in self.journal.list_receipts(caller.tenant_id, limit=10000)
                if x["license_id"] == act["license_id"] and (x["extra"] or {}).get("activation_id") == act["activation_id"]]
    return {"activation": self._activation_view(act, surface), "receipts": receipts}

def tool_activation_deactivate_propose(self, caller, args):
    self.require_principal(caller, ["tenant_owner", "issuer"])
    r = self.store.q1("SELECT * FROM activations WHERE tenant_id=? AND activation_id=?",
                      (caller.tenant_id, args.get("activation_id")))
    if not r:
        raise ToolError("unknown activation", state="LICENSE_UNKNOWN")
    payload = {"activation_id": args["activation_id"], "license_id": r["license_id"],
               "product_id": (self.store.get_license(caller.tenant_id, r["license_id"]) or {}).get("product_id")}
    return self._make_proposal(caller, "deactivate", payload)

def tool_activation_deactivate(self, caller, args):
    proposal = self._get_proposal(caller, "activation_deactivate", args, "deactivate")
    self._validate_token(caller, "activation_deactivate", proposal, "deactivate", args)
    payload = json.loads(proposal["payload"])
    mandate = self.check_mandate(caller, "activation_deactivate", payload.get("product_id"), "deactivate")
    try:
        receipt = self.journal.append(caller.tenant_id, "deactivate", actor=caller.principal_id,
                                      license_id=payload["license_id"], mandate_ref=mandate["mandate_id"],
                                      proposal_hash=proposal["proposal_hash"],
                                      extra={"activation_id": payload["activation_id"], "route": "admin"})
        self.store.x("UPDATE activations SET status='deactivated' WHERE tenant_id=? AND activation_id=?",
                     (caller.tenant_id, payload["activation_id"]))
        self.store.x("UPDATE proposals SET status='executed' WHERE proposal_id=?", (proposal["proposal_id"],))
        self.store.commit()
    except Exception:
        self.store.rollback()
        raise
    return {"activation_id": payload["activation_id"], "state": "LICENSE_DEACTIVATED", "receipt": receipt}

def tool_activation_reclaim_stale(self, caller, args):
    self.require_principal(caller, ["tenant_owner", "issuer"])
    product_id = args.get("product_id")
    mandate = self.check_mandate(caller, "activation_reclaim_stale", product_id or "*", "reclaim")
    rows = self.store.q("SELECT DISTINCT license_id FROM activations WHERE tenant_id=? AND status='live'", (caller.tenant_id,))
    reclaimed = []
    try:
        for r in rows:
            lic = self.store.get_license(caller.tenant_id, r["license_id"])
            if product_id and lic and lic["product_id"] != product_id:
                continue
            reclaimed += _reclaim_stale(self, caller.tenant_id, r["license_id"], actor=caller.principal_id,
                                        mandate_ref=mandate["mandate_id"])
        self.store.commit()
    except Exception:
        self.store.rollback()
        raise
    return {"reclaimed": reclaimed, "count": len(reclaimed)}

for _name, _fn in list(globals().items()):
    if _name.startswith(("activate_runtime", "checkin_runtime", "deactivate_runtime")):
        setattr(Core, _name, _fn)
for _fn_name in ["_is_stale", "_live_activations", "_reclaim_stale", "_runtime_refusal",
                 "_activation_by_token", "_activation_view", "tool_seat_usage",
                 "tool_activation_list", "tool_activation_inspect",
                 "tool_activation_deactivate_propose", "tool_activation_deactivate",
                 "tool_activation_reclaim_stale"]:
    setattr(Core, _fn_name, globals()[_fn_name])
# refresh handler map now that the S12.4 tools exist on the class
_orig_init = Core.__init__
def _init_with_handlers(self, *a, **kw):
    _orig_init(self, *a, **kw)
    self.handlers = {name: getattr(self, "tool_" + name) for name in ALL_TOOLS}
Core.__init__ = _init_with_handlers
