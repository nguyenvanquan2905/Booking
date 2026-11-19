"""PII encryption (AES-GCM), deterministic lookup hashing, and log masking (MVP-83)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from collections.abc import Mapping
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)\d(?:[\s.-]?\d){7,10}(?!\d)")
_BEARER_RE = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-~+/]+=*")
_LONG_DIGITS_RE = re.compile(r"(?<!\d)\d{12,19}(?!\d)")

_SENSITIVE_KEYS = frozenset(
    {
        "phone",
        "customer_phone",
        "email",
        "customer_email",
        "name",
        "customer_name",
        "full_name",
        "password",
        "token",
        "api_key",
        "secret",
        "cookie",
        "cookies",
        "storage_state",
        "authorization",
    }
)


def mask_phone(phone: str) -> str:
    """Mask phone number keeping only prefix and last 4 digits."""
    cleaned = phone.strip()
    if len(cleaned) <= 4:
        return "***"
    prefix_len = 4 if cleaned.startswith("+") else 3
    if len(cleaned) <= prefix_len + 4:
        return cleaned[:1] + "***" + cleaned[-2:]
    return f"{cleaned[:prefix_len]}***{cleaned[-4:]}"


def mask_email(email: str) -> str:
    """Mask email local-part while preserving domain."""
    cleaned = email.strip()
    if "@" not in cleaned:
        return "***"
    local, domain = cleaned.split("@", 1)
    if len(local) <= 1:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def mask_name(name: str) -> str:
    """Mask each word of a person's name to initial + '***'."""
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "***"
    return " ".join(f"{part[0]}***" for part in parts)


def redact_pii_in_text(text: str) -> str:
    """Redact phone numbers, emails, bearer tokens, and 12-19 digit IDs/cards in free text."""
    redacted = _EMAIL_RE.sub(lambda m: mask_email(m.group(0)), text)
    redacted = _PHONE_RE.sub(lambda m: mask_phone(m.group(0)), redacted)
    redacted = _BEARER_RE.sub(r"\1 ***", redacted)
    redacted = _LONG_DIGITS_RE.sub(lambda m: f"{m.group(0)[:2]}***{m.group(0)[-4:]}", redacted)
    return redacted


def redact_pii_in_dict(data: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively mask known PII keys and redact free-text PII patterns."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        lowered = key.lower()
        if isinstance(value, Mapping):
            result[key] = redact_pii_in_dict(value)
        elif isinstance(value, list):
            result[key] = [
                redact_pii_in_dict(item)
                if isinstance(item, Mapping)
                else (redact_pii_in_text(item) if isinstance(item, str) else item)
                for item in value
            ]
        elif lowered in _SENSITIVE_KEYS and isinstance(value, str):
            if "phone" in lowered:
                result[key] = mask_phone(value)
            elif "email" in lowered:
                result[key] = mask_email(value)
            elif "name" in lowered:
                result[key] = mask_name(value)
            else:
                result[key] = "***REDACTED***"
        elif isinstance(value, str):
            result[key] = redact_pii_in_text(value)
        else:
            result[key] = value
    return result


class PiiCipher:
    """AES-256-GCM cipher and HMAC-SHA256 lookup hasher for PII storage."""

    _PREFIX = "enc:v1:"

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("PII encryption secret must not be empty")
        self._key = hashlib.sha256(secret.encode("utf-8")).digest()
        self._aesgcm = AESGCM(self._key)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        token = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"{self._PREFIX}{token}"

    def decrypt(self, payload: str) -> str:
        if not payload.startswith(self._PREFIX):
            raise ValueError("Unsupported encrypted PII payload format")
        raw = base64.urlsafe_b64decode(payload[len(self._PREFIX) :].encode("ascii"))
        nonce, ciphertext = raw[:12], raw[12:]
        plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")

    def hash_value(self, value: str) -> str:
        normalized = value.strip().lower().encode("utf-8")
        return hmac.new(self._key, normalized, hashlib.sha256).hexdigest()
