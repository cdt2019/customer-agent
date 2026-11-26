"""给接入方后端调的对话接口。浏览器不直接连这里：接入方带着服务密钥和访客令牌转发。"""

import hmac
import json
import uuid
from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from customer_agent import runtime, service, settings
from customer_agent.api.deps import db
from customer_agent.chat import agent, guard, handoff, images, staff, tools
from customer_agent.db import ChatMessage, Conversation, Handoff, Image, IndexVersion


def require_key(x_api_key: str = Header(default="")) -> None:
    if not settings.SERVICE_API_KEY:
        raise HTTPException(503, "服务密钥没有配置")
    if not hmac.compare_digest(x_api_key, settings.SERVICE_API_KEY):
        raise HTTPException(401, "服务密钥不对")


router = APIRouter(prefix="/v1", dependencies=[Depends(require_key)])


class StatusOut(BaseModel):
    enabled: bool  # 关着时聊天窗只显示联系方式
    max_message_chars: int  # 买家一条消息最多几个字，聊天窗按它提示
    suggestions: dict[str, list[str]]  # 聊天窗的常见问题，按语言


@router.get("/status")
def status(session: DbSession = Depends(db)) -> StatusOut:
    """接入方在给聊天窗配置时问一下：总开关开着、今天的用量没到上限，再带上聊天窗要显示的设置。"""
    row = service.current(session)
    return StatusOut(enabled=service.open_now(session), max_message_chars=row.max_message_chars, suggestions=row.suggestions)


class ConversationIn(BaseModel):
    index_id: int
    visitor_id: str = Field(min_length=1, max_length=100)  # 接入方给的访客编号，用来算限额
    channel: str = Field("web", max_length=20)


class ConversationOut(BaseModel):
    id: str
    status: str


@router.post("/conversations", status_code=201)
def create(body: ConversationIn, session: DbSession = Depends(db)) -> ConversationOut:
    index = session.get(IndexVersion, body.index_id)
    if index is None:
        raise HTTPException(404, "没有这个索引版本")
    conversation = Conversation(id=uuid.uuid4().hex, kb_id=index.kb_id, index_id=index.id, channel=body.channel, visitor_id=body.visitor_id)
    session.add(conversation)
    session.commit()
    return ConversationOut(id=conversation.id, status=conversation.status)


class ImageOut(BaseModel):
    id: int
    width: int
    height: int


def image_out(row: Image) -> ImageOut:
    return ImageOut(id=row.id, width=row.width, height=row.height)


MEDIA = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def image_file(row: Image) -> FileResponse:
    """把图发出去：内容类型照存的格式给，不让浏览器猜，图片里也跑不了东西。"""
    headers = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox", "Cache-Control": "private, max-age=3600"}
    return FileResponse(images.path_of(row), media_type=MEDIA[row.stored_name.rsplit(".", 1)[1]], headers=headers)


def images_by_message(session: DbSession, conversation_id: str) -> dict[int, ImageOut]:
    return {row.message_id: image_out(row) for row in session.scalars(select(Image).where(Image.conversation_id == conversation_id))}


class MessageOut(BaseModel):
    id: int
    role: str
    text: str
    sources: list[dict]
    feedback: int | None
    image: ImageOut | None  # 买家发的图


class HandoffOut(BaseModel):
    kind: str  # ticket 建了工单；record 记下了
    ticket_no: str | None
    email: str | None
    reply_hours: int
    away_message: str | None  # 不在客服时间时的说明


class HistoryOut(ConversationOut):
    messages: list[MessageOut]
    handoff: HandoffOut | None


def handoff_out(row: Handoff | None) -> HandoffOut | None:
    if row is None:
        return None
    info = runtime.shop().info()
    return HandoffOut(kind=row.kind, ticket_no=row.ticket_no, email=row.email, reply_hours=info.reply_hours, away_message=None if info.online else info.away_message)


def get_conversation(session: DbSession, conversation_id: str) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(404, "没有这个会话")
    return conversation


@router.get("/conversations/{conversation_id}")
def history(conversation_id: str, after: int = 0, session: DbSession = Depends(db)) -> HistoryOut:
    """取历史。聊天窗在转人工期间每隔几秒带上 after（已有的最后一条消息编号）来拉客服的新回复（docs/07 §3）。"""
    conversation = get_conversation(session, conversation_id)
    staff.expire(session, conversation)
    staff.seen(session, conversation)
    rows = session.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation.id, ChatMessage.id > after).order_by(ChatMessage.id))
    pictures = images_by_message(session, conversation.id)
    latest = session.scalars(select(Handoff).where(Handoff.conversation_id == conversation.id).order_by(Handoff.id.desc())).first()
    return HistoryOut(
        id=conversation.id,
        status=conversation.status,
        messages=[MessageOut(id=m.id, role=m.role, text=m.text, sources=m.sources, feedback=m.feedback, image=pictures.get(m.id)) for m in rows],
        handoff=handoff_out(latest),
    )


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=guard.MAX_MESSAGE_CHARS)
    visitor_token: str | None = Field(None, max_length=2000)  # 接入方签发，原样带回去查订单


def sse(event: agent.Event) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


def _reply(own: DbSession, conversation_id: str, text: str, visitor: str | None, on_user: Callable[[DbSession, int], dict] | None = None) -> StreamingResponse:
    """买家的一条消息按 SSE 流回答。客服在接时不调模型，只回 user 和 done（done 里 staff 为真）。
    on_user 在买家的消息存好后调一次（参数是会话和消息编号），返回的内容并进 user 事件；发图片时用它把图挂到这条消息上。"""

    def stream() -> Iterator[str]:
        # 依赖注入的会话在响应开始流之前就关了；SQLAlchemy 的会话关了还能接着用，这里用完再关一次
        conversation = own.get(Conversation, conversation_id)
        try:
            if conversation.status == "staff":
                events = staff.buyer_says(own, conversation, text)
            else:
                index = own.get(IndexVersion, conversation.index_id)
                events = agent.respond(own, conversation, index, runtime.retriever_for(index, tools.RECIPE), runtime.shop(), runtime.chat_model(), visitor, text)
            for event in events:
                if event.type == "user" and on_user:
                    event = agent.Event("user", {**event.data, **on_user(own, event.data["message_id"])})
                yield sse(event)
        except Exception:
            own.rollback()
            yield sse(agent.Event("error", {"code": "failed"}))
            raise
        finally:
            own.close()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _admit(session: DbSession, conversation: Conversation, text: str) -> None:
    """收不收这条消息。客服在接时只管字数，不算 AI 的限额；AI 在答时按总开关和限额来，还要有模型密钥。"""
    staff.seen(session, conversation)  # 买家在发消息，当然在看
    staff.expire(session, conversation)
    if conversation.status == "staff":
        if len(text) > service.current(session).max_message_chars:
            raise HTTPException(422, f"一条消息最多 {service.current(session).max_message_chars} 字")
        return
    try:
        service.check(session, conversation, runtime.shop(), text)
        runtime.chat_model()
    except service.Refused as refused:
        raise HTTPException(refused.status, refused.message) from refused
    except runtime.MissingKey as error:
        raise HTTPException(503, str(error)) from error


@router.post("/conversations/{conversation_id}/messages")
def send(conversation_id: str, body: SendIn, session: DbSession = Depends(db)) -> StreamingResponse:
    """发一条消息，回答按 SSE 流回：user（买家的话，已打码）、status（在调哪个工具）、text（文字）、clear（撤掉已流出的文字）、handoff（转人工）、done（结束）、error。
    客服接手时不调模型，只回 user 和 done（done 里 staff 为真），买家的话留给客服看，也不算 AI 的限额。"""
    _admit(session, get_conversation(session, conversation_id), body.text)
    return _reply(session, conversation_id, body.text, body.visitor_token)


@router.post("/conversations/{conversation_id}/images")
def send_image(conversation_id: str, file: UploadFile, visitor_token: str | None = Form(None, max_length=2000), session: DbSession = Depends(db)) -> StreamingResponse:
    """买家发一张图（docs/09）。清洗后存下来，挂在一条文字是「[图片]」的消息上；之后和发文字一样，AI 回一句或交给客服。
    user 事件里多一个 image：{id, width, height}。"""
    conversation = get_conversation(session, conversation_id)
    if images.count(session, conversation.id) >= images.PER_CONVERSATION:
        raise HTTPException(429, f"一个对话最多发 {images.PER_CONVERSATION} 张图片")
    _admit(session, conversation, images.TEXT)
    try:
        cleaned = images.clean(file.file.read(images.MAX_BYTES + 1))
    except images.Rejected as error:
        raise HTTPException(422, str(error)) from error

    def attach(own: DbSession, message_id: int) -> dict:
        return {"image": image_out(images.attach(own, conversation_id, message_id, cleaned)).model_dump()}

    return _reply(session, conversation_id, images.TEXT, visitor_token, attach)


@router.get("/conversations/{conversation_id}/images/{image_id}", response_model=None)
def read_image(conversation_id: str, image_id: int, session: DbSession = Depends(db)) -> FileResponse:
    """买家经接入方看自己会话里的图。"""
    image = session.get(Image, image_id)
    if image is None or image.conversation_id != conversation_id:
        raise HTTPException(404, "没有这张图片")
    return image_file(image)


class HandoffIn(BaseModel):
    email: str = Field("", max_length=200)
    visitor_token: str | None = Field(None, max_length=2000)


class HandoffResult(BaseModel):
    status: str  # handoff 已转；needs_email 要买家留邮箱
    handoff: HandoffOut | None


@router.post("/conversations/{conversation_id}/handoff")
def request_handoff(conversation_id: str, body: HandoffIn, session: DbSession = Depends(db)) -> HandoffResult:
    """买家点了「转人工」。摘要取最近的对话；已经转过的直接返回原来的结果。"""
    conversation = get_conversation(session, conversation_id)
    if conversation.status == "handoff":
        latest = session.scalars(select(Handoff).where(Handoff.conversation_id == conversation.id).order_by(Handoff.id.desc())).first()
        return HandoffResult(status="handoff", handoff=handoff_out(latest))
    recent = session.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation.id).order_by(ChatMessage.id.desc()).limit(8)).all()
    lines = [f"{'买家' if m.role == 'user' else 'AI'}：{m.text}" for m in reversed(recent)]
    summary = "买家点了「转人工」。\n" + ("\n".join(lines) if lines else "还没有聊过。")
    row = handoff.transfer(session, conversation, runtime.shop(), body.visitor_token, summary, email=body.email)
    session.commit()
    return HandoffResult(status="handoff" if row else "needs_email", handoff=handoff_out(row))


class FeedbackIn(BaseModel):
    useful: bool | None  # 再点一次取消时传空


@router.post("/conversations/{conversation_id}/messages/{message_id}/feedback", status_code=204)
def feedback(conversation_id: str, message_id: int, body: FeedbackIn, session: DbSession = Depends(db)) -> None:
    message = session.get(ChatMessage, message_id)
    if message is None or message.role != "assistant" or message.conversation_id != conversation_id:
        raise HTTPException(404, "没有这条回答")
    message.feedback = None if body.useful is None else int(body.useful)
    session.commit()
