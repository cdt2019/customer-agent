"""把聊天窗的请求转给客服服务。浏览器只连店铺；服务密钥和访客令牌由这里加上。

聊天窗只认这组接口（见 docs/02 §5.4），换一个接入方也照这组实现。
"""

from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from demo_shop import identity, settings, store, tokens

router = APIRouter(prefix="/api/chat")
CLOSED = {"enabled": False, "max_message_chars": 0, "suggestions": {}}
_owners: dict[str, str] = {}  # 会话归谁：模拟站只记在内存里，重启后旧会话打不开，聊天窗会开新的


def _agent() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.AGENT_URL, headers={"X-Api-Key": settings.AGENT_KEY}, timeout=httpx.Timeout(30, read=180), trust_env=False)


def _owner(request: Request) -> str:
    who, browser = identity.current(request)
    if not browser:
        raise HTTPException(403, "先打开店铺页面")
    return f"{who}:{browser}"


def _check(request: Request, conversation_id: str) -> str:
    who = _owner(request)
    if _owners.get(conversation_id) != who:
        raise HTTPException(404, "没有这个会话")
    return who


def _token(request: Request) -> str:
    who, browser = identity.current(request)
    return tokens.sign(settings.TOKEN_SECRET, who, browser, settings.TOKEN_MINUTES)


def _relay(response: httpx.Response) -> Response:
    return Response(response.content, status_code=response.status_code, media_type=response.headers.get("content-type"))


@router.get("/config")
async def config(request: Request, response: Response) -> dict:
    identity.ensure_browser(request, response)
    info = store.info()
    try:
        async with _agent() as agent:
            reply = await agent.get("/v1/status")
        status = reply.json() if reply.status_code == 200 else CLOSED
    except httpx.TransportError:
        status = CLOSED  # 客服服务连不上：聊天窗只显示联系方式
    return {
        "enabled": status["enabled"],
        "max_message_chars": status["max_message_chars"],
        "name": info["name"],
        "contacts": info["contacts"],
        "reply_hours": info["reply_hours"],
        "suggestions": status["suggestions"],
        "theme": store.widget().get("theme"),
        "page_url": "/#support",
        "source_url": "/#help/{document}",
    }


@router.post("/conversations")
async def create(request: Request) -> Response:
    owner = _owner(request)
    async with _agent() as agent:
        reply = await agent.post("/v1/conversations", json={"index_id": settings.INDEX_ID, "visitor_id": owner, "channel": "web"})
    if reply.status_code == 201:
        _owners[reply.json()["id"]] = owner
    return _relay(reply)


@router.get("/conversations/{conversation_id}")
async def history(conversation_id: str, request: Request, after: int = 0) -> Response:
    """取历史；转人工期间聊天窗带着 after 定时来拉客服的新回复。"""
    _check(request, conversation_id)
    async with _agent() as agent:
        return _relay(await agent.get(f"/v1/conversations/{conversation_id}", params={"after": after}))


class SendIn(BaseModel):
    text: str


@router.post("/conversations/{conversation_id}/messages")
async def send(conversation_id: str, body: SendIn, request: Request) -> Response:
    _check(request, conversation_id)
    agent = _agent()
    return await _stream(agent, agent.build_request("POST", f"/v1/conversations/{conversation_id}/messages", json={"text": body.text, "visitor_token": _token(request)}))


async def _stream(agent: httpx.AsyncClient, request: httpx.Request) -> Response:
    """把客服服务的 SSE 原样流回浏览器；出错时照原样回。"""
    upstream = await agent.send(request, stream=True)
    if upstream.status_code != 200:
        content = await upstream.aread()
        await agent.aclose()
        return Response(content, status_code=upstream.status_code, media_type=upstream.headers.get("content-type"))

    async def forward() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await agent.aclose()

    return StreamingResponse(forward(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/conversations/{conversation_id}/images")
async def send_image(conversation_id: str, file: UploadFile, request: Request) -> Response:
    """聊天窗发一张图片（docs/09）：加上访客令牌转给客服服务，回答照样是 SSE。"""
    _check(request, conversation_id)
    agent = _agent()
    body = {"file": (file.filename or "image", await file.read(), file.content_type or "application/octet-stream")}
    return await _stream(agent, agent.build_request("POST", f"/v1/conversations/{conversation_id}/images", files=body, data={"visitor_token": _token(request)}))


@router.get("/conversations/{conversation_id}/images/{image_id}")
async def read_image(conversation_id: str, image_id: int, request: Request) -> Response:
    """看自己会话里的图片。"""
    _check(request, conversation_id)
    async with _agent() as agent:
        reply = await agent.get(f"/v1/conversations/{conversation_id}/images/{image_id}")
    headers = {name: reply.headers[name] for name in ("content-security-policy", "x-content-type-options", "cache-control") if name in reply.headers}
    return Response(reply.content, status_code=reply.status_code, media_type=reply.headers.get("content-type"), headers=headers)


class HandoffIn(BaseModel):
    email: str = ""


@router.post("/conversations/{conversation_id}/handoff")
async def handoff(conversation_id: str, body: HandoffIn, request: Request) -> Response:
    _check(request, conversation_id)
    async with _agent() as agent:
        return _relay(await agent.post(f"/v1/conversations/{conversation_id}/handoff", json={"email": body.email, "visitor_token": _token(request)}))


class FeedbackIn(BaseModel):
    useful: bool | None


@router.post("/conversations/{conversation_id}/messages/{message_id}/feedback")
async def feedback(conversation_id: str, message_id: int, body: FeedbackIn, request: Request) -> Response:
    _check(request, conversation_id)
    async with _agent() as agent:
        return _relay(await agent.post(f"/v1/conversations/{conversation_id}/messages/{message_id}/feedback", json=body.model_dump()))
