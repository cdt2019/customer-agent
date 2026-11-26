"""后台改总开关、限额和单价。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from customer_agent import service
from customer_agent.api.deps import db
from customer_agent.chat import guard

router = APIRouter()


class ServiceSettingsIO(BaseModel):
    enabled: bool
    per_visitor_day: int = Field(ge=1, le=10_000)
    per_conversation: int = Field(ge=1, le=1_000)
    max_message_chars: int = Field(ge=50, le=guard.MAX_MESSAGE_CHARS)
    daily_token_limit: int = Field(ge=1_000)
    price_input: float = Field(ge=0)  # 每百万 token 的价格（元），只用来估算花费
    price_cached_input: float = Field(ge=0)
    price_output: float = Field(ge=0)


class ServiceStateOut(ServiceSettingsIO):
    used_today: int
    open_now: bool


def state(session: DbSession) -> ServiceStateOut:
    row = service.current(session)
    fields = {name: getattr(row, name) for name in ServiceSettingsIO.model_fields}
    return ServiceStateOut(**fields, used_today=service.used_today(session), open_now=service.open_now(session))


@router.get("/api/service-settings")
def read(session: DbSession = Depends(db)) -> ServiceStateOut:
    return state(session)


@router.put("/api/service-settings")
def write(body: ServiceSettingsIO, session: DbSession = Depends(db)) -> ServiceStateOut:
    row = service.current(session)
    for name, value in body.model_dump().items():
        setattr(row, name, value)
    session.commit()
    return state(session)
