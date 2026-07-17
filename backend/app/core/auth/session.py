from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


class SessionSigner:
    def __init__(self, secret_key: str, ttl_minutes: int):
        self.secret_key = secret_key.encode("utf-8")
        self.ttl_seconds = ttl_minutes * 60

    def sign(self, payload: dict[str, Any]) -> str:
        body = dict(payload)
        body["iat"] = int(time.time())
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        token_body = _b64url_encode(raw)
        signature = hmac.new(self.secret_key, token_body.encode("ascii"), hashlib.sha256).digest()
        return f"{token_body}.{_b64url_encode(signature)}"

    def unsign(self, token: str) -> dict[str, Any] | None:
        try:
            token_body, signature_raw = token.split(".", 1)
            expected = hmac.new(self.secret_key, token_body.encode("ascii"), hashlib.sha256).digest()
            actual = _b64url_decode(signature_raw)
            if not hmac.compare_digest(expected, actual):
                return None
            payload = json.loads(_b64url_decode(token_body).decode("utf-8"))
            if int(time.time()) - int(payload.get("iat", 0)) > self.ttl_seconds:
                return None
            return payload
        except Exception:
            return None
