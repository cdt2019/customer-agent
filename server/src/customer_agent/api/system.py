"""后台「接入方」页的运行信息：只读。这些都在服务器的环境变量里，改了要重启，不在页面上改。"""

from fastapi import APIRouter
from pydantic import BaseModel

from customer_agent import settings
from customer_agent.channels import telegram_bot

router = APIRouter()


class SystemOut(BaseModel):
    llm_model: str  # 回答用的模型
    timezone: str  # 每天的限额和统计从这里的零点算
    service_key_set: bool  # 接入方调对话接口用的服务密钥配了没有；密钥本身不给
    telegram: str | None  # Telegram 机器人：连上了是 @名字，配了还没连上是空字符串，没配是空（docs/10）


@router.get("/api/system")
def read_system() -> SystemOut:
    telegram = None if not settings.TELEGRAM_BOT_TOKEN else f"@{telegram_bot.username}" if telegram_bot.username else ""
    return SystemOut(llm_model=settings.LLM_MODEL, timezone=str(settings.TIMEZONE), service_key_set=bool(settings.SERVICE_API_KEY), telegram=telegram)
