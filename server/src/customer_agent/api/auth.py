"""管理后台的登录：一个管理员账号，密码在环境变量里。登录后发一个签过名的 cookie，后台接口都先过这里。

签名的钥匙由密码经 scrypt 派生：改了密码，之前的登录全部失效；拿到 cookie 也没法快速离线猜密码。
猜密码：每次失败等 1 秒；15 分钟内全站失败 10 次就暂停登录（计数在进程里，只跑一个进程）。
"""

import base64
import hashlib
import hmac
import json
import time
from collections import deque
from functools import lru_cache
from threading import Lock

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel

from customer_agent import settings

COOKIE = "admin_session"
SESSION_DAYS = 7

MAX_FAILURES = 10
LOCK_SECONDS = 15 * 60

router = APIRouter(prefix="/api")
_failures: deque[float] = deque()
_failures_lock = Lock()


@lru_cache(maxsize=1)
def _key_for(password: str) -> bytes:
    return hashlib.scrypt(password.encode(), salt=b"customer-agent/admin-session", n=2**14, r=8, p=1, dklen=32)


def _key() -> bytes:
    return _key_for(settings.ADMIN_PASSWORD)


def _too_many_failures(now: float, failed: bool = False) -> bool:
    """记一次失败（failed）并返回现在是不是该暂停登录。"""
    with _failures_lock:
        while _failures and _failures[0] <= now - LOCK_SECONDS:
            _failures.popleft()
        if failed:
            _failures.append(now)
        return len(_failures) >= MAX_FAILURES


def _sign(body: str) -> str:
    return base64.urlsafe_b64encode(hmac.new(_key(), body.encode(), hashlib.sha256).digest()).decode().rstrip("=")


def issue(username: str, now: float | None = None) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"u": username, "exp": int((now or time.time()) + SESSION_DAYS * 86400)}).encode()).decode()
    return f"{body}.{_sign(body)}"


def verify(token: str, now: float | None = None) -> str | None:
    """有效时返回用户名。"""
    body, _, mac = token.partition(".")
    if not settings.ADMIN_PASSWORD or not hmac.compare_digest(mac, _sign(body)):
        return None
    claims = json.loads(base64.urlsafe_b64decode(body))
    return claims["u"] if claims["exp"] > (now or time.time()) else None


def require_admin(admin_session: str = Cookie(default="")) -> str:
    if not settings.ADMIN_PASSWORD:
        raise HTTPException(503, "后台密码没有配置：请设置环境变量 ADMIN_PASSWORD")
    username = verify(admin_session) if admin_session else None
    if username is None:
        raise HTTPException(401, "请先登录")
    return username


class LoginIn(BaseModel):
    username: str
    password: str


class MeOut(BaseModel):
    username: str


@router.post("/login")
def login(body: LoginIn, response: Response) -> MeOut:
    if not settings.ADMIN_PASSWORD:
        raise HTTPException(503, "后台密码没有配置：请设置环境变量 ADMIN_PASSWORD")
    if _too_many_failures(time.time()):
        raise HTTPException(429, "密码试错太多次，15 分钟后再试")
    right_user = hmac.compare_digest(body.username, settings.ADMIN_USER)
    right_password = hmac.compare_digest(body.password, settings.ADMIN_PASSWORD)
    if not (right_user and right_password):
        _too_many_failures(time.time(), failed=True)
        time.sleep(1)
        raise HTTPException(401, "账号或密码不对")
    response.set_cookie(COOKIE, issue(body.username), max_age=SESSION_DAYS * 86400, httponly=True, samesite="strict", secure=settings.ADMIN_COOKIE_SECURE)
    return MeOut(username=body.username)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE)


@router.get("/me")
def me(admin_session: str = Cookie(default="")) -> MeOut:
    return MeOut(username=require_admin(admin_session))
