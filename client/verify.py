"""Offline artefact AUTHENTICITY verification (SPEC S2.3 steps 1-6).

Zero network. Maps to the S2.4 named states. Under model (B) this does NOT
by itself entitle an app to run paid features -- see package docstring.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from license_server.artefact import verify_authenticity  # noqa: E402

def verify_offline(artefact, trusted_keys, expected_tenant, expected_product, now=None, anchor_time=None):
    """trusted_keys: {kid: public_key_pem} for the expected tenant."""
    return verify_authenticity(artefact, trusted_keys, expected_tenant=expected_tenant,
                               expected_product=expected_product, now=now, anchor_time=anchor_time)
