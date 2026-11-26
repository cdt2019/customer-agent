"""资料来源：把一个文件夹读成一批文档。文件开头可以有 `--- key: value ---` 的说明块。"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from customer_agent.rag.parsers import PARSERS, pick

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
LANG_SUFFIX = re.compile(r"\.(zh|en)$")
FIRST_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.M)


@dataclass(frozen=True)
class SourceDoc:
    source_id: str  # 相对路径；Markdown 去掉后缀和语言（faq/when-delivered），别的格式保留后缀（手册.pdf）
    lang: str
    title: str
    kind: str
    markdown: str


def clean(markdown: str) -> str:
    """统一换行，去掉注释和行尾空白，连续空行压成一行。"""
    text = markdown.replace("\r\n", "\n")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """拆出开头的说明块，返回 (说明, 正文)。"""
    head = FRONT_MATTER.match(text)
    if not head:
        return {}, text
    return dict(line.split(": ", 1) for line in head[1].splitlines() if ": " in line), text[head.end() :]


def read_folder(root: Path) -> Iterator[SourceDoc]:
    for path in sorted(p for p in root.rglob("*") if p.suffix in PARSERS):
        meta, text = split_front_matter(pick(path.suffix).parse(path).replace("\r\n", "\n"))
        relative = path.relative_to(root)
        stem = (relative.with_suffix("") if path.suffix == ".md" else relative).as_posix()
        lang = LANG_SUFFIX.search(stem)
        heading = FIRST_HEADING.search(text)
        yield SourceDoc(
            source_id=LANG_SUFFIX.sub("", stem),
            lang=meta.get("lang") or (lang[1] if lang else "zh"),
            title=meta.get("title") or (heading[1] if heading else path.stem),
            kind=meta.get("kind") or path.parent.name,
            markdown=clean(text),
        )
