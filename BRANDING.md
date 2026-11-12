# Branding — Cyan Eclipse License Server

Recorded at creation (2026-11-12) per the firm's new-app branding default.
Source system: Eclipse Brand System v1.2 (`eclipse-brand-system.md`).

## Name / wordmark

- Product name: **Cyan Eclipse License Server**
- Firm: **Cyan Eclipse Technologies LLC**
- Tagline: **Provenance. Governance. Proof.**
- Wordmark text treatment (web lockup form, per brand system §5.2):
  `CYAN ECLIPSE TECHNOLOGIES` with ECLIPSE in cyan (`--cyan`); product
  surfaces pair the product name with the powered-by line
  `**Powered by Cyan Eclipse Technologies** — https://cetech.ai`
  in the README header (line 3 position) and the closing line.

## Theme tokens (brand system §4, canonical)

| Token | Value | Role |
|---|---|---|
| `--bg` | `#0d1b2a` | base surface (navy) |
| `--bg2` | `#080c14` | alt sections / footer |
| `--cyan` | `#0ff6f7` | primary accent |
| `--blue` | `#00d4ff` | links, secondary accent |
| `--purple` | `#7b2cbf` | gradient terminus only |
| `--grad` | `linear-gradient(90deg,#0ff6f7,#00d4ff,#7b2cbf)` | accents / wordmarks only, never body text or content fills |
| `--text` / `--muted` | `#fefefe` / `#a0aec0` | body text on navy |

Dark surfaces only (P1). System font stack on web surfaces (P4).

## Identity surfaces present in v1 core

- **README** — product name, tagline, powered-by header + closing lines.
- **Package metadata** — `pyproject.toml`: name
  `cyan-eclipse-license-server`, description carrying name + tagline.
- **`policy_show` identity block** — the MCP `policy_show` tool returns
  `{product, vendor, powered_by, tagline, status, activation_model}`
  (see `license_server.core.IDENTITY`).
- **Client package docstring** — carries the product attribution and the
  model-(B) honesty note.

## Surface state (honest, v1 core)

- **Icon: NONE.** No icon has been drawn, generated, or placeholdered.
  Icon election is the owner's individual act and an Icongate
  PASS/MARGINAL verdict is required before any ship (Icongate law).
- **Splash / launch / UI: NO SURFACE.** v1 core is a server + client
  library; there is no GUI, splash, or web UI surface to brand. If a UI
  surface is ever built, the tokens above and the brand §9 gate apply
  before it ships.
- **Status label:** `In development · bench pending` (brand system §8 V1
  closed set). No seal is displayed: no bench card exists (S3).
