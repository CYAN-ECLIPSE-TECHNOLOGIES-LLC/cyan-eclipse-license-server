"""Model-(B) client state logic (SPEC S12.3).

States: NOT_ACTIVATED / SEAT_LIMIT / DEACTIVATED come from activation
attempts; SERVER_UNREACHABLE = check-in failing INSIDE the offline window
(paid features continue); SUSPENDED_OFFLINE = window lapsed (paid features
suspend; existing work stays readable + exportable). One successful
check-in restores full paid function immediately.
"""
from datetime import timedelta

class ClientSession:
    def __init__(self, offline_window_hours=72):
        self.offline_window = timedelta(hours=offline_window_hours)
        self.activated = False
        self.deactivated = False
        self.seat_limit = False
        self.last_successful_checkin = None
        self.server_state = None  # last licence state reported by the server

    def on_activation_result(self, result, now):
        state = result.get("state")
        if state in ("LICENSE_VALID", "LICENSE_GRACE"):
            self.activated = True
            self.deactivated = False
            self.seat_limit = False
            self.server_state = state
            self.last_successful_checkin = now
            return state
        if state == "LICENSE_SEAT_LIMIT":
            self.seat_limit = True
            return "LICENSE_SEAT_LIMIT"
        if state == "LICENSE_DEACTIVATED":
            self.deactivated = True
            self.activated = False
            return "LICENSE_DEACTIVATED"
        return state or "LICENSE_NOT_ACTIVATED"

    def on_checkin_result(self, result, now):
        state = result.get("state")
        if state == "LICENSE_DEACTIVATED":
            self.deactivated = True
            self.activated = False
            return state
        self.server_state = state
        self.last_successful_checkin = now
        return state

    def evaluate(self, now, checkin_reachable=True):
        """Current named state + what may run, given connectivity right now."""
        if self.deactivated:
            return {"state": "LICENSE_DEACTIVATED", "paid_features": False, "read_export": True}
        if not self.activated:
            return {"state": "LICENSE_SEAT_LIMIT" if self.seat_limit else "LICENSE_NOT_ACTIVATED",
                    "paid_features": False, "read_export": True}
        if self.server_state in ("LICENSE_REVOKED", "LICENSE_EXPIRED", "LICENSE_SUPERSEDED"):
            return {"state": self.server_state, "paid_features": False, "read_export": True}
        if checkin_reachable:
            return {"state": self.server_state or "LICENSE_VALID", "paid_features": True, "read_export": True}
        # check-in failing: bounded offline window from last successful check-in
        if self.last_successful_checkin is None or now - self.last_successful_checkin <= self.offline_window:
            return {"state": "LICENSE_SERVER_UNREACHABLE", "paid_features": True, "read_export": True}
        return {"state": "LICENSE_SUSPENDED_OFFLINE", "paid_features": False, "read_export": True}
