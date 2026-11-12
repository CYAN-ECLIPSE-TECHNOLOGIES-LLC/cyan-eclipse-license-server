"""Per-tenant append-only hash-chained issuance journal (SPEC S1.5).

receipt_hash = SHA-256(canonical receipt without receipt_hash).
chain_verify recomputes every link; chain_verify_anchored compares against a
caller-supplied anchor (the server holds NO anchor store) and labels a
verified-but-shorter chain as a possibly truncated prefix.
"""
from .util import canon, sha256_hex, now_iso
import json

GENESIS = "0" * 64
OPERATIONS = ["issue", "renew", "revoke", "supersede", "transfer", "product_register", "tier_define",
              "mandate_grant", "mandate_revoke", "key_rotate", "key_compromise", "activate", "deactivate", "seat_reclaim"]

class Journal:
    def __init__(self, store):
        self.store = store

    def head(self, tenant_id):
        r = self.store.q1("SELECT sequence, receipt_hash FROM journal WHERE tenant_id=? ORDER BY sequence DESC LIMIT 1", (tenant_id,))
        if not r:
            return {"sequence": 0, "head_hash": GENESIS, "genesis_hash": GENESIS}
        return {"sequence": r["sequence"], "head_hash": r["receipt_hash"], "genesis_hash": GENESIS}

    def count(self, tenant_id):
        r = self.store.q1("SELECT COUNT(*) AS c FROM journal WHERE tenant_id=?", (tenant_id,))
        return r["c"]

    def append(self, tenant_id, operation, actor=None, license_id=None, mandate_ref=None,
               proposal_hash=None, payload_hash=None, extra=None, timestamp=None):
        """Append inside the caller's transaction; caller commits. Raises on failure."""
        if operation not in OPERATIONS:
            raise ValueError(f"unknown journal operation: {operation}")
        h = self.head(tenant_id)
        seq = h["sequence"] + 1
        receipt = {"sequence": seq, "tenant_id": tenant_id, "operation": operation,
                   "license_id": license_id, "actor": actor, "mandate_ref": mandate_ref,
                   "proposal_hash": proposal_hash, "payload_hash": payload_hash,
                   "prev_hash": h["head_hash"], "timestamp": timestamp or now_iso(),
                   "extra": extra or {}}
        receipt["receipt_hash"] = sha256_hex(canon(receipt))
        self.store.x("INSERT INTO journal(tenant_id,sequence,operation,license_id,actor,mandate_ref,proposal_hash,payload_hash,prev_hash,receipt_hash,timestamp,extra) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (tenant_id, seq, operation, license_id, actor, mandate_ref, proposal_hash,
                      payload_hash, receipt["prev_hash"], receipt["receipt_hash"], receipt["timestamp"],
                      json.dumps(receipt["extra"], sort_keys=True)))
        return receipt

    def list_receipts(self, tenant_id, limit=100, offset=0):
        rows = self.store.q("SELECT * FROM journal WHERE tenant_id=? ORDER BY sequence LIMIT ? OFFSET ?", (tenant_id, limit, offset))
        return [self._row(r) for r in rows]

    def get_receipt(self, tenant_id, sequence):
        r = self.store.q1("SELECT * FROM journal WHERE tenant_id=? AND sequence=?", (tenant_id, sequence))
        return self._row(r) if r else None

    @staticmethod
    def _row(r):
        return {"sequence": r["sequence"], "tenant_id": r["tenant_id"], "operation": r["operation"],
                "license_id": r["license_id"], "actor": r["actor"], "mandate_ref": r["mandate_ref"],
                "proposal_hash": r["proposal_hash"], "payload_hash": r["payload_hash"],
                "prev_hash": r["prev_hash"], "receipt_hash": r["receipt_hash"],
                "timestamp": r["timestamp"], "extra": json.loads(r["extra"])}

    def verify(self, tenant_id):
        rows = self.store.q("SELECT * FROM journal WHERE tenant_id=? ORDER BY sequence", (tenant_id,))
        prev = GENESIS
        for i, r in enumerate(rows, start=1):
            rec = self._row(r)
            if rec["sequence"] != i:
                return {"ok": False, "failed_at": rec["sequence"], "reason": "sequence_gap", "count": len(rows), "head_hash": prev}
            if rec["prev_hash"] != prev:
                return {"ok": False, "failed_at": rec["sequence"], "reason": "prev_hash_mismatch", "count": len(rows), "head_hash": prev}
            body = {k: rec[k] for k in ("sequence", "tenant_id", "operation", "license_id", "actor", "mandate_ref", "proposal_hash", "payload_hash", "prev_hash", "timestamp", "extra")}
            if sha256_hex(canon(body)) != rec["receipt_hash"]:
                return {"ok": False, "failed_at": rec["sequence"], "reason": "receipt_hash_mismatch", "count": len(rows), "head_hash": prev}
            prev = rec["receipt_hash"]
        return {"ok": True, "count": len(rows), "head_hash": prev, "genesis_hash": GENESIS}

    def verify_anchored(self, tenant_id, anchor_hash, anchor_sequence=None):
        v = self.verify(tenant_id)
        if not v["ok"]:
            return {**v, "anchored": False, "label": "CHAIN_INVALID"}
        if v["head_hash"] == anchor_hash:
            return {**v, "anchored": True, "label": "ANCHORED_MATCH"}
        if anchor_sequence is not None and v["count"] < anchor_sequence:
            return {**v, "anchored": False, "label": "TRUNCATED_PREFIX_POSSIBLE",
                    "note": "local chain verifies but is shorter than the anchored head: possibly truncated prefix"}
        return {**v, "anchored": False, "label": "ANCHOR_MISMATCH"}
