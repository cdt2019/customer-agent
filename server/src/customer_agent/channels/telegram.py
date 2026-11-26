"""和 Telegram 机器人接口说话（docs/10）：收消息（长轮询）、发消息、发「正在输入」、下载图片。只管说话，不懂对话。"""

import httpx

POLL_SECONDS = 25  # 长轮询一次最多等这么久


class Telegram:
    def __init__(self, token: str, proxy: str | None = None, transport: httpx.BaseTransport | None = None):
        options = {"proxy": proxy, "transport": transport, "trust_env": False, "timeout": httpx.Timeout(15, read=POLL_SECONDS + 15)}
        self._api = httpx.Client(base_url=f"https://api.telegram.org/bot{token}/", **options)
        self._files = httpx.Client(base_url=f"https://api.telegram.org/file/bot{token}/", **options)

    def _call(self, method: str, **params) -> dict | list:
        reply = self._api.post(method, json=params)
        reply.raise_for_status()
        return reply.json()["result"]

    def me(self) -> dict:
        return self._call("getMe")

    def updates(self, offset: int) -> list[dict]:
        """等新消息，最多等 POLL_SECONDS 秒。offset 是下一条要的编号，Telegram 会把它之前的标成已收。"""
        return self._call("getUpdates", offset=offset, timeout=POLL_SECONDS, allowed_updates=["message"])

    def send(self, chat_id: int, text: str, buttons: list[str] | None = None) -> None:
        """发纯文本。buttons 是输入框上方的快捷问题，点了就当买家发了这句。"""
        markup = {"keyboard": [[{"text": b}] for b in buttons], "resize_keyboard": True, "one_time_keyboard": True} if buttons else {"remove_keyboard": True}
        self._call("sendMessage", chat_id=chat_id, text=text[:4096], reply_markup=markup)

    def typing(self, chat_id: int) -> None:
        self._call("sendChatAction", chat_id=chat_id, action="typing")

    def download(self, file_id: str, limit: int) -> bytes:
        """下载买家发的文件，超过 limit 字节就不下了，返回空。"""
        info = self._call("getFile", file_id=file_id)
        if info.get("file_size", 0) > limit:
            return b""
        reply = self._files.get(info["file_path"])
        reply.raise_for_status()
        return reply.content
