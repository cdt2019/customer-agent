"""后台改聊天窗的常见问题。聊天窗经接入方从 /v1/status 拿到。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.orm import Session as DbSession

from customer_agent import service
from customer_agent.api.deps import db

router = APIRouter()

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Lang = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]


class WidgetSettings(BaseModel):
    suggestions: dict[Lang, Annotated[list[Question], Field(max_length=6)]]  # 按语言，每种最多 6 条


@router.get("/api/widget-settings")
def read(session: DbSession = Depends(db)) -> WidgetSettings:
    return WidgetSettings(suggestions=service.current(session).suggestions)


@router.put("/api/widget-settings")
def write(body: WidgetSettings, session: DbSession = Depends(db)) -> WidgetSettings:
    row = service.current(session)
    row.suggestions = {lang: items for lang, items in body.suggestions.items() if items}
    session.commit()
    return WidgetSettings(suggestions=row.suggestions)
