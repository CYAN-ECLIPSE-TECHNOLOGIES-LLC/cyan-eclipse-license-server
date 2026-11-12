"""Tenant signing-key store (SPEC S5.6).

Private keys live ONLY in locked files (0600) inside a 0700 directory
OUTSIDE the repo tree and outside the DB. This module never returns private
key material to callers of the core; it signs in-process.
"""
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

class KeyStore:
    def __init__(self, key_dir):
        self.key_dir = key_dir

    def _path(self, kid):
        return os.path.join(self.key_dir, f"{kid}.pem")

    def exists(self, kid):
        return os.path.exists(self._path(kid))

    def generate(self, kid):
        """Create a new keypair file (0600) in a 0700 dir. Returns public PEM."""
        os.makedirs(self.key_dir, mode=0o700, exist_ok=True)
        try:
            os.chmod(self.key_dir, 0o700)
        except OSError:
            pass
        if self.exists(kid):
            raise FileExistsError(f"key already exists: {kid}")
        priv = Ed25519PrivateKey.generate()
        pem = priv.private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())
        fd = os.open(self._path(kid), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, pem)
        finally:
            os.close(fd)
        os.chmod(self._path(kid), 0o600)
        return self.public_pem(kid)

    def _load_private(self, kid):
        with open(self._path(kid), "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)

    def public_pem(self, kid):
        priv = self._load_private(kid)
        return priv.public_key().public_bytes(serialization.Encoding.PEM,
                                              serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")

    def sign(self, kid, data: bytes) -> bytes:
        return self._load_private(kid).sign(data)

def public_key_from_pem(pem: str):
    return serialization.load_pem_public_key(pem.encode("ascii"))

def verify_signature(public_pem: str, signature: bytes, data: bytes) -> bool:
    try:
        public_key_from_pem(public_pem).verify(signature, data)
        return True
    except Exception:
        return False
