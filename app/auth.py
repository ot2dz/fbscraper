# -*- coding: utf-8 -*-
"""Cookie session auth based on the ADMIN_PASSWORD env variable."""
import hashlib
import hmac
import time

from fastapi import Request

from app.config import ADMIN_PASSWORD, secret_key

COOKIE_NAME = "fbscraper_session"
SESSION_TTL = 7 * 24 * 3600


def verify_password(password: str) -> bool:
    return hmac.compare_digest(password or "", ADMIN_PASSWORD)


def _sign(payload: str) -> str:
    return hmac.new(secret_key().encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_session() -> str:
    payload = str(int(time.time()) + SESSION_TTL)
    return f"{payload}.{_sign(payload)}"


def is_logged_in(request: Request) -> bool:
    raw = request.cookies.get(COOKIE_NAME, "")
    if "." not in raw:
        return False
    payload, signature = raw.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(payload)):
        return False
    try:
        return int(payload) > time.time()
    except ValueError:
        return False
