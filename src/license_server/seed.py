"""Seed tenant #1 (Cyan Eclipse) -- fixture-grade wiring readiness only.

Registers products parity / loom / plumb and their tiers from the SPEC
(S6.1/S6.2/S10.2), an owner + issuer principal, and an issuer mandate.
Does NOT integrate into the actual Parity/Loom/Plumb apps.
Idempotent: re-running changes nothing.
"""
from .core import Caller
from .util import now_iso

TENANT_ID = "cet"
TENANT_NAME = "Cyan Eclipse Technologies LLC"
OWNER = "cet-owner"
ISSUER = "cet-issuer"
DEFAULT_KID = "cet-2026-01"

PRODUCTS = [("parity", "Cyan Eclipse Parity"), ("loom", "Cyan Eclipse Loom"), ("plumb", "Cyan Eclipse Plumb")]

# (product, tier, features, seats, perpetual, term_days)
TIERS = [
    ("parity", "free", [], 1, True, None),
    ("parity", "pro", ["3way_merge_apply", "sftp_ftps", "webdav_s3", "wildcard_alignment", "script_sync_apply"], 1, True, None),
    ("loom", "per-seat", ["edit", "create", "export", "view"], 1, False, 365),
    ("plumb", "term", ["scan", "report", "view", "export"], 1, False, 365),
]

def seed(core, kid=DEFAULT_KID):
    s = core.store
    if s.get_tenant(TENANT_ID):
        return {"tenant_id": TENANT_ID, "seeded": False, "note": "tenant already present"}
    owner = Caller(TENANT_ID, OWNER)
    s.x("INSERT INTO tenants(tenant_id,name,state) VALUES (?,?,?)", (TENANT_ID, TENANT_NAME, "active"))
    s.x("INSERT INTO principals(tenant_id,principal_id,principal_class,name) VALUES (?,?,?,?)",
        (TENANT_ID, OWNER, "tenant_owner", "Tenant #1 owner principal"))
    s.x("INSERT INTO principals(tenant_id,principal_id,principal_class,name) VALUES (?,?,?,?)",
        (TENANT_ID, ISSUER, "issuer", "Tenant #1 issuer principal"))
    s.x("INSERT INTO principals(tenant_id,principal_id,principal_class,name) VALUES (?,?,?,?)",
        (TENANT_ID, "cet-support", "support_reader", "Tenant #1 support reader"))
    s.x("INSERT INTO principals(tenant_id,principal_id,principal_class,name) VALUES (?,?,?,?)",
        (TENANT_ID, "cet-auditor", "auditor", "Tenant #1 auditor"))
    s.commit()
    # signing key: generate in the locked store (outside repo) if absent, register public
    if core.keystore:
        if not core.keystore.exists(kid):
            pub = core.keystore.generate(kid)
        else:
            pub = core.keystore.public_pem(kid)
        core.register_public_key(TENANT_ID, kid, pub)
        core.current_kids[TENANT_ID] = kid
    for pid, name in PRODUCTS:
        core.dispatch(owner, "product_register", {"product_id": pid, "name": name, "custody": "witness"})
    for pid, tier, feats, seats, perp, term in TIERS:
        core.dispatch(owner, "tier_define", {"product_id": pid, "tier_id": tier, "features": feats,
                                             "seats": seats, "perpetual": perp, "term_days": term})
    res = core.dispatch(owner, "principal_manage",
                        {"action": "grant_mandate", "principal_id": ISSUER,
                         "products": ["parity", "loom", "plumb"],
                         "op_classes": ["issue", "renew", "revoke", "reinstate", "supersede", "transfer", "deactivate", "reclaim"],
                         "expires_at": "2027-11-12T00:00:00Z"})
    return {"tenant_id": TENANT_ID, "seeded": True, "kid": kid, "mandate": res}
