"""浏览器的身份：cookie 记着当前模拟身份和浏览器编号。真店铺里这一步是登录。"""

import secrets

from fastapi import Request, Response

from demo_shop import store


def current(request: Request) -> tuple[str, str]:
    """返回 (身份, 浏览器编号)。"""
    who = request.cookies.get("who", "guest")
    return (who if who in store.IDENTITIES else "guest"), request.cookies.get("browser", "")


def ensure_browser(request: Request, response: Response) -> str:
    browser = request.cookies.get("browser") or secrets.token_urlsafe(12)
    response.set_cookie("browser", browser, max_age=90 * 86400, httponly=True, samesite="lax")
    return browser
