"""Cyan Eclipse License Server — web admin (SPEC S1.7, secondary surface).

Powered by Cyan Eclipse Technologies — https://cetech.ai
Provenance. Governance. Proof.

The web admin is an MCP CLIENT of the License Server core: every datum
it renders comes from a T0 (read) MCP tool call over the server's stdio
face. The web layer holds no database, journal or key-store access and
offers no writes — v1 is read-only; lifecycle writes remain on the MCP
tool surface (propose -> mandate-confirm), exactly as SPEC S1.7 rules
("all writes route through the same T2 MCP tools").

Access posture v1: firm-side only. The process binds loopback on the
host that runs the service; there is no public listener and no tenant
access (external tenant-admin access is the v2 onboarding scope).
"""
