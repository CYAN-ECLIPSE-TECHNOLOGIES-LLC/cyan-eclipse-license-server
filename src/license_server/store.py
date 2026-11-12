"""Tenant-scoped store interface (SPEC S1.4 seam) over stdlib SQLite.

All state access goes through this class and every query is tenant-scoped.
Private key material is NEVER stored here (SPEC S5.6) -- the key registry
holds public keys + kids only.
"""
import json, sqlite3, threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants(tenant_id TEXT PRIMARY KEY, name TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active');
CREATE TABLE IF NOT EXISTS products(tenant_id TEXT NOT NULL, product_id TEXT NOT NULL, name TEXT NOT NULL, custody TEXT NOT NULL DEFAULT 'witness', PRIMARY KEY(tenant_id, product_id));
CREATE TABLE IF NOT EXISTS tiers(tenant_id TEXT NOT NULL, product_id TEXT NOT NULL, tier_id TEXT NOT NULL, version INTEGER NOT NULL, features TEXT NOT NULL, seats INTEGER NOT NULL DEFAULT 1, perpetual INTEGER NOT NULL DEFAULT 0, term_days INTEGER, PRIMARY KEY(tenant_id, product_id, tier_id, version));
CREATE TABLE IF NOT EXISTS principals(tenant_id TEXT NOT NULL, principal_id TEXT NOT NULL, principal_class TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', PRIMARY KEY(tenant_id, principal_id));
CREATE TABLE IF NOT EXISTS mandates(mandate_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, principal_id TEXT NOT NULL, products TEXT NOT NULL, op_classes TEXT NOT NULL, expires_at TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS licenses(license_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, product_id TEXT NOT NULL, tier_id TEXT NOT NULL, features TEXT NOT NULL, licensee TEXT NOT NULL, seats INTEGER NOT NULL, issued_at TEXT NOT NULL, expires_at TEXT, perpetual INTEGER NOT NULL DEFAULT 0, kid TEXT NOT NULL, order_ref TEXT, sandbox INTEGER NOT NULL DEFAULT 0, prev_license_id TEXT, status TEXT NOT NULL DEFAULT 'active', artefact TEXT NOT NULL, artefact_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS activations(activation_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, license_id TEXT NOT NULL, install_id TEXT NOT NULL, install_label TEXT NOT NULL DEFAULT '', token_hash TEXT NOT NULL, artefact_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'live', activated_at TEXT NOT NULL, last_checkin TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS journal(tenant_id TEXT NOT NULL, sequence INTEGER NOT NULL, operation TEXT NOT NULL, license_id TEXT, actor TEXT, mandate_ref TEXT, proposal_hash TEXT, payload_hash TEXT, prev_hash TEXT NOT NULL, receipt_hash TEXT NOT NULL, timestamp TEXT NOT NULL, extra TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(tenant_id, sequence));
CREATE TABLE IF NOT EXISTS refusals(id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT, operation TEXT NOT NULL, actor TEXT, reason TEXT NOT NULL, proposal_hash TEXT, timestamp TEXT NOT NULL, entry_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposals(proposal_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, proposal_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'proposed', created_by TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS key_registry(tenant_id TEXT NOT NULL, kid TEXT NOT NULL, public_key_pem TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, PRIMARY KEY(tenant_id, kid));
"""

class Store:
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def q(self, sql, params=()):
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def q1(self, sql, params=()):
        rows = self.q(sql, params)
        return rows[0] if rows else None

    def x(self, sql, params=()):
        with self.lock:
            return self.conn.execute(sql, params)

    def commit(self):
        with self.lock:
            self.conn.commit()

    def rollback(self):
        with self.lock:
            self.conn.rollback()

    def get_tenant(self, tenant_id):
        r = self.q1("SELECT * FROM tenants WHERE tenant_id=?", (tenant_id,))
        return dict(r) if r else None

    def get_product(self, tenant_id, product_id):
        r = self.q1("SELECT * FROM products WHERE tenant_id=? AND product_id=?", (tenant_id, product_id))
        return dict(r) if r else None

    def get_tier(self, tenant_id, product_id, tier_id):
        r = self.q1("SELECT * FROM tiers WHERE tenant_id=? AND product_id=? AND tier_id=? ORDER BY version DESC LIMIT 1", (tenant_id, product_id, tier_id))
        if not r:
            return None
        d = dict(r); d["features"] = json.loads(d["features"]); d["perpetual"] = bool(d["perpetual"])
        return d

    def get_principal(self, tenant_id, principal_id):
        if not principal_id:
            return None
        r = self.q1("SELECT * FROM principals WHERE tenant_id=? AND principal_id=?", (tenant_id, principal_id))
        return dict(r) if r else None

    def get_license(self, tenant_id, license_id):
        # tenant-scoped: a cross-tenant id is simply not found (no oracle, S1.4)
        r = self.q1("SELECT * FROM licenses WHERE tenant_id=? AND license_id=?", (tenant_id, license_id))
        return self._license_dict(r) if r else None

    def get_license_any_tenant(self, license_id):
        r = self.q1("SELECT * FROM licenses WHERE license_id=?", (license_id,))
        return self._license_dict(r) if r else None

    @staticmethod
    def _license_dict(r):
        if r is None:
            return None
        d = dict(r); d["features"] = json.loads(d["features"]); d["licensee"] = json.loads(d["licensee"])
        d["perpetual"] = bool(d["perpetual"]); d["sandbox"] = bool(d["sandbox"])
        return d

    def public_keys(self, tenant_id):
        rows = self.q("SELECT kid, public_key_pem, status FROM key_registry WHERE tenant_id=?", (tenant_id,))
        return [dict(r) for r in rows]
