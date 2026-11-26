"""回答用的模型。接的是兼容 OpenAI 接口的服务，换供应商只改 settings 里的地址和型号。"""

from collections.abc import Iterator
from dataclasses import dataclass

from openai import OpenAI


@dataclass(frozen=True)
class Reply:
    text: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ToolRequest:
    id: str
    name: str
    arguments: str  # 模型给的 JSON 文本，不一定合法


@dataclass(frozen=True)
class Finished:
    """一次流式调用的结尾。"""

    text: str
    tool_requests: list[ToolRequest]
    input_tokens: int
    output_tokens: int
    cached_tokens: int


class ChatModel:
    def __init__(self, base_url: str, model: str, api_key: str, extra_body: dict | None = None):
        """extra_body 是每次请求额外带的参数，各家不一样，比如关掉思考模式。"""
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self._extra_body = extra_body or None

    def complete(self, system: str, user: str) -> Reply:
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            extra_body=self._extra_body,
        )
        usage = response.usage
        return Reply(response.choices[0].message.content, usage.prompt_tokens, usage.completion_tokens)

    def stream(self, messages: list[dict], tools: list[dict] | None, tool_choice: dict | None = None) -> Iterator[str | Finished]:
        """一段段给出文字，最后给一个 Finished。tools 为空时模型只能直接回答；tool_choice 指定必须调哪个工具。"""
        options = {"tools": tools} if tools else {}
        if tool_choice:
            options["tool_choice"] = tool_choice
        parts = self._client.chat.completions.create(
            model=self.model, temperature=0, messages=messages, stream=True, stream_options={"include_usage": True}, extra_body=self._extra_body, **options
        )
        text, calls, usage = "", {}, None
        for part in parts:
            usage = part.usage or usage
            if not part.choices:
                continue
            delta = part.choices[0].delta
            if delta.content:
                text += delta.content
                yield delta.content
            for call in delta.tool_calls or []:
                slot = calls.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                slot["id"] = call.id or slot["id"]
                slot["name"] += call.function.name or ""
                slot["arguments"] += call.function.arguments or ""
        cached = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
        yield Finished(text, [ToolRequest(**calls[i]) for i in sorted(calls)], usage.prompt_tokens, usage.completion_tokens, cached)
