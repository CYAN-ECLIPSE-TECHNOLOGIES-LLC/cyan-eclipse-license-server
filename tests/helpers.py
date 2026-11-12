import os, sys, tempfile, uuid
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from license_server.core import Core, Caller
from license_server.seed import seed, TENANT_ID, OWNER, ISSUER

OWNER_C = Caller(TENANT_ID, OWNER)
ISSUER_C = Caller(TENANT_ID, ISSUER)
LICENSEE = {"name": "Test User", "email": "test@example.com"}

def make_core():
    tmp = tempfile.mkdtemp(prefix="cetlic-test-")
    core = Core(os.path.join(tmp, "db.sqlite"), key_dir=os.path.join(tmp, "keys"), current_kids={})
    seed(core)
    return core

def issue(core, product="parity", tier="pro", seats=None, licensee=None, expires_at=None, perpetual=None):
    args = {"product_id": product, "tier_id": tier, "licensee": licensee or LICENSEE}
    if seats is not None:
        args["seats"] = seats
    if expires_at is not None:
        args["expires_at"] = expires_at
    if perpetual is not None:
        args["perpetual"] = perpetual
    prop = core.dispatch(ISSUER_C, "license_issue_propose", args)
    assert "proposal_id" in prop, prop
    tok = f"confirm-issue-{prop['proposal_id']}-{prop['proposal_hash'][:12]}"
    mint = core.dispatch(ISSUER_C, "license_issue", {"proposal_id": prop["proposal_id"], "confirm_token": tok})
    assert "artefact" in mint, mint
    return mint

def propose_and_run(core, caller, propose_tool, propose_args, exec_tool, verb):
    prop = core.dispatch(caller, propose_tool, propose_args)
    assert "proposal_id" in prop, prop
    tok = f"confirm-{verb}-{prop['proposal_id']}-{prop['proposal_hash'][:12]}"
    return core.dispatch(caller, exec_tool, {"proposal_id": prop["proposal_id"], "confirm_token": tok})

def revoke(core, license_id):
    return propose_and_run(core, ISSUER_C, "license_revoke_propose", {"license_id": license_id, "reason": "test"},
                           "license_revoke", "revoke")

def new_install():
    return str(uuid.uuid4())
