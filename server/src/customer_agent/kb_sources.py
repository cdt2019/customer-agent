"""知识库的资料从哪来：接入方的帮助文章（技术方案 §5.2），或者一个文件夹。命令行和后台的「同步」都走这里。"""

from collections.abc import Iterator
from pathlib import Path

from customer_agent import runtime
from customer_agent.rag.sources import SourceDoc, clean, read_folder

SHOP = "shop"  # 知识库的来源写成这个，就从接入方的接口同步；否则是文件夹路径


def available(source: str | None) -> bool:
    return source == SHOP or (source is not None and Path(source).is_dir())


def documents(source: str) -> Iterator[SourceDoc]:
    if source != SHOP:
        yield from read_folder(Path(source))
        return
    for article in runtime.shop().articles():
        yield SourceDoc(source_id=article.id, lang=article.lang, title=article.title, kind=article.kind, markdown=clean(article.markdown))
