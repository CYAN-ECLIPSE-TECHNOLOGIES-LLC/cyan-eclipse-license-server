"""Client library for Cyan Eclipse License Server (SPEC S2.3 + S12).

Honesty note (S12.2/S12.6): offline verification in this package proves
artefact AUTHENTICITY only. Under activation model (B) authenticity is
necessary, not sufficient -- entitlement to run paid features additionally
requires a live activation in good standing with the licence service.
"""
from .verify import verify_offline
from .state import ClientSession
from .activation import ActivationClient

__all__ = ["verify_offline", "ClientSession", "ActivationClient"]
