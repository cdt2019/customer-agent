"""导入文件：在隔离的子进程里解析，再检查解析结果靠不靠谱。

上传的文件不可信，解析器崩了、卡死都不能拖垮服务，所以放到子进程里跑并设超时。
子进程常驻，Docling 的模型只加载一次（每次新起一个要多等一分多钟，docs/05 §32）。
"""

import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from customer_agent import settings
from customer_agent.rag.sources import clean, split_front_matter

PARSE_TIMEOUT = 600  # 秒
IDLE_SECONDS = 600  # 解析子进程空闲这么久就关掉
MIN_CHARS = 20  # 比这还少，基本可以认为没解析出内容

HEADING = re.compile(r"^(#{1,6})\s+\S", re.M)
TABLE = re.compile(r"(?:^\|.*\n?)+", re.M)
IMAGE = "<!-- image -->"


class ParseError(Exception):
    """文件解析不了，str(error) 是给人看的原因。"""


class _Worker:
    """常驻的解析子进程。模型只加载一次；崩了、超时了就杀掉，下一份重新起；空闲 IDLE_SECONDS 关掉，把内存还回去。"""

    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.idle: threading.Timer | None = None
        self.lock = threading.Lock()  # 一次只解析一份；空闲计时到点时也要等手上这份解析完

    def ensure(self) -> subprocess.Popen[str]:
        if self.process is None or self.process.poll() is not None:
            env = {**os.environ, "HF_HOME": str(settings.HF_HOME), "PYTHONUTF8": "1"}
            self.process = subprocess.Popen(
                [sys.executable, "-m", "customer_agent.rag.parse_worker"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True, encoding="utf-8", errors="replace"
            )
        return self.process

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        self.process = None

    def stop_when_idle(self) -> None:
        with self.lock:
            self.stop()

    def run(self, task: dict) -> dict:
        with self.lock:
            if self.idle is not None:
                self.idle.cancel()
            try:
                return self._run(task)
            finally:
                self.idle = threading.Timer(IDLE_SECONDS, self.stop_when_idle)
                self.idle.daemon = True
                self.idle.start()

    def _run(self, task: dict) -> dict:
        process = self.ensure()
        try:
            process.stdin.write(json.dumps(task, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except OSError as error:
            self.stop()
            raise ParseError("解析器意外退出，请重新解析") from error
        replies: list[dict] = []

        def read() -> None:
            for line in process.stdout:  # 跳过不是回复的行
                if line.startswith("{"):
                    replies.append(json.loads(line))
                    return

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        reader.join(PARSE_TIMEOUT)
        if reader.is_alive():
            self.stop()
            raise ParseError(f"解析超过 {PARSE_TIMEOUT // 60} 分钟，已停止")
        if not replies:
            self.stop()
            raise ParseError("解析器意外退出（可能是内存不够），请重新解析")
        return replies[0]


_worker = _Worker()


def parse_isolated(path: Path, parser: str) -> str:
    """在常驻的子进程里用指定的解析器把文件解析成 Markdown。"""
    out = path.with_name(path.name + ".parsed")
    try:
        reply = _worker.run({"source": str(path), "target": str(out), "parser": parser})
        if not reply["ok"]:
            raise ParseError(f"解析器出错：{reply['error']}")
        return out.read_bytes().decode("utf-8")
    finally:
        out.unlink(missing_ok=True)


@dataclass(frozen=True)
class Report:
    markdown: str
    checks: list[str]  # 解析到了什么
    warnings: list[str]  # 值得人看一眼的地方


def inspect(raw: str, suffix: str) -> Report:
    """清洗解析结果并做检查。什么都没解析出来时抛 ParseError，不让空文档进知识库。"""
    images = raw.count(IMAGE)
    _, body = split_front_matter(raw.replace("\r\n", "\n"))
    markdown = clean(body)
    chars = len(re.sub(r"\s", "", markdown))
    if chars < MIN_CHARS:
        if suffix == ".pdf":
            raise ParseError("这份 PDF 几乎没有文字层，可能是扫描件。第一版不支持扫描件，可以换成文字版")
        raise ParseError("没有解析出文字内容")

    levels = [len(m) for m in HEADING.findall(markdown)]
    tables = len(TABLE.findall(markdown))
    checks = [f"标题 {len(levels)} 个", f"表格 {tables} 张", f"正文 {chars:,} 字"]
    warnings = []
    if images:
        warnings.append(f"有 {images} 张图片，图片里的内容不会进知识库")
    if not levels:
        warnings.append("没有识别出标题，切块时只能按字数切")
    elif suffix == ".pdf" and len(levels) > 1 and len(set(levels)) == 1:
        warnings.append("PDF 的标题层级没有识别出来，可以在右边手动改 # 的数量")
    return Report(markdown, checks, warnings)
