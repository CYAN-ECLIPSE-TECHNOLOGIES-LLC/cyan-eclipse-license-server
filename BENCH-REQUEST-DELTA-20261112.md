PROPRIETARY — CYAN ECLIPSE TECHNOLOGIES LLC · COMPANY INTELLECTUAL PROPERTY

# (IP — PROPRIETARY IP) BENCH REQUEST — License Server v1 core (new build, model (B))

Filed: 2026-11-12 · Slate: ETO-18 (build) · ETO-25 (bench prep)
Subject: **cyan-eclipse-license-server v1 core @ `3b48cc0c081fd7766bcf3484394bb858a5e32233`**
Repo (PRIVATE): https://github.com/CYAN-ECLIPSE-TECHNOLOGIES-LLC/cyan-eclipse-license-server
Build home: Shard E `/home/witness/app-family/cyan-eclipse-license-server/` (GitHub == droplet verified at filing)
Spec: `~/workspace/cyan-eclipse/license-server-20261112/SPEC.md` **as amended** — Amendment S12 (owner ruling 2026-11-12 13:09 PT: activation model (B)) controls wherever it conflicts with S1–S11.
Build record: `~/workspace/cyan-eclipse/license-server-20261112/BUILD-RECORD-20261112.md`

## What is asked

Judge the v1 licensing core against the amended SPEC. This is a NEW-BUILD bench (not a re-bench delta on a judged subject): MCP licensing core (27 tools: S1.3 surface + S12.4 seat/activation admin tools; tier floors; 9-item denylist refused and absent from `tools/list`) · per-tenant hash-chained issuance journal · `.cetlic` Ed25519 artefact · mandate-gated propose→confirm issuance · model-(B) activation + seat registry · thin HTTP runtime face (shared handlers) · client authenticity + activation library · tenant-#1 fixture seed (Parity/Loom/Plumb products; NO integration into the real apps).

Bench gate kept: **BENCHED ≠ LIVE.** Nothing is deployed (no service, no public listener; the HTTP face ran localhost-only in tests), no external tenant exists, and no claim in this request asserts more than "built + builder-tested". The verdict is the bench's.

## Claims to judge

- **C1 — Journal battery.** Per-tenant SHA-256 hash chain verifies end-to-end; a mutated receipt fails verification at the tampered link; anchored verify works with a caller-supplied anchor (no anchor store); a truncated chain is labelled possibly-truncated, never silently verified. Journal-before-release: a lifecycle operation whose journal write fails issues nothing.
- **C2 — Artefact battery.** `.cetlic` envelope carries the S2.2 fields exactly; Ed25519 verify follows the S2.3 order (parse → kid → signature → product → clock → expiry) mapping to the S2.4 named states; mutating any single field (tier / seats / expiry / licensee) fails verification.
- **C3 — Mandate battery.** Issuance succeeds only with a valid in-scope unexpired mandate + a confirm token bound to the proposal hash (`confirm-<verb>-<proposal_id>-<hash12>`); no-mandate / wrong-scope / expired attempts and wrong-token executions are refused, each refusal receipted, and no artefact exists for any refused attempt.
- **C4 — Seat + activation battery (model (B), S12.2/S12.3).** A seat is a live activation slot: activation at cap is refused `LICENSE_SEAT_LIMIT`; deactivation frees a slot immediately; revocation is effective at the next check-in and blocks new activations; an activation stale past the reclaim window (30 d) is reclaimable and its later check-in returns `LICENSE_DEACTIVATED`; check-in presents activation token + artefact hash only (no usage telemetry); client-side offline-window logic (72 h → `LICENSE_SUSPENDED_OFFLINE`; inside window `LICENSE_SERVER_UNREACHABLE` with features continuing) behaves per S12.3.
- **C5 — Tenant isolation.** Cross-tenant reads/mutations are refused and receipted; a cross-tenant `license_id` lookup returns `unknown`, not exists-elsewhere (no enumeration oracle).
- **C6 — Dual-face contract parity.** Identical cases through the MCP face and the HTTP face produce identical outcomes (verify · activate · check-in at minimum); the face contains no logic of its own.
- **C7 — Denylist enforcement.** `license_delete`, `journal_append` (direct), `journal_rewrite`, `key_export_private`, `key_generate_for_tenant`, `mandate_self_grant`, `bulk_issue_unjournalled`, `status_override_silent`, `activation_delete` are refused at the protocol layer and absent from `tools/list` for non-admin callers.
- **C8 — Key custody posture.** Tenant #1's signing private key exists only in a locked 0600 file outside the repo and outside the DB (verify by inspection of the repo tree + store); rotation journals `key_rotate` and never invalidates in-term licences signed under the retired kid.

## Builder evidence (not a verdict)

- Test suite: `PYTHONPATH=src:. python3 -m unittest discover -s tests` on Shard E — **61 passed / 0 failed**, independently re-run by the commissioning lane after the final commit (journal 7 · artefact 10 · mandate 8 · seats 8 · tenant isolation 7 · faces 8 · client offline 7 · lifecycle 6).
- MCP stdio smoke against the seeded runtime: 27 tools listed; `chain_verify` ok over the seeded tenant-#1 journal.
- Parity: droplet HEAD == `git ls-remote` HEAD == `3b48cc0…`; working tree clean; pre-push grep: no `.pem`/`.key`/private-key material in tracked files.

## Named gap on the face of this request

SPEC §S12.5 **OPEN GAP — DISCONNECTED / AIR-GAPPED OPERATION**: model (B) as ruled cannot activate in an air-gapped environment and v1 contains no offline activation path, exception mechanism, or fallback — by owner ruling, not by build omission. Judge the build as ruled; the gap itself is an owner-ruling matter recorded on the spec, not a defect claim against the build.

## Out of scope for this bench

Parity/Loom app integrations (ETO-21/ETO-22, not built) · external tenant onboarding (v2, ETO-24) · witness-mode tenant issuance flow (v2) · any production deployment or availability claim for the activation path (S12.3 posture is a build-and-operations requirement, unproven until a deployment bench) · pricing (none exists; pricing-intel pass still owed).

© Cyan Eclipse Technologies LLC — Proprietary · Company Intellectual Property
