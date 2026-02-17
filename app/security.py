"""Webhook signature validation helpers."""

from __future__ import annotations

import hashlib
import hmac


def verify_hmac_signature(payload: bytes, signature: str | None, secret: str | None) -> bool:
    if not secret:
        return True
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
