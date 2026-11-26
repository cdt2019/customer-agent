"""访客令牌：代表「这个浏览器、这个身份」，短期有效。只有店铺自己能解开，客服服务原样带回。"""

import base64
import hashlib
import hmac
import json
import time


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign(secret: str, who: str, browser: str, minutes: int) -> str:
    body = _b64(json.dumps({"who": who, "browser": browser, "exp": int(time.time()) + minutes * 60}).encode())
    return f"{body}.{_b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())}"


def read(secret: str, token: str) -> str | None:
    """令牌有效时返回身份（guest / member-a / member-b），否则返回空。"""
    body, _, mac = token.partition(".")
    expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(mac, expected):
        return None
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    return claims["who"] if claims["exp"] > time.time() else None
