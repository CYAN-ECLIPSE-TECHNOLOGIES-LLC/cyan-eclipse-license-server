PROPRIETARY — CYAN ECLIPSE TECHNOLOGIES LLC · COMPANY INTELLECTUAL PROPERTY

# (INT — INTERNAL) BENCH REQUEST — DELTA: License Server host-path removal (ETO-93, Coding Standard §3.11)

Filed: 2026-11-14 · Slate: ETO-93 (tkt-09268d8ddfe2), Sweep Cure
Program WS-11 · Subject: cyan-eclipse-license-server @ commit
5a026f4e9539bcf3cb7baaa4598ec3fef36f0cc1 (one commit past the
census-bound 892e5de + the README-only fcc889e).
Repo (PRIVATE): https://github.com/CYAN-ECLIPSE-TECHNOLOGIES-LLC/cyan-eclipse-license-server
Origin: the Coding Standard checker census (2026-11-14) failed
§3.11 (CM-2) on this product: src/license_server/__main__.py:10
and :18 carried the literal default
"/home/witness/app-family/cyan-eclipse-license-server-runtime/"
— the PLU-17 host-path class, third instance, and the source
path the Plumb and Obscura copies fell back to. This delta
judges ONLY the host-path cure; the v1 core (PASS-WITH-FINDINGS),
web admin (PASS), redundancy (PASS-WITH-FINDINGS) and reinstate
pair verdicts are not re-opened.

## What is asked

Judge the removal of the host-path runtime default at source:
the runtime dir now resolves through proper mechanisms only —
(1) CETLIC_RUNTIME_DIR env override (explicit deployment
config; the systemd unit and the Dockerfile both set it, so the
deployed runtime location did not move); (2) the per-user state
root of the account running the server (Windows
%LOCALAPPDATA%\CyanEclipseLicenseServer · macOS
~/Library/Application Support/CyanEclipseLicenseServer · Linux
$XDG_STATE_HOME/cyan-eclipse-license-server, fallback
~/.local/state/cyan-eclipse-license-server). CETLIC_DB /
CETLIC_KEY_DIR still override the DB / key locations
individually. Delivered state claimed: BUILT + DEPLOYED +
PROOF-FILED, tenant-#1 fixture scope for the live exercise. No
production-posture claim beyond the deployed-service evidence
below is made by this filing.

## Claims to judge

- **HP-C1 — Literal gone at source and in the artefact.**
  src/license_server/__main__.py carries no host-specific
  absolute path (pre-cure sha256 386f4047… == the census record's
  artefact hash; cured sha256 a636706a…). The assembled shipped
  artefact (package + pyproject + README + LICENSE + Dockerfile
  + glama.json, zipped) scans clean against 11 host-path /
  internal-address / internal-hostname patterns, per member.
  Probes: re-run tests/test_no_host_paths.py::
  ShippedArtefactHostPathTest; grep the tree's src/ for
  /home/<user> patterns.
- **HP-C2 — Resolution mechanisms.** default_runtime_dir()
  resolves env-override-first on every platform, then the
  per-user state root (XDG_STATE_HOME / fallback, LOCALAPPDATA /
  fallback, Application Support); the resolved default is never
  a host-specific path and never inside the repo tree. Probes:
  RuntimeResolutionMechanismsTest (7 tests, hermetic);
  FreshProcessResolutionTest (fresh interpreter resolves the
  XDG root; --seed lands state.db under the env override only).
- **HP-C3 — Negative control.** With the pre-cure __main__.py
  restored (git stash), the battery fails 9/10 — the artefact
  scan naming src/license_server/__main__.py and the /home/…
  pattern, the fresh-process default returning the old literal.
  (The 1 pass is the seed-under-override leg: the env override
  mechanism pre-existed and is guarded, not new.) Probe: repeat
  the stash control.
- **HP-C4 — No collateral change.** The commit touches only
  __main__.py's docstring + resolution function and adds the
  test file; build_core / faces / core are byte-identical in
  behaviour. Full suite 89/89 OK (79 baseline + 10 new). The
  deployed service's journal chain continued across the deploy
  restart with chain_ok at every read (heads a3944245… pre →
  b024f0e2… post-health → a368da8a… post-fixture; counts are
  live estate traffic, the journal is shared with the estate's
  licence gates). Probes: git diff fcc889e..5a026f4; suite
  re-run; runtime status.json history.
- **HP-C5 — Deployed service on cured bytes.** systemctl
  restart 2026-11-15T00:00:26Z (PID 3312637 → 3654311); ops
  health_check exit 0 (unit_active, http_signed_list, chain_ok
  all true); the established fixture round trip
  (ops/e2e_fixture.py) passed every leg against the deployed
  service — issue → activate LICENSE_VALID → check-in VALID →
  revoke → check-in REVOKED, fixture licence
  4eb7565b-066e-4d9a-832a-c3716c1985df, exit 0. The web admin
  surface (which spawns the cured server as its MCP backend)
  renders its tenant overview. Shard T standby tree
  fast-forwarded to the same commit 5a026f4. Probes: re-run
  health_check.py + e2e_fixture.py; compare HEADs on both
  hosts and GitHub.

## Named gaps on the face of this request

- **Admin client instance (same class, outside the lane
  fence).** admin/mcp_client.py:42 carries the same literal as
  ITS default for CETLIC_RUNTIME_DIR. It is not a member of the
  shipped artefact (the pip package / Dockerfile ship
  src/license_server only; the checker's CM-2 manifest binds
  src/license_server/*.py), and WS-11's fence confined code
  changes to __main__.py + its helper + new tests, so it is
  enumerated here as a GAP for a follow-on lane, not cured.
  Mitigation of record: both deployed units (server + admin)
  set CETLIC_RUNTIME_DIR explicitly, so the admin default
  never fires in deployment; the admin also passes the value
  through to the server subprocess it spawns, which now
  resolves through the cured mechanisms if it were ever unset.
- **Version stays 0.1.0** while shipped bytes changed — follows
  the estate precedent for bench-delta cures at unreleased /
  delta scope (cf. Plumb PLU-16/PLU-17); a bump decision is the
  owner's/Verity's, not this lane's.
- **Fixture scope.** The live exercise used the established
  tenant-#1 fixture round trip (labelled fixture licence,
  revoked at the end of the run), per the lane's fence — no
  real tenant state was created or altered beyond the fixture's
  own journalled receipts.

## Out of scope for this bench

The v1 core, web admin, redundancy and reinstate verdicts (not
re-opened) · the duplicate-register crash (register E-36,
backlogged, not this lane) · transport catch-all shapes
(WS-5 / ETO-53 owns, if present) · the admin-client instance
above (follow-on lane) · any LIVE/certified claim for the cure
beyond the deployed-service evidence stated.

© Cyan Eclipse Technologies LLC — Proprietary · Company Intellectual Property
