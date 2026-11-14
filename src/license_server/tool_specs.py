"""Tool-surface specification for the MCP face: title, description,
input/output schema and annotations for every tool the core serves.

Descriptions follow the firm's tool-description template: front-loaded
purpose (specific verb + resource, distinguished from its siblings),
when to use / when not to use it with named alternatives, behaviour
disclosures (caller classes, mandate scope, journal effects,
irreversibility), parameter semantics beyond the schema, and the
return shape. Every statement here is behaviour-accurate against
core.py -- read the handler before editing its entry.

Caller context on the MCP (stdio) face rides in the tool arguments as
_tenant_id / _principal_id; authorisation (tenant existence, principal
class, mandate scope, tier floors) is enforced inside the core, and
refused attempts are written to the tenant's refusal log and returned
with state REFUSED -- a refusal never creates a licence or a silent
change. Denylisted operations (licence deletion, journal rewriting,
private-key export, self-granted mandates) are not tools at all: they
are excluded from this list by construction, not gated.
"""

_TENANT = {
    "type": "string",
    "description": "Tenant the call acts for. The tenant must exist; an "
                   "unknown tenant is refused with state LICENSE_UNKNOWN. "
                   "Transport authentication is a deployment concern -- "
                   "this parameter scopes the call, it does not "
                   "authenticate it.",
}
_PRINCIPAL = {
    "type": "string",
    "description": "Acting principal inside the tenant. Principal-gated "
                   "tools refuse unknown principals and principals of "
                   "the wrong class; executions (tier T2) additionally "
                   "require a live, unexpired mandate covering the "
                   "product and the operation class.",
}

_S = {"type": "string"}
_I = {"type": "integer"}
_B = {"type": "boolean"}
_A = {"type": "array"}
_O = {"type": "object"}
_SN = {"type": ["string", "null"]}

_RO = {"readOnlyHint": True, "destructiveHint": False,
       "idempotentHint": True, "openWorldHint": False}
_PROPOSE = {"readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": False}
_EXEC = {"readOnlyHint": False, "destructiveHint": False,
         "idempotentHint": False, "openWorldHint": False}
_EXEC_D = {"readOnlyHint": False, "destructiveHint": True,
           "idempotentHint": False, "openWorldHint": False}


def _schema(props, required=()):
    return {"type": "object", "properties": props,
            "required": list(required)}


def _out(props):
    return {"type": "object", "properties": props}


_CTX_T = {"_tenant_id": _TENANT}
_CTX_TP = {"_tenant_id": _TENANT, "_principal_id": _PRINCIPAL}

_PROPOSAL_ID = {
    "type": "string",
    "description": "Proposal id returned by the matching propose tool. "
                   "The proposal must still be in proposed state and "
                   "belong to the caller's tenant; anything else is "
                   "refused and logged.",
}
_CONFIRM = {
    "type": "string",
    "description": "Confirm token bound to the proposal hash, in the "
                   "shape confirm-<verb>-<proposal_id>-<first 12 of the "
                   "proposal hash>. A token bound to any other proposal "
                   "or hash is refused and logged; the token is the "
                   "human-confirmation step of the propose -> confirm "
                   "flow and is single-use.",
}

TOOL_SPECS = {
    # ---------------- T0 reads ----------------
    "policy_show": {
        "title": "Show server policy and posture",
        "description": "Show this server's identity, policy defaults "
                       "(heartbeat 4 h, offline window 72 h, seat-reclaim "
                       "window 30 d, expiry grace 14 d, clock tolerances), "
                       "the tier floor of every tool, the denylist, the "
                       "tenant's signing key ids in force, and the tenant's "
                       "journal head. Use it first, for orientation and "
                       "discovery; it is the only tool that answers without "
                       "a valid tenant (an absent or unknown tenant gets the "
                       "genesis journal head and no key ids). It reports "
                       "posture, never licence state -- use license_status "
                       "or license_inspect for a licence. Read-only; "
                       "changes nothing.",
        "inputSchema": _schema(dict(_CTX_TP)),
        "outputSchema": _out({"identity": _O, "policy": _O,
                              "tier_floors": _O, "denylist": _A,
                              "tools": _A, "kids_in_force": _A,
                              "journal_head": _O, "tenant": _SN}),
        "annotations": _RO,
    },
    "license_verify": {
        "title": "Verify a licence artefact",
        "description": "Verify a signed .cetlic licence artefact string: "
                       "parse the envelope, check the Ed25519 signature "
                       "against the issuing tenant's registered public "
                       "keys, check optional tenant/product expectations, "
                       "then reconcile with the store (an authentic "
                       "artefact for an unknown licence reports "
                       "LICENSE_UNKNOWN; a stored state such as REVOKED "
                       "overrides the artefact's own validity). Use it "
                       "when an artefact is in hand; use license_status "
                       "instead when only a licence id is known. The "
                       "tenant is resolved from the artefact payload, so "
                       "caller context is optional. Read-only.",
        "inputSchema": _schema({
            "artefact": {"type": "string",
                         "description": "The complete .cetlic artefact "
                                        "string (base64url payload + '.' "
                                        "+ base64url signature), exactly "
                                        "as issued."},
            "expected_tenant": {"type": "string",
                                "description": "Optional: refuse unless "
                                               "the artefact's tenant_id "
                                               "equals this value."},
            "product_id": {"type": "string",
                           "description": "Optional: refuse unless the "
                                          "artefact's product_id equals "
                                          "this value."},
            **_CTX_TP}, required=("artefact",)),
        "outputSchema": _out({"state": _S, "payload": _O,
                              "license_id": _S}),
        "annotations": _RO,
    },
    "license_status": {
        "title": "Show one licence's current state",
        "description": "Show the current computed state of one stored "
                       "licence: LICENSE_VALID, LICENSE_GRACE (inside "
                       "the 14-day post-expiry grace), LICENSE_EXPIRED, "
                       "LICENSE_REVOKED, LICENSE_SUPERSEDED, or "
                       "LICENSE_UNKNOWN when the id is not the tenant's. "
                       "Returns state plus product, tier, expiry, "
                       "perpetual flag, and seat count -- the summary "
                       "view. Use license_inspect for the full record "
                       "with its journal receipts, and license_verify "
                       "when an artefact string is in hand. Requires a "
                       "valid _tenant_id. Read-only.",
        "inputSchema": _schema({
            "license_id": {"type": "string",
                           "description": "Stored licence id to report "
                                          "on."},
            **_CTX_TP}, required=("license_id", "_tenant_id")),
        "outputSchema": _out({"state": _S, "license_id": _S,
                              "product_id": _S, "tier_id": _S,
                              "expires_at": _SN, "perpetual": _B,
                              "seats": _I}),
        "annotations": _RO,
    },
    "license_list": {
        "title": "List the tenant's licences",
        "description": "List every licence stored for the caller's "
                       "tenant, optionally filtered by product_id or "
                       "by computed state (for example LICENSE_REVOKED). "
                       "Caller must be a principal of class "
                       "tenant_owner, issuer, support_reader, or "
                       "auditor. On the support surface (support_reader) "
                       "licensee details are masked; other classes see "
                       "the full record. Use license_inspect for one "
                       "licence with its receipts; this tool returns "
                       "the same per-licence view in bulk plus a count "
                       "and the surface served. Read-only.",
        "inputSchema": _schema({
            "product_id": {"type": "string",
                           "description": "Optional filter: only "
                                          "licences for this product."},
            "state": {"type": "string",
                      "description": "Optional filter: only licences "
                                     "whose computed state equals this "
                                     "value (e.g. LICENSE_VALID)."},
            **_CTX_TP}, required=("_tenant_id", "_principal_id")),
        "outputSchema": _out({"licenses": _A, "count": _I,
                              "surface": _S}),
        "annotations": _RO,
    },
    "license_inspect": {
        "title": "Inspect one licence with its receipts",
        "description": "Show one stored licence in full -- terms, "
                       "licensee, artefact and artefact hash, status "
                       "history fields -- together with every journal "
                       "receipt that names it or its predecessor "
                       "licence. Caller must be a principal of class "
                       "tenant_owner, issuer, support_reader, or "
                       "auditor; support_reader sees a masked licensee. "
                       "An unknown id returns state LICENSE_UNKNOWN "
                       "rather than an error. Use license_status for "
                       "the cheap state-only check. Read-only.",
        "inputSchema": _schema({
            "license_id": {"type": "string",
                           "description": "Stored licence id to "
                                          "inspect."},
            **_CTX_TP}, required=("license_id", "_tenant_id",
                                   "_principal_id")),
        "outputSchema": _out({"license": _O, "receipts": _A,
                              "state": _S, "license_id": _S}),
        "annotations": _RO,
    },
    "revocation_list_get": {
        "title": "Get the signed revocation list",
        "description": "Return the tenant's current revocation list: "
                       "the ids of all revoked licences, optionally "
                       "filtered to one product, as a body signed with "
                       "the tenant's current signing key (signature is "
                       "null when no key store is configured). This is "
                       "the published artefact offline verifiers and "
                       "auditors check; under online activation "
                       "(model B), connected apps instead learn of a "
                       "revocation at their next check-in, so do not "
                       "use this as a live status check -- use "
                       "license_status. Requires a valid _tenant_id. "
                       "Read-only.",
        "inputSchema": _schema({
            "product_id": {"type": "string",
                           "description": "Optional filter: only "
                                          "revocations for this "
                                          "product."},
            **_CTX_TP}, required=("_tenant_id",)),
        "outputSchema": _out({"tenant_id": _S, "product_id": _SN,
                              "generated_at": _S, "revoked": _A,
                              "kid": _SN, "signature": _SN}),
        "annotations": _RO,
    },
    "journal_info": {
        "title": "Show journal head and count",
        "description": "Show the head of the caller's tenant journal: "
                       "receipt count, latest sequence number, head "
                       "hash, and genesis hash. The journal is the "
                       "tenant's append-only, hash-chained record of "
                       "every lifecycle operation and refusal. Caller "
                       "must be a principal of class tenant_owner, "
                       "issuer, support_reader, or auditor. Use it to "
                       "anchor or sanity-check the chain; use "
                       "chain_verify to recompute the whole chain and "
                       "journal_list / receipt_get to read entries. "
                       "Read-only.",
        "inputSchema": _schema(dict(_CTX_TP),
                               required=("_tenant_id", "_principal_id")),
        "outputSchema": _out({"tenant_id": _S, "count": _I,
                              "head_hash": _S, "genesis_hash": _S,
                              "sequence": _I}),
        "annotations": _RO,
    },
    "journal_list": {
        "title": "List journal receipts",
        "description": "List the caller's tenant journal receipts in "
                       "sequence order, paged by limit (default 100) "
                       "and offset. Each receipt is one hash-chained "
                       "lifecycle entry (issue, renew, revoke, "
                       "activation events, refusals of note). Caller "
                       "must be a principal of class tenant_owner, "
                       "issuer, support_reader, or auditor. Use "
                       "receipt_get for a single known sequence and "
                       "chain_verify when integrity, not content, is "
                       "the question. Read-only.",
        "inputSchema": _schema({
            "limit": {"type": "integer",
                      "description": "Maximum receipts to return "
                                     "(default 100)."},
            "offset": {"type": "integer",
                       "description": "Receipts to skip before the "
                                      "page starts (default 0)."},
            **_CTX_TP}, required=("_tenant_id", "_principal_id")),
        "outputSchema": _out({"receipts": _A}),
        "annotations": _RO,
    },
    "receipt_get": {
        "title": "Get one journal receipt",
        "description": "Return a single journal receipt by its "
                       "sequence number in the caller's tenant "
                       "journal. Caller must be a principal of class "
                       "tenant_owner, issuer, support_reader, or "
                       "auditor. A sequence that does not exist "
                       "returns receipt null with state "
                       "LICENSE_UNKNOWN. Use journal_list to browse "
                       "and chain_verify to validate the chain the "
                       "receipt sits in. Read-only.",
        "inputSchema": _schema({
            "sequence": {"type": "integer",
                         "description": "Journal sequence number of "
                                        "the receipt (1-based, "
                                        "contiguous per tenant)."},
            **_CTX_TP}, required=("sequence", "_tenant_id",
                                   "_principal_id")),
        "outputSchema": _out({"receipt": _O, "state": _S}),
        "annotations": _RO,
    },
    "chain_verify": {
        "title": "Verify the journal hash chain",
        "description": "Recompute the caller's tenant journal hash "
                       "chain end to end and report whether every "
                       "receipt's sequence and previous-hash link "
                       "check out. Returns ok, the receipt count, the "
                       "head hash, and -- on failure -- the sequence "
                       "it failed at and why (sequence_gap or "
                       "prev_hash_mismatch). Caller must be a "
                       "principal of class tenant_owner, issuer, "
                       "support_reader, or auditor. Use "
                       "chain_verify_anchored instead when an "
                       "externally witnessed anchor must be honoured. "
                       "Read-only.",
        "inputSchema": _schema(dict(_CTX_TP),
                               required=("_tenant_id", "_principal_id")),
        "outputSchema": _out({"ok": _B, "count": _I, "head_hash": _S,
                              "failed_at": _I, "reason": _S}),
        "annotations": _RO,
    },
    "chain_verify_anchored": {
        "title": "Verify the chain against an external anchor",
        "description": "Verify the caller's tenant journal chain "
                       "(exactly as chain_verify) and additionally "
                       "that the chain extends an externally held "
                       "anchor: the receipt at the anchor sequence "
                       "must carry the anchor hash, proving history "
                       "was not rewritten below the anchor. Caller "
                       "must be a principal of class tenant_owner, "
                       "issuer, support_reader, or auditor. Use "
                       "chain_verify when no external anchor exists. "
                       "Read-only.",
        "inputSchema": _schema({
            "anchor_hash": {"type": "string",
                            "description": "Externally witnessed "
                                           "journal hash to anchor "
                                           "against (required)."},
            "anchor_sequence": {"type": "integer",
                                "description": "Optional sequence "
                                               "number the anchor "
                                               "hash belongs to."},
            **_CTX_TP}, required=("anchor_hash", "_tenant_id",
                                   "_principal_id")),
        "outputSchema": _out({"ok": _B, "count": _I, "head_hash": _S,
                              "failed_at": _I, "reason": _S}),
        "annotations": _RO,
    },
    "seat_usage": {
        "title": "Show seat usage for one licence",
        "description": "Show the seat picture for one licence: its "
                       "seat cap, how many activations are live, and "
                       "every activation on record (install label, "
                       "status, activated-at, last check-in, stale "
                       "flag; install ids are truncated off the owner "
                       "surface). Caller must be a principal of class "
                       "tenant_owner, issuer, or support_reader. An "
                       "unknown licence returns state "
                       "LICENSE_UNKNOWN. Use activation_list to "
                       "browse activations across licences and "
                       "activation_inspect for one activation with "
                       "its receipts. Read-only.",
        "inputSchema": _schema({
            "license_id": {"type": "string",
                           "description": "Licence whose seats to "
                                          "report."},
            **_CTX_TP}, required=("license_id", "_tenant_id",
                                   "_principal_id")),
        "outputSchema": _out({"license_id": _S, "seats_cap": _I,
                              "live_count": _I, "activations": _A,
                              "state": _S}),
        "annotations": _RO,
    },
    "activation_list": {
        "title": "List activations",
        "description": "List every activation recorded for the "
                       "caller's tenant, optionally filtered by "
                       "license_id or by status (live, deactivated, "
                       "reclaimed). Caller must be a principal of "
                       "class tenant_owner, issuer, or "
                       "support_reader; support_reader sees "
                       "truncated install ids. Returns the "
                       "activations, a count, and the surface "
                       "served. Use seat_usage for the per-licence "
                       "cap-versus-live summary. Read-only.",
        "inputSchema": _schema({
            "license_id": {"type": "string",
                           "description": "Optional filter: only "
                                          "activations of this "
                                          "licence."},
            "status": {"type": "string",
                       "description": "Optional filter: only "
                                      "activations with this status."},
            **_CTX_TP}, required=("_tenant_id", "_principal_id")),
        "outputSchema": _out({"activations": _A, "count": _I,
                              "surface": _S}),
        "annotations": _RO,
    },
    "activation_inspect": {
        "title": "Inspect one activation",
        "description": "Show one activation in full -- install, "
                       "status, timestamps, stale flag, artefact "
                       "hash -- plus the journal receipts that name "
                       "it. Caller must be a principal of class "
                       "tenant_owner, issuer, or support_reader; "
                       "support_reader sees a truncated install id. "
                       "An unknown activation id returns state "
                       "LICENSE_UNKNOWN rather than an error. "
                       "Read-only.",
        "inputSchema": _schema({
            "activation_id": {"type": "string",
                              "description": "Activation id to "
                                             "inspect."},
            **_CTX_TP}, required=("activation_id", "_tenant_id",
                                   "_principal_id")),
        "outputSchema": _out({"activation": _O, "receipts": _A,
                              "state": _S, "activation_id": _S}),
        "annotations": _RO,
    },
    # ---------------- T1 proposals ----------------
    "license_issue_propose": {
        "title": "Propose issuing a licence",
        "description": "Create a proposal to issue a new licence. A "
                       "proposal changes nothing by itself: it "
                       "validates the request (product and tier must "
                       "exist, seats must be >= 1 and default to the "
                       "tier's, licensee needs a name and an email, "
                       "and a term licence needs expires_at or a "
                       "tier term) and returns a proposal id, its "
                       "hash, and the confirm-token shape. Caller "
                       "must be tenant_owner or issuer. Nothing is "
                       "issued until license_issue executes the "
                       "proposal with the bound confirm token under "
                       "a live mandate. Each call creates a fresh "
                       "proposal.",
        "inputSchema": _schema({
            "product_id": {"type": "string",
                           "description": "Registered product to "
                                          "licence (required)."},
            "tier_id": {"type": "string",
                        "description": "Defined tier of that "
                                       "product (required)."},
            "licensee": {"type": "object",
                         "description": "Who the licence is issued "
                                        "to; must carry name and "
                                        "email."},
            "seats": {"type": "integer",
                      "description": "Seat count (activation cap). "
                                     "Defaults to the tier's seats; "
                                     "must be >= 1."},
            "features": {"type": "array",
                         "description": "Feature list to grant. "
                                        "Defaults to the tier's "
                                        "features."},
            "expires_at": {"type": "string",
                           "description": "ISO-8601 expiry for a "
                                          "term licence. Omit for "
                                          "perpetual, or when the "
                                          "tier's term_days should "
                                          "set it."},
            "perpetual": {"type": "boolean",
                          "description": "True for a perpetual "
                                         "licence (no expiry). "
                                         "Defaults to the tier's "
                                         "setting."},
            "order_ref": {"type": "string",
                          "description": "External order reference "
                                         "carried into the "
                                         "artefact, for reconciliation "
                                         "with the seller's records."},
            "sandbox": {"type": "boolean",
                        "description": "True marks the licence as a "
                                       "sandbox/test issuance "
                                       "(default false)."},
            "prev_license_id": {"type": "string",
                                "description": "Previous licence this "
                                               "issuance succeeds, "
                                               "when chaining manually; "
                                               "renewals normally go "
                                               "through "
                                               "license_renew_propose."},
            **_CTX_TP}, required=("product_id", "tier_id",
                                   "_tenant_id", "_principal_id")),
        "outputSchema": _out({"proposal_id": _S, "proposal_hash": _S,
                              "kind": _S, "payload": _O,
                              "confirm_token_shape": _S}),
        "annotations": _PROPOSE,
    },
    "license_renew_propose": {
        "title": "Propose renewing a licence",
        "description": "Create a proposal to renew an existing "
                       "licence. Validates that the licence exists "
                       "(unknown ids fail with LICENSE_UNKNOWN) and "
                       "that a term licence gets a new expires_at; "
                       "fields left out (tier, licensee, seats) "
                       "inherit the current licence's values when "
                       "license_renew executes. Caller must be "
                       "tenant_owner or issuer. The proposal alone "
                       "changes nothing and extends nothing. Each "
                       "call creates a fresh proposal.",
        "inputSchema": _schema({
            "license_id": {"type": "string",
                           "description": "Licence to renew "
                                          "(required)."},
            "expires_at": {"type": "string",
                           "description": "New ISO-8601 expiry. "
                                          "Required for term "
                                          "licences."},
            "tier_id": {"type": "string",
                        "description": "Tier to renew onto; "
                                       "defaults to the current "
                                       "tier."},
            "licensee": {"type": "object",
                         "description": "Replacement licensee "
                                        "record; defaults to the "
                                        "current one."},
            "seats": {"type": "integer",
                      "description": "New seat count; defaults "
                                     "to the current count."},
            **_CTX_TP}, required=("license_id", "_tenant_id",
                                   "_principal_id")),
        "outputSchema": _out({"proposal_id": _S, "proposal_hash": _S,
                              "kind": _S, "payload": _O,
                              "confirm_token_shape": _S}),
        "annotations": _PROPOSE,
    },
    "license_revoke_propose": {
        "title": "Propose revoking a licence",
        "description": "Create a proposal to revoke an existing "
                       "licence, with a reason that will be "
                       "journalled at execution. Validates that the "
                       "licence exists (unknown ids fail with "
                       "LICENSE_UNKNOWN). Caller must be "
                       "tenant_owner or issuer. The proposal alone "
                       "revokes nothing: revocation happens only "
                       "when license_revoke executes it, and "
                       "connected clients then see the revocation "
                       "at their next check-in. Each call creates a "
                       "fresh proposal.",
        "inputSchema": _schema({
            "license_id": {"type": "string",
                           "description": "Licence to revoke "
                                          "(required)."},
            "reason": {"type": "string",
                       "description": "Reason recorded in the "
                                      "journal at revocation (for "
                                      "example a refund or "
                                      "chargeback reference)."},
            **_CTX_TP}, required=("license_id", "_tenant_id",
                                   "_principal_id")),
        "outputSchema": _out({"proposal_id": _S, "proposal_hash": _S,
                              "kind": _S, "payload": _O,
                              "confirm_token_shape": _S}),
        "annotations": _PROPOSE,
    },
    "license_reinstate_propose": {
        "title": "Propose reinstating a revoked licence",
        "description": "Create a proposal to reinstate a revoked "
                       "licence: return the SAME licence to active "
                       "service with its original licence id, "
                       "artefact, tier, seats and install bindings "
                       "intact. This is the Standard C path -- a "
                       "licence revoked under the refund/chargeback "
                       "standard whose payment is later reversed in "
                       "the firm's favour is reinstated, never "
                       "re-issued; use license_renew (which mints a "
                       "successor and supersedes the old licence) "
                       "for term renewals instead. Validates that "
                       "the licence exists (LICENSE_UNKNOWN), is "
                       "currently revoked, and -- for term licences "
                       "-- is not expired beyond its grace window. "
                       "The proposal records the journal sequence "
                       "and receipt hash of the revocation it "
                       "reverses, and the executed reinstatement is "
                       "journalled against that revocation. Caller "
                       "must be tenant_owner or issuer. The "
                       "proposal alone reinstates nothing: "
                       "reinstatement happens only when "
                       "license_reinstate executes it, and "
                       "connected clients then see the licence "
                       "valid at their next check-in. Each call "
                       "creates a fresh proposal.",
        "inputSchema": _schema({
            "license_id": {"type": "string",
                           "description": "Revoked licence to "
                                          "reinstate (required)."},
            "reason": {"type": "string",
                       "description": "Reason recorded in the "
                                      "journal at reinstatement "
                                      "(for example the payment "
                                      "reversal reference)."},
            **_CTX_TP}, required=("license_id", "_tenant_id",
                                   "_principal_id")),
        "outputSchema": _out({"proposal_id": _S, "proposal_hash": _S,
                              "kind": _S, "payload": _O,
                              "confirm_token_shape": _S}),
        "annotations": _PROPOSE,
    },
    "activation_deactivate_propose": {
        "title": "Propose deactivating an activation",
        "description": "Create a proposal to deactivate one "
                       "activation, freeing its seat when executed. "
                       "The activation must exist -- an unknown id "
                       "is an error here, unlike the read tools. "
                       "Caller must be tenant_owner or issuer. The "
                       "proposal alone frees nothing; "
                       "activation_deactivate executes it under a "
                       "mandate. Each call creates a fresh proposal.",
        "inputSchema": _schema({
            "activation_id": {"type": "string",
                              "description": "Activation to "
                                             "deactivate "
                                             "(required)."},
            **_CTX_TP}, required=("activation_id", "_tenant_id",
                                   "_principal_id")),
        "outputSchema": _out({"proposal_id": _S, "proposal_hash": _S,
                              "kind": _S, "payload": _O,
                              "confirm_token_shape": _S}),
        "annotations": _PROPOSE,
    },
    # ---------------- T2 executions ----------------
    "license_issue": {
        "title": "Issue a licence (execute proposal)",
        "description": "Execute an issue proposal and mint the "
                       "licence: the signed .cetlic artefact is "
                       "created and the issuance is written to the "
                       "tenant journal BEFORE the artefact is "
                       "returned (journal-before-release). Requires "
                       "the proposal_id and the confirm token bound "
                       "to its hash, plus a live mandate held by "
                       "the caller covering the product and the "
                       "issue operation class. Returns the licence "
                       "id, the artefact string, its hash, the "
                       "payload, and the journal receipt. A proposal "
                       "executes exactly once. This is the only "
                       "path that creates licences -- there is no "
                       "unjournalled bulk issue.",
        "inputSchema": _schema({
            "proposal_id": _PROPOSAL_ID,
            "confirm_token": _CONFIRM,
            **_CTX_TP}, required=("proposal_id", "confirm_token",
                                   "_tenant_id", "_principal_id")),
        "outputSchema": _out({"license_id": _S, "artefact": _S,
                              "artefact_hash": _S, "receipt": _O,
                              "payload": _O}),
        "annotations": _EXEC,
    },
    "license_renew": {
        "title": "Renew a licence (execute proposal)",
        "description": "Execute a renew proposal: mint a successor "
                       "licence carrying the renewed terms, linked "
                       "to the previous licence, which is marked "
                       "superseded. Requires the proposal_id, the "
                       "confirm token bound to its hash "
                       "(confirm-renew-...), and a live mandate "
                       "covering the product and the renew "
                       "operation class. Issuance is journalled "
                       "before the new artefact is returned. "
                       "Returns the new licence id, artefact, "
                       "hash, payload, and receipt. A proposal "
                       "executes exactly once.",
        "inputSchema": _schema({
            "proposal_id": _PROPOSAL_ID,
            "confirm_token": _CONFIRM,
            **_CTX_TP}, required=("proposal_id", "confirm_token",
                                   "_tenant_id", "_principal_id")),
        "outputSchema": _out({"license_id": _S, "artefact": _S,
                              "artefact_hash": _S, "receipt": _O,
                              "payload": _O}),
        "annotations": _EXEC_D,
    },
    "license_supersede": {
        "title": "Supersede or transfer a licence (execute proposal)",
        "description": "Execute a renew-kind proposal as a "
                       "supersede -- or, with transfer true, as a "
                       "transfer -- minting a successor licence "
                       "and marking the previous licence "
                       "superseded. Uses the supersede confirm "
                       "verb (confirm-supersede-...) even though "
                       "the proposal kind is renew, and requires a "
                       "live mandate covering the supersede (or "
                       "transfer) operation class for the product. "
                       "Issuance is journalled before the artefact "
                       "is returned. Returns the new licence id, "
                       "artefact, hash, payload, and receipt. A "
                       "proposal executes exactly once.",
        "inputSchema": _schema({
            "proposal_id": _PROPOSAL_ID,
            "confirm_token": _CONFIRM,
            "transfer": {"type": "boolean",
                         "description": "True executes as a "
                                        "transfer (transfer "
                                        "operation class and "
                                        "journal verb); false "
                                        "(default) as a "
                                        "supersede."},
            **_CTX_TP}, required=("proposal_id", "confirm_token",
                                   "_tenant_id", "_principal_id")),
        "outputSchema": _out({"license_id": _S, "artefact": _S,
                              "artefact_hash": _S, "receipt": _O,
                              "payload": _O}),
        "annotations": _EXEC_D,
    },
    "license_revoke": {
        "title": "Revoke a licence (execute proposal)",
        "description": "Execute a revoke proposal: journal the "
                       "revocation (with the proposal's reason) "
                       "and mark the licence revoked. Requires the "
                       "proposal_id, the confirm token bound to "
                       "its hash (confirm-revoke-...), and a live "
                       "mandate covering the product and the "
                       "revoke operation class. Revocation takes "
                       "the licence out of service; a licence "
                       "revoked under a payment that is later "
                       "reversed in the firm's favour can be "
                       "returned to service by license_reinstate "
                       "(the same licence, never a re-issue), and "
                       "licence deletion does not exist. Connected "
                       "clients see LICENSE_REVOKED at their next "
                       "check-in and the licence joins the signed "
                       "revocation list. Returns the licence id, "
                       "state LICENSE_REVOKED, and the journal "
                       "receipt.",
        "inputSchema": _schema({
            "proposal_id": _PROPOSAL_ID,
            "confirm_token": _CONFIRM,
            **_CTX_TP}, required=("proposal_id", "confirm_token",
                                   "_tenant_id", "_principal_id")),
        "outputSchema": _out({"license_id": _S, "state": _S,
                              "receipt": _O}),
        "annotations": _EXEC_D,
    },
    "license_reinstate": {
        "title": "Reinstate a revoked licence (execute proposal)",
        "description": "Execute a reinstate proposal: journal the "
                       "reinstatement -- linked to the revocation "
                       "it reverses by journal sequence and receipt "
                       "hash -- and mark the SAME licence active "
                       "again. No new licence is minted and the "
                       "original artefact, tier, seats and install "
                       "bindings are unchanged, so connected "
                       "clients see LICENSE_VALID at their next "
                       "check-in on their existing activation. "
                       "Requires the proposal_id, the confirm token "
                       "bound to its hash (confirm-reinstate-...), "
                       "and a live mandate covering the product and "
                       "the reinstate operation class. Execution "
                       "re-validates that the licence is still "
                       "revoked and not expired beyond its grace "
                       "window; anything else is refused and "
                       "logged. Returns the licence id, state "
                       "LICENSE_VALID, the journal receipt, and "
                       "the revocation sequence reversed. A "
                       "proposal executes exactly once.",
        "inputSchema": _schema({
            "proposal_id": _PROPOSAL_ID,
            "confirm_token": _CONFIRM,
            **_CTX_TP}, required=("proposal_id", "confirm_token",
                                   "_tenant_id", "_principal_id")),
        "outputSchema": _out({"license_id": _S, "state": _S,
                              "receipt": _O,
                              "revocation_sequence": _I}),
        "annotations": _EXEC,
    },
    "product_register": {
        "title": "Register a product",
        "description": "Register a product in the caller's tenant "
                       "so tiers can be defined and licences "
                       "issued for it. Tenant_owner only. The "
                       "registration is journalled. product_id "
                       "must be new to the tenant (re-registering "
                       "an existing id fails). custody records the "
                       "key-custody model for the product: "
                       "'witness' (the default -- the tenant holds "
                       "its signing keys and the platform stores "
                       "public keys only) or a custodial election "
                       "where the deployment supports it. Do this "
                       "before tier_define for the product.",
        "inputSchema": _schema({
            "product_id": {"type": "string",
                           "description": "New product id, unique "
                                          "within the tenant "
                                          "(required)."},
            "name": {"type": "string",
                     "description": "Display name; defaults to "
                                    "the product_id."},
            "custody": {"type": "string",
                        "description": "Key-custody model: "
                                       "'witness' (default) or "
                                       "'custodial'."},
            **_CTX_TP}, required=("product_id", "_tenant_id",
                                   "_principal_id")),
        "outputSchema": _out({"product_id": _S, "receipt": _O}),
        "annotations": _EXEC,
    },
    "tier_define": {
        "title": "Define a product tier (new version)",
        "description": "Define a tier for a registered product. "
                       "Tiers are versioned and never edited in "
                       "place: every call creates the next version "
                       "(previous max + 1) with its own journal "
                       "receipt, and returns that version. "
                       "Tenant_owner only; the product must already "
                       "be registered (see product_register). "
                       "Defaults: features [], seats 1, perpetual "
                       "false, term_days null (a term licence then "
                       "needs an explicit expires_at at proposal "
                       "time).",
        "inputSchema": _schema({
            "product_id": {"type": "string",
                           "description": "Registered product "
                                          "(required)."},
            "tier_id": {"type": "string",
                        "description": "Tier id within the "
                                       "product (required)."},
            "features": {"type": "array",
                         "description": "Feature list the tier "
                                        "grants (default [])."},
            "seats": {"type": "integer",
                      "description": "Default seat count for "
                                     "licences on this tier "
                                     "(default 1)."},
            "perpetual": {"type": "boolean",
                          "description": "True if the tier is "
                                         "perpetual by default."},
            "term_days": {"type": "integer",
                          "description": "Default term length in "
                                         "days for term licences "
                                         "on this tier."},
            **_CTX_TP}, required=("product_id", "tier_id",
                                   "_tenant_id", "_principal_id")),
        "outputSchema": _out({"product_id": _S, "tier_id": _S,
                              "version": _I, "receipt": _O}),
        "annotations": _EXEC,
    },
    "principal_manage": {
        "title": "Manage principals and mandates",
        "description": "Administer the tenant's principals and "
                       "mandates -- the only path that creates "
                       "either. Tenant_owner only; grants and "
                       "revocations are journalled. action "
                       "create_principal registers a principal "
                       "(principal_id + principal_class: "
                       "tenant_owner, issuer, support_reader, "
                       "auditor). action grant_mandate gives a "
                       "principal a mandate scoped to products "
                       "and operation classes until expires_at, "
                       "and returns the mandate_id. action "
                       "revoke_mandate revokes a mandate by id, "
                       "effective immediately. There is "
                       "deliberately no self-service mandate "
                       "escalation: mandate_self_grant is "
                       "denylisted and does not exist as a tool.",
        "inputSchema": _schema({
            "action": {"type": "string",
                       "description": "One of create_principal, "
                                      "grant_mandate, "
                                      "revoke_mandate "
                                      "(required)."},
            "principal_id": {"type": "string",
                             "description": "Principal the action "
                                            "targets (required "
                                            "for create_principal "
                                            "and grant_mandate)."},
            "principal_class": {"type": "string",
                                "description": "Class for "
                                               "create_principal: "
                                               "tenant_owner, "
                                               "issuer, "
                                               "support_reader, or "
                                               "auditor."},
            "name": {"type": "string",
                     "description": "Display name for "
                                    "create_principal."},
            "products": {"type": "array",
                         "description": "For grant_mandate: "
                                        "product ids the mandate "
                                        "covers ('*' covers all)."},
            "op_classes": {"type": "array",
                           "description": "For grant_mandate: "
                                          "operation classes "
                                          "covered, e.g. issue, "
                                          "renew, revoke, "
                                          "supersede, transfer, "
                                          "deactivate, reclaim."},
            "expires_at": {"type": "string",
                           "description": "For grant_mandate: "
                                          "ISO-8601 mandate "
                                          "expiry (required)."},
            "mandate_id": {"type": "string",
                           "description": "For revoke_mandate: "
                                          "mandate to revoke "
                                          "(required)."},
            **_CTX_TP}, required=("action", "_tenant_id",
                                   "_principal_id")),
        "outputSchema": _out({"principal_id": _S,
                              "principal_class": _S,
                              "mandate_id": _S, "receipt": _O}),
        "annotations": _EXEC_D,
    },
    "activation_deactivate": {
        "title": "Deactivate an activation (execute proposal)",
        "description": "Execute a deactivate proposal: journal "
                       "the deactivation and mark the activation "
                       "deactivated, freeing its seat immediately. "
                       "Requires the proposal_id, the confirm "
                       "token bound to its hash "
                       "(confirm-deactivate-...), and a live "
                       "mandate covering the product and the "
                       "deactivate operation class. The affected "
                       "install sees LICENSE_DEACTIVATED at its "
                       "next check-in. Returns the activation id, "
                       "state LICENSE_DEACTIVATED, and the "
                       "journal receipt. A proposal executes "
                       "exactly once.",
        "inputSchema": _schema({
            "proposal_id": _PROPOSAL_ID,
            "confirm_token": _CONFIRM,
            **_CTX_TP}, required=("proposal_id", "confirm_token",
                                   "_tenant_id", "_principal_id")),
        "outputSchema": _out({"activation_id": _S, "state": _S,
                              "receipt": _O}),
        "annotations": _EXEC_D,
    },
    "activation_reclaim_stale": {
        "title": "Reclaim stale activation seats",
        "description": "Reclaim seats held by stale activations: "
                       "every live activation in the tenant whose "
                       "last check-in is older than the reclaim "
                       "window (30 days by policy default) is "
                       "marked reclaimed, with a seat_reclaim "
                       "journal receipt per slot. Optionally "
                       "scoped to one product. Caller must be "
                       "tenant_owner or issuer AND hold a live "
                       "mandate covering the reclaim operation "
                       "class. Fresh activations are untouched, "
                       "and running it again reclaims nothing "
                       "further. Returns the reclaimed activation "
                       "ids and their count.",
        "inputSchema": _schema({
            "product_id": {"type": "string",
                           "description": "Optional: reclaim "
                                          "only within this "
                                          "product."},
            **_CTX_TP}, required=("_tenant_id", "_principal_id")),
        "outputSchema": _out({"reclaimed": _A, "count": _I}),
        "annotations": {"readOnlyHint": False,
                        "destructiveHint": True,
                        "idempotentHint": True,
                        "openWorldHint": False},
    },
}
