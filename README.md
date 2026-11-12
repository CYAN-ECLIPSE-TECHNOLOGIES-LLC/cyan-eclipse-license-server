# Cyan Eclipse License Server

**Powered by Cyan Eclipse Technologies** — https://cetech.ai

**Provenance. Governance. Proof.**

Cyan Eclipse License Server is the firm's licensing system of record: an
MCP-native core that registers products and versioned tiers, issues signed
`.cetlic` licence artefacts (Ed25519 over canonical JSON) under a
propose → mandate-confirm flow, records every lifecycle operation in a
per-tenant append-only hash-chained issuance journal, and — under the
owner-ruled activation model (B) — runs online activation with real-time
seat control: a seat is a live activation slot, check-ins carry an
activation token and artefact hash only (no usage telemetry), revocation
takes effect at the next check-in, and a bounded 72-hour offline window
separates a transient outage from suspension.

Status: **In development · bench pending** — v1 core built 2026-11-12
(Slate ETO-18). Nothing here is certified, deployed, or live. The HTTP
face binds localhost in tests only; there is no production listener.

## Layout

- `src/license_server/` — the core (store, journal, artefact, keys),
  the MCP stdio server, the thin HTTP face, and the tenant-#1 seed.
- `client/` — the client library: offline artefact **authenticity**
  verification (SPEC S2.3 steps 1–6) plus an activation client and the
  model-(B) client state logic. Honest limit, stated in the package
  itself: offline authenticity ≠ entitlement to run — under (B),
  entitlement additionally requires a live activation in good standing.
- `tests/` — the unittest battery (journal chain, artefact mutation,
  mandate gate, seat cap, revocation propagation, stale reclaim,
  cross-tenant isolation, HTTP↔core parity, client offline states).

## Use

```
PYTHONPATH=src python3 -m license_server --seed     # seed tenant #1 (Cyan Eclipse)
PYTHONPATH=src python3 -m license_server            # MCP server on stdio
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Runtime state (SQLite DB + signing keys) lives OUTSIDE the repo tree in
`cyan-eclipse-license-server-runtime/` beside the build home: the signing
private key is a locked 0600 file in a 0700 directory, never in git,
never in the DB (the key registry holds public keys + kids only).

## Policy defaults (as coded, published by `policy_show`)

heartbeat 4 h · offline window 72 h · reclaim window 30 d · expiry grace 14 d.

## Standing notes

- Tenant #1 is seeded with products `parity` / `loom` / `plumb` and their
  SPEC tiers as fixture-grade wiring readiness only — no integration into
  the actual apps in v1 core.
- Per the firm's new-app branding default, branding is applied at
  creation (see `BRANDING.md`); this product's icon is **not** invented
  here: icon election is the owner's act and is pending, gated by Icongate.
- Known open gap, on the record (SPEC S12.5): model (B) cannot activate
  in disconnected / air-gapped environments; v1 contains no offline
  activation path and no fallback. Owner ruling owed.

A Cyan Eclipse Technologies product. The "Powered by Cyan Eclipse Technologies" attribution travels with it.
