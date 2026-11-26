"""买家在聊天里发的图片（docs/09）：清洗、存盘、记库。现在的模型看不懂图，图主要给接手的客服看。"""

import json
import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from customer_agent import settings
from customer_agent.db import Image

MAX_BYTES = 5 * 1024**2
PER_CONVERSATION = 5
CLEAN_TIMEOUT = 30  # 秒
TEXT = "[图片]"  # 发图片时那条消息的文字；模型也按它知道买家发了图


class Rejected(Exception):
    """不收这张图，str(error) 是给买家看的原因。"""


@dataclass(frozen=True)
class Cleaned:
    stored_name: str
    width: int
    height: int
    size: int


def count(session: Session, conversation_id: str) -> int:
    return session.scalar(select(func.count()).select_from(Image).where(Image.conversation_id == conversation_id)) or 0


def clean(data: bytes) -> Cleaned:
    """在子进程里认格式、缩小、重新编码，存进 IMAGES_DIR。"""
    if len(data) > MAX_BYTES:
        raise Rejected(f"图片最大 {MAX_BYTES // 1024**2}MB")
    settings.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex
    with tempfile.TemporaryDirectory(dir=settings.IMAGES_DIR) as work:
        source, target = Path(work) / "in", Path(work) / "out"
        source.write_bytes(data)
        try:
            done = subprocess.run(
                [sys.executable, "-m", "customer_agent.chat.image_worker", str(source), str(target)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=CLEAN_TIMEOUT, env={**os.environ, "PYTHONUTF8": "1"},
            )
        except subprocess.TimeoutExpired as error:
            raise Rejected("这张图片处理不了，换一张试试") from error
        lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
        info = json.loads(lines[-1]) if lines else {"error": "处理失败"}
        if done.returncode != 0 or "error" in info:
            raise Rejected("只能发 JPG、PNG、WebP 格式的图片")
        stored = f"{name}.{info['format']}"
        final = settings.IMAGES_DIR / stored
        target.replace(final)
    return Cleaned(stored_name=stored, width=info["width"], height=info["height"], size=final.stat().st_size)


def attach(session: Session, conversation_id: str, message_id: int, cleaned: Cleaned) -> Image:
    """把清洗好的图挂到买家那条「[图片]」消息上。"""
    row = Image(conversation_id=conversation_id, message_id=message_id, stored_name=cleaned.stored_name, width=cleaned.width, height=cleaned.height, size=cleaned.size)
    session.add(row)
    session.commit()
    return row


def path_of(image: Image) -> Path:
    return settings.IMAGES_DIR / image.stored_name


def remove_files(names: list[str]) -> None:
    for name in names:
        (settings.IMAGES_DIR / name).unlink(missing_ok=True)
