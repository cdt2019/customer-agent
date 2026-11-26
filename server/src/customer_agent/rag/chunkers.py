"""切块：把一篇 Markdown 切成块。每种策略是一个函数，签名相同，在 CHUNKERS 里按名字取。"""

import re
from collections.abc import Callable
from dataclasses import dataclass

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SENTENCE = re.compile(r"[^。！？!?]*[。！？!?]+|[^。！？!?]+")  # 连着的标点算同一句，一个字也不能丢


@dataclass(frozen=True)
class Chunk:
    heading_path: tuple[str, ...]  # 所在的各级标题，定长切块时为空
    text: str


def sections(markdown: str) -> list[tuple[tuple[str, ...], str]]:
    """按标题分段，返回 (各级标题, 正文)。代码块里的 # 不算标题。"""
    out, trail, body, in_code = [], [], [], False

    def flush() -> None:
        text = "\n".join(body).strip()
        if text:
            out.append((tuple(title for _, title in trail), text))
        body.clear()

    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        match = None if in_code else HEADING.match(line)
        if not match:
            body.append(line)
            continue
        flush()
        level = len(match[1])
        while trail and trail[-1][0] >= level:
            trail.pop()
        trail.append((level, match[2]))
    flush()
    return out


def atoms(text: str, size: int) -> list[str]:
    """切成不该再拆的小片：句子、整张表格、整个代码块。单片超过 size 才硬拆。"""
    pieces, block, in_code = [], [], False

    def flush_block() -> None:
        if block:
            pieces.append("\n".join(block) + "\n")
            block.clear()

    for line in text.splitlines():
        fence = line.lstrip().startswith("```")
        if in_code or fence or line.startswith("|"):
            if fence:
                in_code = not in_code
            block.append(line)
            continue
        flush_block()
        pieces.extend(SENTENCE.findall(line))
        pieces.append("\n")
    flush_block()

    out = []
    for piece in pieces:
        if len(piece) <= size:
            out.append(piece)
            continue
        for line in piece.splitlines(keepends=True):
            out.extend(line[i : i + size] for i in range(0, len(line), size))
    return out


def pack(pieces: list[str], size: int, overlap: int) -> list[str]:
    """把小片依次装进块，装不下就开新块，新块开头带上一块末尾 overlap 个字。"""
    out, buf, carried = [], "", 0
    for piece in pieces:
        if len(buf) + len(piece) > size and len(buf) > carried:
            out.append(buf)
            buf = buf[-overlap:] if overlap else ""
            carried = len(buf)
        buf += piece
    if buf.strip() and len(buf) > carried:
        out.append(buf)
    return [b.strip() for b in out if b.strip()]


def by_heading(markdown: str, size: int, overlap: int) -> list[Chunk]:
    """按标题分段，段太长再按句子切。表格和代码块尽量不切开。"""
    return [Chunk(path, text) for path, body in sections(markdown) for text in pack(atoms(body, size), size, overlap)]


def fixed(markdown: str, size: int, overlap: int) -> list[Chunk]:
    """不管结构，按字数滑窗切。作为对照。"""
    step = size - overlap
    return [Chunk((), markdown[i : i + size].strip()) for i in range(0, max(len(markdown) - overlap, 1), step)]


def overlaps(markdown: str, texts: list[str]) -> list[int]:
    """每块开头有多少字和上一块重复：按顺序在原文里定位，看和上一块的结尾交叠多少。"""
    out, previous_end, search_from = [], 0, 0
    for text in texts:
        start = markdown.find(text, search_from)
        if start < 0:
            out.append(0)
            continue
        out.append(max(0, min(previous_end - start, len(text))))
        previous_end, search_from = start + len(text), start + 1
    return out


def titled(title: str, heading_path: list[str] | tuple[str, ...], text: str) -> str:
    """块的正文前面带上「文章标题 › 小节标题」：算向量、重排、交给模型时都用这个样子。"""
    return " › ".join((title, *heading_path)) + "\n" + text


CHUNKERS: dict[str, Callable[[str, int, int], list[Chunk]]] = {"heading": by_heading, "fixed": fixed}
