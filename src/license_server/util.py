import base64, hashlib, json
from datetime import datetime, timezone, timedelta

def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def hash_obj(obj) -> str:
    return sha256_hex(canon(obj))

def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def b64u_decode(s: str) -> bytes:
    if not isinstance(s, str):
        raise ValueError("not a string")
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii") + pad.encode("ascii"))

def now_iso(dt=None):
    dt = dt or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_iso(s):
    if s is None:
        return None
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

def utcnow():
    return datetime.now(timezone.utc)

def add_days(dt, days):
    return dt + timedelta(days=days)
