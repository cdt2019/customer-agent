"""不靠提示词、由代码保证的规矩。"""

import re

MASK = "••••••"
MAX_MESSAGE_CHARS = 4000  # 硬上限，挡住超大的请求；实际上限在后台设置里（service_settings.max_message_chars）
MAX_TOOL_ROUNDS = 3  # 一轮对话最多调几次工具

_LABEL = r"(密码|验证码|卡密|口令|password|passwd|token|access_?token|session)"
_SECRETS = [
    re.compile(r"eyJ[\w-]{6,}(?:\.[\w-]+)*"),  # JWT，登录凭证常见的样子
    re.compile(rf'{_LABEL}("?\s*(?:是|为|:|：|=)\s*"?)[^\s"，。,一-鿿]{{4,}}', re.I),  # 值不含中文，「密码是多少」不算
    re.compile(rf"{_LABEL}(\s+)(?=[^\s一-鿿]*\d)[^\s一-鿿]{{4,}}", re.I),  # 值里要有数字，「session token」这种说法不算
]
_CLAIMS_HANDOFF = re.compile(r"已(?:经)?(?:为你|帮你|给你|替你)?(?:转接?|转给|提交给|交给)(?:到)?(?:人工|客服)")


_OFFERS_HANDOFF = re.compile(r"转(?:接)?(?:给|到)?(?:人工|客服|过去)[^。！\n]{0,12}[吗？?]|(?:帮你|给你|为你|替你)转[^。！\n]{0,12}[吗？?]|要(?:不要)?转吗|(?:human|agent|support team)[^.!?\n]{0,24}\?", re.I)


def offers_handoff(text: str) -> bool:
    """模型在反问买家要不要转人工。"""
    return bool(_OFFERS_HANDOFF.search(text))


_UNANSWERED = re.compile(r"没(?:有)?查到|查不到|资料里没有|没有找到相关|couldn'?t find|no information", re.I)


def unanswered(text: str) -> bool:
    """这条回答是在说没查到。"""
    return bool(_UNANSWERED.search(text))


def redact(text: str) -> str:
    """把像密码、验证码、卡密、登录凭证的内容打码。发给模型和存库之前都要过这一步。"""
    text = _SECRETS[0].sub(MASK, text)
    for pattern in _SECRETS[1:]:
        text = pattern.sub(lambda m: f"{m[1]}{m[2]}{MASK}", text)
    return text


def claims_handoff(text: str) -> bool:
    """模型嘴上说「已转人工」。"""
    return bool(_CLAIMS_HANDOFF.search(text))
