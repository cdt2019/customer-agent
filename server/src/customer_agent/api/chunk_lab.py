"""切块实验室：改参数马上看切出来的样子，只算不写库；满意了再存成新的索引版本。"""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from customer_agent.api import datasets
from customer_agent.api.deps import db
from customer_agent.db import Document, IndexVersion
from customer_agent.rag.chunkers import CHUNKERS, overlaps

router = APIRouter()

SHORT = 60  # 比这还短的块，通常信息不够


class Settings(BaseModel):
    chunker: Literal["heading", "fixed"]
    size: int = Field(ge=100, le=1200)
    overlap: int = Field(ge=0, le=300)

    @model_validator(mode="after")
    def overlap_below_half(self) -> "Settings":
        if self.overlap * 2 > self.size:
            raise ValueError("重叠不能超过块大小的一半")
        return self


class ChunkStats(BaseModel):
    count: int
    average: int
    shortest: int
    longest: int
    short: int  # 过短的块数
    long: int  # 超过「块大小 + 重叠」的块数


def stats(lengths: list[int], limit: int) -> ChunkStats:
    if not lengths:
        return ChunkStats(count=0, average=0, shortest=0, longest=0, short=0, long=0)
    return ChunkStats(
        count=len(lengths),
        average=round(sum(lengths) / len(lengths)),
        shortest=min(lengths),
        longest=max(lengths),
        short=sum(n < SHORT for n in lengths),
        long=sum(n > limit for n in lengths),
    )


class PreviewIn(Settings):
    index_id: int  # 拿来对比的索引版本
    document_id: int


class PreviewChunk(BaseModel):
    heading_path: list[str]
    text: str
    overlap: int  # 开头有多少字和上一块重复


class Comparison(BaseModel):
    candidate: ChunkStats
    current: ChunkStats


class PreviewOut(BaseModel):
    chunks: list[PreviewChunk]
    document: Comparison
    knowledge_base: Comparison


@router.post("/api/chunk-lab/preview")
def preview(body: PreviewIn, session: DbSession = Depends(db)) -> PreviewOut:
    index, doc = session.get(IndexVersion, body.index_id), session.get(Document, body.document_id)
    if index is None or doc is None or doc.kb_id != index.kb_id:
        raise HTTPException(404, "没有这篇文档")

    def lengths(markdown: str, chunker: str, size: int, overlap: int) -> list[int]:
        return [len(c.text) for c in CHUNKERS[chunker](markdown, size, overlap)]

    pieces = CHUNKERS[body.chunker](doc.markdown, body.size, body.overlap)
    shared = overlaps(doc.markdown, [p.text for p in pieces])
    everything = session.scalars(select(Document.markdown).where(Document.kb_id == index.kb_id)).all()
    candidate = [n for markdown in everything for n in lengths(markdown, body.chunker, body.size, body.overlap)]
    current = [n for markdown in everything for n in lengths(markdown, index.chunker, index.chunk_size, index.overlap)]
    return PreviewOut(
        chunks=[PreviewChunk(heading_path=list(p.heading_path), text=p.text, overlap=n) for p, n in zip(pieces, shared, strict=True)],
        document=Comparison(
            candidate=stats([len(p.text) for p in pieces], body.size + body.overlap),
            current=stats(lengths(doc.markdown, index.chunker, index.chunk_size, index.overlap), index.chunk_size + index.overlap),
        ),
        knowledge_base=Comparison(candidate=stats(candidate, body.size + body.overlap), current=stats(current, index.chunk_size + index.overlap)),
    )


class SaveIn(Settings):
    index_id: int  # 新版本沿用它的知识库和向量模型
    name: str = Field(min_length=1, max_length=50, pattern=r"^[\w.-]+$")


class SaveOut(BaseModel):
    id: int


@router.post("/api/chunk-lab/indexes", status_code=202)
def save(body: SaveIn, background: BackgroundTasks, session: DbSession = Depends(db)) -> SaveOut:
    """存成新的索引版本并开始建索引。在用的版本不受影响。"""
    base = session.get(IndexVersion, body.index_id)
    if base is None:
        raise HTTPException(404, "没有这个索引版本")
    siblings = session.scalars(select(IndexVersion).where(IndexVersion.kb_id == base.kb_id)).all()
    if any(item.name == body.name for item in siblings):
        raise HTTPException(409, f"已经有叫 {body.name} 的索引版本")
    for item in siblings:
        if (item.chunker, item.chunk_size, item.overlap, item.embed_model) == (body.chunker, body.size, body.overlap, base.embed_model):
            raise HTTPException(409, f"索引版本 {item.name} 已经是这组设置")
    datasets.require_idle(session)
    index = IndexVersion(kb_id=base.kb_id, name=body.name, chunker=body.chunker, chunk_size=body.size, overlap=body.overlap, embed_model=base.embed_model)
    session.add(index)
    session.commit()
    datasets.start(index.id, background, session, sync=False, rebuild=False, kind="build")
    return SaveOut(id=index.id)
