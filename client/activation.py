"""Activation client for the thin HTTP face (SPEC S12.2/S12.4).

Check-in presents the activation token + artefact hash ONLY -- no usage
telemetry, no content, no file or project names (S7/S12.2).
"""
import json, urllib.request, urllib.error

class ActivationClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def _post(self, path, obj):
        req = urllib.request.Request(self.base_url + path,
                                     data=json.dumps(obj).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode())
            except Exception:
                return {"state": "LICENSE_SERVER_UNREACHABLE", "http_status": e.code}
        except Exception:
            return {"state": "LICENSE_SERVER_UNREACHABLE"}

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base_url + path, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return {"state": "LICENSE_SERVER_UNREACHABLE"}

    def activate(self, artefact, install_id, install_label=""):
        return self._post("/activate", {"artefact": artefact, "install_id": install_id,
                                        "install_label": install_label})

    def checkin(self, activation_token, artefact_hash):
        return self._post("/checkin", {"activation_token": activation_token,
                                       "artefact_hash": artefact_hash})

    def deactivate(self, activation_token, artefact_hash):
        return self._post("/deactivate", {"activation_token": activation_token,
                                          "artefact_hash": artefact_hash})

    def status(self, tenant_id, license_id):
        return self._get(f"/status?tenant_id={tenant_id}&license_id={license_id}")

    def verify(self, tenant_id, artefact, product_id=None):
        return self._post("/verify", {"tenant_id": tenant_id, "artefact": artefact,
                                      "product_id": product_id})

    def revocation_list(self, tenant_id, product_id=None):
        q = f"?tenant_id={tenant_id}"
        if product_id:
            q += f"&product_id={product_id}"
        return self._get("/revocation-list" + q)
