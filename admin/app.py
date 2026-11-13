"""Cyan Eclipse License Server — web admin surface (SPEC S1.7).

Server-rendered, stdlib-only. Every figure on every view is read at
render time from the deployed core through the MCP client
(admin.mcp_client); the web layer computes nothing from raw store data
and caches nothing between requests.

Views (SPEC S1.7): tenant overview · licence search + inspect ·
journal head + chain verify result · revocation list state.
Read-mostly per spec: v1 offers NO writes. Lifecycle writes remain on
the MCP tool surface (propose -> mandate-confirm, tier-gated in the
core). Any non-GET request is refused 405.

Access posture v1: binds 127.0.0.1 only, beside the service on Shard E.
Reached by firm operators over the host's own access controls (SSH
tunnel). No public listener, no tenant access — tenant-admin access is
the v2 onboarding scope (Slate ETO-24).

Branding: Eclipse Brand System tokens as recorded in the product's
BRANDING.md (navy base, cyan accent, gradient for accents only, system
font stack, dark surfaces only). The product name is carried in full
composite form on every view. Status label is the brand §8 closed-set
label for this product: "In development · bench pending".
"""
import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

from .mcp_client import McpClient, McpError

PRODUCT = "Cyan Eclipse License Server"
TAGLINE = "Provenance. Governance. Proof."
STATUS_LABEL = "In development · bench pending"
DEFAULT_PORT = 8798

TENANTS = [t.strip() for t in
           os.environ.get("CETLIC_ADMIN_TENANTS", "cet").split(",")
           if t.strip()]
LABELS = {}
for pair in os.environ.get("CETLIC_ADMIN_TENANT_LABELS", "").split(";"):
    if "=" in pair:
        k, v = pair.split("=", 1)
        LABELS[k.strip()] = v.strip()
PRINCIPAL = os.environ.get("CETLIC_ADMIN_PRINCIPAL", "cet-owner")


def esc(x):
    return html.escape("" if x is None else str(x))


def tenant_label(tenant):
    return LABELS.get(tenant, tenant)


# ---------------------------------------------------------------- data
class AdminData:
    """One method per view; all data via T0 MCP tools, nothing else."""

    def __init__(self, client, tenants=None, principal=PRINCIPAL):
        self.client = client
        self.tenants = tenants or TENANTS
        self.principal = principal

    def _t(self, name, args, tenant):
        return self.client.tool(name, args, tenant=tenant,
                                principal=self.principal)

    def overview(self):
        out = []
        for tenant in self.tenants:
            pol = self._t("policy_show", {}, tenant)
            lics = self._t("license_list", {}, tenant)
            acts = self._t("activation_list", {}, tenant)
            jinfo = self._t("journal_info", {}, tenant)
            verify = self._t("chain_verify", {}, tenant)
            rev = self._t("revocation_list_get", {}, tenant)
            by_state = {}
            seats = 0
            for lic in lics.get("licenses", []):
                by_state[lic.get("state")] = \
                    by_state.get(lic.get("state"), 0) + 1
                seats += lic.get("seats") or 0
            live = sum(1 for a in acts.get("activations", [])
                       if a.get("status") == "live")
            out.append({
                "tenant": tenant, "label": tenant_label(tenant),
                "identity": pol.get("identity", {}),
                "policy": pol.get("policy", {}),
                "kids": pol.get("kids_in_force", []),
                "licences": lics.get("count", 0), "by_state": by_state,
                "seats_total": seats, "activations_live": live,
                "activations_total": acts.get("count", 0),
                "journal": jinfo, "verify": verify,
                "revoked": len(rev.get("revoked", [])),
            })
        return out

    def licences(self, tenant, product=None, state=None, q=None):
        args = {}
        if product:
            args["product_id"] = product
        if state:
            args["state"] = state
        res = self._t("license_list", args, tenant)
        rows = res.get("licenses", [])
        if q:
            needle = q.lower()
            def hit(lic):
                lee = lic.get("licensee") or {}
                fields = [lic.get("license_id", ""), lic.get("order_ref") or "",
                          lee.get("name", ""), lee.get("email", "")]
                return any(needle in f.lower() for f in fields)
            rows = [r for r in rows if hit(r)]
        products = sorted({r.get("product_id") for r in
                           self._t("license_list", {}, tenant)
                           .get("licenses", [])})
        states = sorted({r.get("state") for r in
                         self._t("license_list", {}, tenant)
                         .get("licenses", [])})
        return {"rows": rows, "count": len(rows),
                "surface": res.get("surface"), "products": products,
                "states": states}

    def licence_detail(self, tenant, license_id):
        ins = self._t("license_inspect", {"license_id": license_id}, tenant)
        if ins.get("state") == "LICENSE_UNKNOWN":
            return None
        usage = self._t("seat_usage", {"license_id": license_id}, tenant)
        status = self._t("license_status", {"license_id": license_id},
                         tenant)
        return {"license": ins.get("license", {}),
                "receipts": ins.get("receipts", []),
                "usage": usage, "status": status}

    def journal(self, tenant, offset=0, limit=25):
        jinfo = self._t("journal_info", {}, tenant)
        verify = self._t("chain_verify", {}, tenant)
        lst = self._t("journal_list", {"limit": limit, "offset": offset},
                      tenant)
        return {"info": jinfo, "verify": verify,
                "receipts": lst.get("receipts", []),
                "offset": offset, "limit": limit}

    def revocations(self, tenant):
        return self._t("revocation_list_get", {}, tenant)


# ---------------------------------------------------------------- chrome
CSS = """
:root{--bg:#0d1b2a;--bg2:#080c14;--cyan:#0ff6f7;--blue:#00d4ff;
--purple:#7b2cbf;--grad:linear-gradient(90deg,#0ff6f7,#00d4ff,#7b2cbf);
--text:#fefefe;--muted:#a0aec0;--line:rgba(255,255,255,.09);
--card:rgba(255,255,255,.03)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",
Roboto,"Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--blue);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1060px;margin:0 auto;padding:28px 22px 48px}
header.site{border-bottom:1px solid var(--line);padding-bottom:16px;
margin-bottom:8px}
.wordmark{font-size:13px;letter-spacing:.22em;color:var(--muted)}
.wordmark b{color:var(--text);font-weight:600}
.wordmark .ecl{color:var(--cyan)}
h1.product{font-size:26px;font-weight:650;margin:8px 0 2px}
.tagline{color:var(--muted);font-size:14px}
.chip{display:inline-block;font-size:12px;color:var(--cyan);
border:1px solid rgba(15,246,247,.4);border-radius:999px;
padding:2px 10px;margin-left:10px;vertical-align:2px}
.scope{margin:14px 0 4px;font-size:13px;color:var(--muted);
background:var(--bg2);border:1px solid var(--line);border-radius:10px;
padding:9px 13px}
nav.main{display:flex;gap:6px;margin:16px 0 22px;flex-wrap:wrap}
nav.main a{color:var(--text);padding:7px 14px;border-radius:999px;
border:1px solid var(--line);font-size:14px}
nav.main a.on{background:var(--cyan);color:#06202b;border-color:var(--cyan);
font-weight:600}
.card{background:var(--card);border:1px solid var(--line);
border-radius:14px;padding:18px 20px;margin:0 0 18px}
.card h2{font-size:17px;margin:0 0 4px;font-weight:620}
.card h3{font-size:14px;margin:16px 0 6px;color:var(--cyan);
font-weight:600;letter-spacing:.02em}
.sub{color:var(--muted);font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
gap:12px;margin:14px 0 4px}
.stat{background:var(--bg2);border:1px solid var(--line);
border-radius:12px;padding:12px 14px}
.stat .n{font-size:23px;font-weight:650}
.stat .k{font-size:12px;color:var(--muted);margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:8px 0}
th{ text-align:left;color:var(--muted);font-weight:600;font-size:12px;
letter-spacing:.04em;text-transform:uppercase;padding:7px 9px;
border-bottom:1px solid var(--line)}
td{padding:7px 9px;border-bottom:1px solid rgba(255,255,255,.05);
vertical-align:top}
tr:hover td{background:rgba(255,255,255,.02)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
font-size:12.5px;word-break:break-all}
.pill{display:inline-block;font-size:11.5px;border-radius:999px;
padding:1px 9px;border:1px solid var(--line);color:var(--muted)}
.pill.ok{color:var(--cyan);border-color:rgba(15,246,247,.45)}
.pill.bad{color:#ff7b93;border-color:rgba(255,123,147,.5)}
.pill.warn{color:#ffd479;border-color:rgba(255,212,121,.5)}
form.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:end;
margin:6px 0 4px}
form.filters label{font-size:12px;color:var(--muted);display:block;
margin-bottom:4px}
input,select{background:var(--bg2);color:var(--text);
border:1px solid var(--line);border-radius:9px;padding:8px 11px;
font-size:14px}
button{background:var(--cyan);color:#06202b;border:0;border-radius:9px;
padding:9px 16px;font-size:14px;font-weight:600;cursor:pointer}
.err{background:rgba(255,123,147,.08);border:1px solid rgba(255,123,147,.4);
border-radius:12px;padding:14px 16px;font-size:14px}
pre.artefact{background:var(--bg2);border:1px solid var(--line);
border-radius:10px;padding:12px;overflow:auto;max-height:220px;
font-size:11.5px;white-space:pre-wrap;word-break:break-all}
footer.site{margin-top:30px;border-top:1px solid var(--line);
padding-top:14px;color:var(--muted);font-size:12.5px}
.rule{height:3px;border-radius:2px;background:var(--grad);
margin:14px 0 0;opacity:.85}
.pager{display:flex;gap:14px;font-size:13.5px;margin-top:8px}
"""


def page(title, active, body):
    nav = "".join(
        f'<a href="{href}"{" class=\"on\"" if key == active else ""}>'
        f'{label}</a>'
        for key, href, label in (
            ("overview", "/", "Overview"),
            ("licences", "/licenses", "Licences"),
            ("journal", "/journal", "Journal"),
            ("revocations", "/revocations", "Revocations")))
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · {esc(PRODUCT)} — Web Admin</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<header class="site">
<div class="wordmark">CYAN <span class="ecl">ECLIPSE</span> TECHNOLOGIES</div>
<h1 class="product">{esc(PRODUCT)} — Web Admin
<span class="chip">{esc(STATUS_LABEL)}</span></h1>
<div class="tagline">{esc(TAGLINE)}</div>
<div class="rule"></div>
<div class="scope">Firm-side admin · loopback only · tenant #1 fixture
scope · read-only — every figure is read live from the License Server's
MCP tools; lifecycle writes stay on the MCP tool surface.</div>
<nav class="main">{nav}</nav>
</header>
{body}
<footer class="site">Powered by Cyan Eclipse Technologies —
https://cetech.ai · {esc(PRODUCT)} · Web admin per SPEC S1.7 (MCP
client; no direct store access) · © Cyan Eclipse Technologies LLC —
Proprietary · Company Intellectual Property</footer>
</div></body></html>"""


def state_pill(state):
    cls = {"LICENSE_VALID": "ok", "LICENSE_REVOKED": "bad",
           "LICENSE_GRACE": "warn", "LICENSE_EXPIRED": "bad",
           "LICENSE_SUPERSEDED": "warn"}.get(state, "")
    return f'<span class="pill {cls}">{esc(state or "—")}</span>'


def verify_pill(verify):
    if verify.get("ok"):
        return '<span class="pill ok">CHAIN VERIFIED</span>'
    return ('<span class="pill bad">CHAIN INVALID — '
            f'{esc(verify.get("reason", "unknown"))} at '
            f'{esc(verify.get("failed_at", "—"))}</span>')


def error_page(title, active, msg):
    return page(title, active,
                f'<div class="err">The License Server refused or could '
                f'not answer this view: {esc(msg)}<br><span class="sub">'
                f'Nothing is cached or invented here — the surface shows '
                f'only what the MCP tools return.</span></div>')


# ---------------------------------------------------------------- views
def render_overview(data):
    cards = []
    for t in data.overview():
        ident = t["identity"]
        states = " · ".join(
            f'{esc(k.replace("LICENSE_", ""))} {v}'
            for k, v in sorted(t["by_state"].items())) or "none"
        pol_rows = "".join(
            f'<tr><td>{esc(k)}</td><td class="mono">{esc(v)}</td></tr>'
            for k, v in sorted(t["policy"].items()))
        cards.append(f"""
<div class="card">
<h2>Tenant {esc(t["tenant"])} — {esc(t["label"])}</h2>
<div class="sub">{esc(ident.get("product", PRODUCT))} · activation model
{esc(ident.get("activation_model", "—"))}</div>
<div class="grid">
<div class="stat"><div class="n">{t["licences"]}</div>
<div class="k">licences ({states})</div></div>
<div class="stat"><div class="n">{t["seats_total"]}</div>
<div class="k">seats granted</div></div>
<div class="stat"><div class="n">{t["activations_live"]} /
{t["activations_total"]}</div><div class="k">activations live</div></div>
<div class="stat"><div class="n">{t["revoked"]}</div>
<div class="k">revoked licences</div></div>
<div class="stat"><div class="n">{esc(t["journal"].get("sequence", 0))}</div>
<div class="k">journal receipts</div></div>
</div>
<h3>Journal head + verification</h3>
<table><tr><th>Head sequence</th><th>Head hash</th><th>Chain</th></tr>
<tr><td>{esc(t["journal"].get("sequence"))}</td>
<td class="mono">{esc(t["journal"].get("head_hash"))}</td>
<td>{verify_pill(t["verify"])}</td></tr></table>
<h3>Signing keys in force</h3>
<div>{", ".join(f'<span class="pill">{esc(k)}</span>' for k in t["kids"]) or "—"}</div>
<h3>Policy (as published by policy_show)</h3>
<table>{pol_rows}</table>
</div>""")
    return page("Tenant overview", "overview", "".join(cards))


def _tenant_picker(data, tenant, base):
    links = " · ".join(
        f'<a href="{base}?tenant={quote(t)}">{esc(t)}</a>'
        if t != tenant else f"<b>{esc(t)}</b>" for t in data.tenants)
    return f'<div class="sub">Tenant: {links}</div>' if len(
        data.tenants) > 1 else ""


def render_licences(data, tenant, product=None, state=None, q=None):
    res = data.licences(tenant, product, state, q)
    rows = []
    for lic in res["rows"]:
        lee = lic.get("licensee") or {}
        who = esc(lee.get("name", ""))
        if lee.get("email"):
            who += f'<br><span class="sub">{esc(lee["email"])}</span>'
        exp = "perpetual" if lic.get("perpetual") else esc(
            lic.get("expires_at") or "—")
        rows.append(f"""<tr>
<td class="mono"><a href="/license/{quote(lic['license_id'])}?tenant={quote(tenant)}">{esc(lic['license_id'])}</a></td>
<td>{esc(lic.get("product_id"))} / {esc(lic.get("tier_id"))}</td>
<td>{who}</td><td>{esc(lic.get("seats"))}</td>
<td>{state_pill(lic.get("state"))}</td>
<td>{esc(lic.get("issued_at"))}</td><td>{exp}</td>
<td class="mono">{esc(lic.get("order_ref") or "—")}</td></tr>""")
    prod_opts = "".join(
        f'<option{" selected" if p == product else ""}>{esc(p)}</option>'
        for p in res["products"])
    state_opts = "".join(
        f'<option{" selected" if s == state else ""}>{esc(s)}</option>'
        for s in res["states"])
    body = f"""
<div class="card"><h2>Licence search — tenant {esc(tenant)}</h2>
{_tenant_picker(data, tenant, "/licenses")}
<div class="sub">{res["count"]} licence(s) · surface:
{esc(res.get("surface"))} (SPEC S1.7 masking: owner surface shows the
full licencee; the support surface masks)</div>
<form class="filters" method="get" action="/licenses">
<input type="hidden" name="tenant" value="{esc(tenant)}">
<div><label>Product</label><select name="product">
<option value="">all</option>{prod_opts}</select></div>
<div><label>State</label><select name="state">
<option value="">all</option>{state_opts}</select></div>
<div><label>Text (id, licencee, order ref)</label>
<input name="q" value="{esc(q or "")}" size="26"></div>
<button type="submit">Search</button></form>
<table><tr><th>Licence</th><th>Product / tier</th><th>Licencee</th>
<th>Seats</th><th>State</th><th>Issued</th><th>Expires</th>
<th>Order ref</th></tr>{''.join(rows) or
'<tr><td colspan="8">No licences match.</td></tr>'}</table></div>"""
    return page("Licence search", "licences", body)


def render_licence_detail(data, tenant, license_id):
    d = data.licence_detail(tenant, license_id)
    if d is None:
        return page("Licence not found", "licences",
                    '<div class="err">LICENSE_UNKNOWN — no such licence '
                    'in this tenant.</div>')
    lic, usage = d["license"], d["usage"]
    lee = lic.get("licensee") or {}
    feats = lic.get("features")
    if isinstance(feats, str):
        try:
            feats = ", ".join(json.loads(feats))
        except Exception:
            pass
    elif isinstance(feats, (list, tuple)):
        feats = ", ".join(str(x) for x in feats)
    fields = [
        ("Licence id", lic.get("license_id")), ("Tenant", lic.get("tenant_id")),
        ("Product / tier", f'{lic.get("product_id")} / {lic.get("tier_id")}'),
        ("State", None), ("Status (record)", lic.get("status")),
        ("Licencee", f'{lee.get("name", "")} <{lee.get("email", "")}>'),
        ("Seats", lic.get("seats")), ("Issued", lic.get("issued_at")),
        ("Expires", "perpetual" if lic.get("perpetual")
         else lic.get("expires_at")),
        ("Signing key", lic.get("kid")), ("Order ref", lic.get("order_ref")),
        ("Sandbox", "yes" if lic.get("sandbox") else "no"),
        ("Previous licence", lic.get("prev_license_id")),
        ("Features", feats),
        ("Artefact hash", lic.get("artefact_hash")),
    ]
    rows = "".join(
        f'<tr><td>{esc(k)}</td><td>'
        + (state_pill(lic.get("state")) if k == "State"
           else f'<span class="mono">{esc(v)}</span>' if k in
           ("Artefact hash", "Licence id") else esc(v))
        + "</td></tr>" for k, v in fields)
    acts = "".join(
        f'<tr><td class="mono">{esc(a.get("install_id"))}</td>'
        f'<td>{esc(a.get("install_label"))}</td>'
        f'<td>{esc(a.get("status"))}</td>'
        f'<td>{esc(a.get("activated_at"))}</td>'
        f'<td>{esc(a.get("last_checkin"))}</td></tr>'
        for a in usage.get("activations", []))
    recs = "".join(
        f'<tr><td>{esc(r.get("sequence"))}</td>'
        f'<td>{esc(r.get("timestamp"))}</td>'
        f'<td>{esc(r.get("operation"))}</td>'
        f'<td>{esc(r.get("actor"))}</td>'
        f'<td class="mono">{esc((r.get("receipt_hash") or "")[:16])}…</td></tr>'
        for r in d["receipts"])
    body = f"""
<div class="card"><h2>Licence {esc(license_id)}</h2>
<div class="sub">Tenant {esc(tenant)} ·
<a href="/licenses?tenant={quote(tenant)}">back to search</a></div>
<table>{rows}</table>
<h3>Artefact (.cetlic)</h3>
<pre class="artefact">{esc(lic.get("artefact"))}</pre>
<h3>Seats — {esc(usage.get("live_count"))} live of
{esc(usage.get("seats_cap"))} granted</h3>
<table><tr><th>Install</th><th>Label</th><th>Status</th>
<th>Activated</th><th>Last check-in</th></tr>
{acts or '<tr><td colspan="5">No activations.</td></tr>'}</table>
<h3>Journal receipts for this licence</h3>
<table><tr><th>Seq</th><th>Time</th><th>Operation</th><th>Actor</th>
<th>Receipt</th></tr>{recs or
'<tr><td colspan="5">No receipts.</td></tr>'}</table></div>"""
    return page(f"Licence {license_id}", "licences", body)


def render_journal(data, tenant, offset=0):
    j = data.journal(tenant, offset)
    info, verify = j["info"], j["verify"]
    recs = "".join(
        f'<tr><td>{esc(r.get("sequence"))}</td>'
        f'<td>{esc(r.get("timestamp"))}</td>'
        f'<td>{esc(r.get("operation"))}</td>'
        f'<td class="mono">{esc(r.get("license_id") or "—")}</td>'
        f'<td>{esc(r.get("actor") or "—")}</td>'
        f'<td class="mono">{esc((r.get("receipt_hash") or "")[:16])}…</td></tr>'
        for r in j["receipts"])
    prev_off = max(0, offset - j["limit"])
    next_off = offset + j["limit"]
    pager = f'<a href="/journal?tenant={quote(tenant)}&offset={prev_off}">← earlier</a>' \
        if offset else '<span class="sub">← earlier</span>'
    pager += (f' · <a href="/journal?tenant={quote(tenant)}&offset={next_off}">later →</a>'
              if len(j["receipts"]) == j["limit"] else "")
    body = f"""
<div class="card"><h2>Journal — tenant {esc(tenant)}</h2>
{_tenant_picker(data, tenant, "/journal")}
<table><tr><th>Receipts</th><th>Head sequence</th><th>Head hash</th>
<th>Genesis</th><th>Chain verification (chain_verify)</th></tr>
<tr><td>{esc(info.get("count"))}</td><td>{esc(info.get("sequence"))}</td>
<td class="mono">{esc(info.get("head_hash"))}</td>
<td class="mono">{esc((info.get("genesis_hash") or "")[:16])}…</td>
<td>{verify_pill(verify)} <span class="sub">over
{esc(verify.get("count"))} receipts</span></td></tr></table>
<h3>Receipts (sequence order)</h3>
<table><tr><th>Seq</th><th>Time</th><th>Operation</th><th>Licence</th>
<th>Actor</th><th>Receipt hash</th></tr>
{recs or '<tr><td colspan="6">No receipts.</td></tr>'}</table>
<div class="pager">{pager}</div></div>"""
    return page("Journal", "journal", body)


def render_revocations(data, tenant):
    rev = data.revocations(tenant)
    rows = "".join(
        f'<tr><td class="mono"><a href="/license/{quote(r["license_id"])}'
        f'?tenant={quote(tenant)}">{esc(r["license_id"])}</a></td>'
        f'<td>{esc(r.get("product_id"))}</td></tr>'
        for r in rev.get("revoked", []))
    body = f"""
<div class="card"><h2>Revocation list — tenant {esc(tenant)}</h2>
{_tenant_picker(data, tenant, "/revocations")}
<div class="sub">The signed revocation list exactly as published by
revocation_list_get (SPEC S2.6/S12.6). Connected apps take revocation
state from check-in; this list is the published audit artefact.</div>
<table><tr><th>Generated at</th><th>Signing key</th><th>Signature</th>
<th>Revoked licences</th></tr>
<tr><td>{esc(rev.get("generated_at"))}</td>
<td class="mono">{esc(rev.get("kid"))}</td>
<td>{'<span class="pill ok">SIGNED</span>' if rev.get("signature")
else '<span class="pill warn">UNSIGNED</span>'}</td>
<td>{len(rev.get("revoked", []))}</td></tr></table>
<table><tr><th>Licence</th><th>Product</th></tr>
{rows or '<tr><td colspan="2">No revoked licences.</td></tr>'}</table>
</div>"""
    return page("Revocation list", "revocations", body)


# ---------------------------------------------------------------- http
def make_handler(data):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep stdout clean
            pass

        def _send(self, code, body, ctype="text/html; charset=utf-8"):
            raw = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _tenant(self, qs):
            t = (qs.get("tenant") or [data.tenants[0]])[0]
            return t if t in data.tenants else data.tenants[0]

        def do_GET(self):
            u = urlparse(self.path)
            qs = parse_qs(u.query)
            tenant = self._tenant(qs)
            try:
                if u.path == "/":
                    self._send(200, render_overview(data))
                elif u.path == "/licenses":
                    self._send(200, render_licences(
                        data, tenant,
                        product=(qs.get("product") or [None])[0],
                        state=(qs.get("state") or [None])[0],
                        q=(qs.get("q") or [None])[0]))
                elif u.path.startswith("/license/"):
                    lid = unquote(u.path[len("/license/"):])
                    self._send(200, render_licence_detail(data, tenant, lid))
                elif u.path == "/journal":
                    off = int((qs.get("offset") or ["0"])[0])
                    self._send(200, render_journal(data, tenant, off))
                elif u.path == "/revocations":
                    self._send(200, render_revocations(data, tenant))
                elif u.path == "/healthz":
                    self._send(200, "ok\n", "text/plain; charset=utf-8")
                else:
                    self._send(404, page("Not found", "",
                                         '<div class="err">No such view.'
                                         '</div>'))
            except McpError as e:
                active = {"": "overview"}.get(u.path.strip("/"),
                                              u.path.strip("/"))
                self._send(200, error_page("Service error", active, str(e)))
            except Exception as e:  # noqa: BLE001 — render, never crash
                self._send(500, error_page("Error", "", f"{type(e).__name__}: {e}"))

        def _no_write(self):
            self._send(405, page(
                "Read-only", "",
                '<div class="err">Method not allowed. The web admin is '
                'read-only in v1 (SPEC S1.7, read-mostly): lifecycle '
                'writes route through the License Server\'s T2 MCP '
                'tools under their mandate gates — there is no write '
                'path in this web layer.</div>'))

        do_POST = _no_write
        do_PUT = _no_write
        do_DELETE = _no_write
        do_PATCH = _no_write

    return Handler


def main(port=None):
    port = int(port or os.environ.get("CETLIC_ADMIN_PORT", DEFAULT_PORT))
    client = McpClient()
    data = AdminData(client)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(data))
    print(f"{PRODUCT} web admin on http://127.0.0.1:{port} "
          f"(loopback, firm-side, MCP client of the deployed core)",
          flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
