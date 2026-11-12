"""Licence artefact (.cetlic) -- SPEC S2.

Envelope: base64url(canonical payload) + "." + base64url(Ed25519 signature).
kid and v live INSIDE the signed payload. Verification steps 1-6 (S2.3) are
the offline AUTHENTICITY path; under model (B) a passing artefact is
necessary, not sufficient -- entitlement also needs a live activation (S12.2).
"""
import json
from datetime import timedelta
from .util import canon, b64u, b64u_decode, sha256_hex, parse_iso, utcnow
from .keys import verify_signature

GRACE_DAYS = 14

def make_envelope(payload: dict, sign_fn) -> str:
    body = canon(payload)
    sig = sign_fn(body)
    return b64u(body) + "." + b64u(sig)

def parse_envelope(artefact: str):
    """Returns (payload_dict, payload_bytes, signature_bytes) or raises ValueError."""
    if not isinstance(artefact, str) or artefact.count(".") != 1:
        raise ValueError("envelope shape")
    a, b = artefact.split(".")
    body = b64u_decode(a)
    sig = b64u_decode(b)
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("payload not an object")
    if canon(payload) != body:
        raise ValueError("payload not canonical")
    return payload, body, sig

def artefact_hash(artefact: str) -> str:
    _, body, _ = parse_envelope(artefact)
    return sha256_hex(body)

def verify_authenticity(artefact, trusted_keys, expected_tenant=None, expected_product=None,
                        now=None, anchor_time=None):
    """S2.3 steps 1-6. trusted_keys: {kid: public_pem}. Returns named state dict."""
    now = now or utcnow()
    try:
        payload, body, sig = parse_envelope(artefact)
    except Exception:
        return {"state": "LICENSE_MALFORMED", "payload": None}
    if payload.get("v") != 1:
        return {"state": "LICENSE_MALFORMED", "payload": payload}
    kid = payload.get("kid")
    if not kid or kid not in trusted_keys:
        return {"state": "LICENSE_UNKNOWN_KEY", "payload": payload}
    if not verify_signature(trusted_keys[kid], sig, body):
        return {"state": "LICENSE_BAD_SIGNATURE", "payload": payload}
    if expected_product is not None and payload.get("product_id") != expected_product:
        return {"state": "LICENSE_WRONG_PRODUCT", "payload": payload,
                "actual_product": payload.get("product_id")}
    if expected_tenant is not None and payload.get("tenant_id") != expected_tenant:
        return {"state": "LICENSE_WRONG_PRODUCT", "payload": payload,
                "actual_product": payload.get("product_id")}
    issued = parse_iso(payload.get("issued_at"))
    if issued and now < issued - timedelta(hours=24):
        return {"state": "LICENSE_CLOCK_SUSPECT", "payload": payload}
    if anchor_time is not None:
        anchor = parse_iso(anchor_time) if isinstance(anchor_time, str) else anchor_time
        if now < anchor - timedelta(hours=48):
            return {"state": "LICENSE_CLOCK_SUSPECT", "payload": payload}
    if not payload.get("perpetual") and payload.get("expires_at"):
        exp = parse_iso(payload["expires_at"])
        if now > exp:
            if now <= exp + timedelta(days=GRACE_DAYS):
                return {"state": "LICENSE_GRACE", "payload": payload}
            return {"state": "LICENSE_EXPIRED", "payload": payload}
    return {"state": "LICENSE_VALID", "payload": payload}
