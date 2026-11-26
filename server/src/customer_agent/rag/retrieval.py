"""检索：给一个问题，按配方走几步，找出最相关的几块，并把每一步记下来。

配方（Recipe）决定走哪些步：可选扩展问题 → 每条查询的语义、关键词各取一批候选 →
不止一路就融合 → 可选重排前若干块 → 取前几块。
"""

import time
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from customer_agent.db import Chunk, Document, IndexVersion, RetrievalTrace
from customer_agent.llm import ChatModel
from customer_agent.rag.chunkers import titled
from customer_agent.rag.embedders import Embedder
from customer_agent.rag.expand import expand
from customer_agent.rag.rerankers import Reranker
from customer_agent.rag.stores import Hit, QdrantStore


@dataclass(frozen=True)
class Recipe:
    dense: bool = True
    keyword: bool = False
    expand: bool = False  # 先让模型改写、拆分问题，每条都去检索
    rerank: int = 0  # 重排前多少块；0 是不重排
    candidates: int = 20  # 每一路取多少块
    limit: int = 5  # 最后交给模型多少块


@dataclass(frozen=True)
class Retrieved:
    chunk: Chunk
    document: Document
    score: float

    @property
    def text(self) -> str:
        return titled(self.document.title, self.chunk.heading_path, self.chunk.text)


def rrf(routes: list[list[Hit]], k: int = 60) -> list[Hit]:
    """把几路排名合成一个：每块的分数是它在各路里 1/(k+名次) 的和。只看名次，不看各路自己的分数。"""
    scores: dict[int, float] = {}
    for hits in routes:
        for rank, hit in enumerate(hits, 1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0) + 1 / (k + rank)
    return [Hit(chunk_id, score) for chunk_id, score in sorted(scores.items(), key=lambda item: -item[1])]


@dataclass(frozen=True)
class Retriever:
    embedder: Embedder
    store: QdrantStore
    reranker: Reranker | None = None  # 配方里开了重排才用得到
    llm: ChatModel | None = None  # 配方里开了扩展问题才用得到

    def retrieve(self, session: Session, index: IndexVersion, query: str, recipe: Recipe) -> tuple[list[Retrieved], RetrievalTrace]:
        """返回排好序的全部候选和这次检索的记录；前 recipe.limit 块是交给模型的。"""
        stages, clock = [], time.perf_counter()

        def record(name: str, hits: list[Hit], **extra) -> None:
            nonlocal clock
            now = time.perf_counter()
            stages.append({"name": name, "ms": round((now - clock) * 1000), **extra, "hits": [{"chunk_id": h.chunk_id, "score": round(h.score, 4)} for h in hits]})
            clock = now

        start = clock
        queries = [query]
        if recipe.expand:
            queries = expand(self.llm, query)
            record("expand", [], queries=queries)
        routes = []
        for q in queries:
            if recipe.dense:
                routes.append(self.store.dense(index.collection, self.embedder.query(q), recipe.candidates))
                record("dense", routes[-1], query=q)
            if recipe.keyword:
                routes.append(self.store.keyword(index.collection, q, recipe.candidates))
                record("keyword", routes[-1], query=q)
        hits = routes[0]
        if len(routes) > 1:
            hits = rrf(routes)
            record("fuse", hits)

        rows = {c.id: (c, d) for c, d in session.execute(select(Chunk, Document).join(Document).where(Chunk.id.in_([h.chunk_id for h in hits])))}
        found = [Retrieved(*rows[h.chunk_id], h.score) for h in hits if h.chunk_id in rows]
        if recipe.rerank:
            head, tail = found[: recipe.rerank], found[recipe.rerank :]
            scores = self.reranker.scores(query, [r.text for r in head])
            head = sorted((Retrieved(r.chunk, r.document, s) for r, s in zip(head, scores, strict=True)), key=lambda r: -r.score)
            found = head + tail
            record("rerank", [Hit(r.chunk.id, r.score) for r in head])

        documents = {r.chunk.id: r.document.source_id for r in found}
        for stage in stages:
            for hit in stage["hits"]:
                hit["document"] = documents.get(hit["chunk_id"])
        stages.append({"name": "select", "chunk_ids": [r.chunk.id for r in found[: recipe.limit]]})
        trace = RetrievalTrace(index_id=index.id, query=query, config=asdict(recipe), stages=stages, took_ms=round((time.perf_counter() - start) * 1000))
        session.add(trace)
        session.flush()
        return found, trace
