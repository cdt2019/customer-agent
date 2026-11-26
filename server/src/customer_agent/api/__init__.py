"""客服服务的接口：管理后台（要登录）和接入方的对话接口（要服务密钥）。

启动（在 server/ 下）：uv run uvicorn customer_agent.api:app --port 8000
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import update

from customer_agent.api import auth, chats, chunk_lab, conversations, datasets, evaluations, handoffs, imports, knowledge, playground, service_settings, shop, system, tasks, usage, widget
from customer_agent import retention, runtime, settings
from customer_agent.channels import telegram_bot
from customer_agent.db import EvalRun, IngestJob, Session, SourceFile

log = logging.getLogger(__name__)


async def clean_daily() -> None:
    """每天清一次到期的聊天记录。启动时先清一次。"""
    while True:
        try:
            with Session() as session:
                cleaned = await asyncio.to_thread(retention.clean, session)
            log.info("到期清理：%s 个会话，%s 条检索过程", cleaned.conversations, cleaned.traces)
        except Exception:
            log.exception("到期清理失败，明天再试")
        await asyncio.sleep(24 * 3600)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # 评测在服务进程里跑，服务一重启，还标着进行中的就不会再有结果了
    with Session() as session:
        session.execute(update(EvalRun).where(EvalRun.status == "running").values(status="failed", error="服务重启，评测中断"))
        session.execute(update(IngestJob).where(IngestJob.status == "running").values(status="failed", error="服务重启，任务中断"))
        session.execute(update(SourceFile).where(SourceFile.status.in_(("queued", "parsing"))).values(status="failed", error="服务重启，解析中断，可以重新解析"))
        session.commit()
    tasks = [asyncio.create_task(clean_daily())]
    bot = runtime.telegram()
    if bot and settings.TELEGRAM_INDEX_ID:
        tasks.append(asyncio.create_task(telegram_bot.run_forever(bot)))
    elif bot:
        log.error("配了 TELEGRAM_BOT_TOKEN 但没配 TELEGRAM_INDEX_ID，Telegram 不启用")
    yield
    for task in tasks:
        task.cancel()


# 不开放 /docs 和 /openapi.json：接口定义用 app.openapi() 在本地导出
app = FastAPI(title="customer-agent 管理后台", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth.router)
app.include_router(conversations.router)  # 自己按服务密钥鉴权
for module in (knowledge, datasets, imports, chunk_lab, playground, evaluations, tasks, service_settings, chats, handoffs, usage, shop, system, widget):
    app.include_router(module.router, dependencies=[Depends(auth.require_admin)])
