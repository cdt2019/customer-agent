"""数据集：看文档和切出来的块，把资料同步进来，重建索引。"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from customer_agent import kb_sources, runtime
from customer_agent.api.control import maintenance, stop
from customer_agent.api.deps import db
from customer_agent.db import Chunk, Document, EvalRun, IndexVersion, IngestJob, KnowledgeBase, Session
from customer_agent.rag import ingest

router = APIRouter()
log = logging.getLogger(__name__)


class DocumentRow(BaseModel):
    id: int
    source_id: str
    lang: str
    title: str
    kind: str
    chars: int
    chunks: int
    stale: bool  # 文档改过，这个索引还没跟上


class JobOut(BaseModel):
    status: str
    total: int
    progress: dict[str, int]
    error: str
    finished_at: datetime | None


class DatasetOut(BaseModel):
    documents: list[DocumentRow]
    chunks: int
    average_chars: int
    embed_model: str
    can_sync: bool  # 这个知识库记着资料来源，才能从页面同步
    busy: bool
    last_job: JobOut | None


@router.get("/api/indexes/{index_id}/dataset")
def dataset(index_id: int, session: DbSession = Depends(db)) -> DatasetOut:
    index = session.get(IndexVersion, index_id)
    if index is None:
        raise HTTPException(404, "没有这个索引版本")
    kb = session.get(KnowledgeBase, index.kb_id)
    counts = {
        document_id: (count, chars)
        for document_id, count, chars in session.execute(
            select(Chunk.document_id, func.count(), func.sum(func.length(Chunk.text))).where(Chunk.index_id == index.id).group_by(Chunk.document_id)
        )
    }
    stale = {doc.id for doc in ingest.stale(session, index)}
    rows = session.execute(
        select(Document.id, Document.source_id, Document.lang, Document.title, Document.kind, func.length(Document.markdown))
        .where(Document.kb_id == index.kb_id)
        .order_by(Document.kind, Document.source_id, Document.lang)
    ).all()
    total = sum(count for count, _ in counts.values())
    job = session.scalars(select(IngestJob).where(IngestJob.index_id == index.id).order_by(IngestJob.id.desc()).limit(1)).first()
    return DatasetOut(
        documents=[
            DocumentRow(id=r[0], source_id=r[1], lang=r[2], title=r[3], kind=r[4], chars=r[5], chunks=counts.get(r[0], (0, 0))[0], stale=r[0] in stale)
            for r in rows
        ],
        chunks=total,
        average_chars=round(sum(chars for _, chars in counts.values()) / total) if total else 0,
        embed_model=index.embed_model,
        can_sync=kb.source is not None,
        busy=maintenance.locked(),
        last_job=JobOut(status=job.status, total=job.total, progress=job.progress, error=job.error, finished_at=job.finished_at) if job else None,
    )


class ChunkRow(BaseModel):
    id: int
    seq: int
    heading_path: list[str]
    text: str


class DocumentDetail(BaseModel):
    id: int
    title: str
    kind: str
    markdown: str
    chunks: list[ChunkRow]


@router.get("/api/indexes/{index_id}/documents/{document_id}")
def document(index_id: int, document_id: int, session: DbSession = Depends(db)) -> DocumentDetail:
    index, doc = session.get(IndexVersion, index_id), session.get(Document, document_id)
    if index is None or doc is None or doc.kb_id != index.kb_id:
        raise HTTPException(404, "没有这篇文档")
    chunks = session.scalars(select(Chunk).where(Chunk.index_id == index.id, Chunk.document_id == doc.id).order_by(Chunk.seq))
    return DocumentDetail(
        id=doc.id,
        title=doc.title,
        kind=doc.kind,
        markdown=doc.markdown,
        chunks=[ChunkRow(id=c.id, seq=c.seq, heading_path=c.heading_path, text=c.text) for c in chunks],
    )


def maintain(index_id: int, sync: bool, rebuild: bool, kind: str) -> None:
    """在后台同步资料和更新索引。失败原因记进任务，页面上看得到。"""
    try:
        with Session() as session:
            index = session.get(IndexVersion, index_id)
            if sync:
                kb = session.get(KnowledgeBase, index.kb_id)
                try:
                    ingest.sync(session, kb, kb_sources.documents(kb.source))
                except Exception as error:
                    session.rollback()
                    session.add(IngestJob(index_id=index.id, kind=kind, status="failed", error=f"同步失败：{error!r}", finished_at=datetime.now(UTC)))
                    session.commit()
                    return
            if rebuild:
                ingest.clear(session, index)
            ingest.refresh(session, index, runtime.embedder(index.embed_model), runtime.store(), kind, stop.is_set)
    except Exception:  # refresh 已经把原因记进任务
        log.exception("更新索引失败")
    finally:
        maintenance.release()


def require_idle(session: DbSession) -> None:
    if session.scalar(select(EvalRun.id).where(EvalRun.status == "running").limit(1)):
        raise HTTPException(409, "有一次评测在跑，等它结束再更新索引")
    if maintenance.locked():
        raise HTTPException(409, "已经有一个同步或建索引的任务在跑")


def start(index_id: int, background: BackgroundTasks, session: DbSession, sync: bool, rebuild: bool, kind: str) -> None:
    index = session.get(IndexVersion, index_id)
    if index is None:
        raise HTTPException(404, "没有这个索引版本")
    if sync:
        if not kb_sources.available(session.get(KnowledgeBase, index.kb_id).source):
            raise HTTPException(422, "这个知识库没有可用的资料来源，先用命令行 agent sync 导入一次")
    require_idle(session)
    if not maintenance.acquire(blocking=False):
        raise HTTPException(409, "已经有一个同步或建索引的任务在跑")
    stop.clear()
    background.add_task(maintain, index.id, sync, rebuild, kind)


@router.post("/api/indexes/{index_id}/sync", status_code=202)
def sync_index(index_id: int, background: BackgroundTasks, session: DbSession = Depends(db)) -> None:
    """重新读资料来源，只重算变了的文档。"""
    start(index_id, background, session, sync=True, rebuild=False, kind="sync")


@router.post("/api/indexes/{index_id}/rebuild", status_code=202)
def rebuild_index(index_id: int, background: BackgroundTasks, session: DbSession = Depends(db)) -> None:
    """清掉这个索引的块，全部重切重算。"""
    start(index_id, background, session, sync=False, rebuild=True, kind="rebuild")
