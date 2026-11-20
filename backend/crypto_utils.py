"""Fernet encryption for BYOK keys, derived from JWT_SECRET."""
import base64
import hashlib
from cryptography.fernet import Fernet
from config import JWT_SECRET

_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(JWT_SECRET.encode()).digest()))


def encrypt(plain: str) -> str:
    return _fernet.encrypt(plain.encode()).decode() if plain else ""


def decrypt(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode() if token else ""
