"""导入：把来源里的文档同步进数据库，再让一个索引版本和数据库里的文档对齐。

两步都可以反复执行：没变的跳过，中途断了重跑就接着做。
"""

import hashlib
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from customer_agent.db import Chunk, Document, IndexVersion, IngestJob, KnowledgeBase
from customer_agent.rag.chunkers import CHUNKERS, titled
from customer_agent.rag.embedders import Embedder
from customer_agent.rag.sources import SourceDoc
from customer_agent.rag.stores import QdrantStore


def content_hash(doc: SourceDoc) -> str:
    return hashlib.sha256(f"{doc.title}\n{doc.kind}\n{doc.markdown}".encode()).hexdigest()


def save_upload(session: Session, kb: KnowledgeBase, doc: SourceDoc) -> None:
    """把确认过的导入文件写进知识库；同名文件覆盖。由调用方提交。"""
    query = select(Document).where(Document.kb_id == kb.id, Document.source_id == doc.source_id, Document.lang == doc.lang)
    row = session.scalars(query).one_or_none()
    if row is None:
        row = Document(kb_id=kb.id, source_id=doc.source_id, lang=doc.lang, origin="upload")
        session.add(row)
    row.title, row.kind, row.markdown, row.content_hash = doc.title, doc.kind, doc.markdown, content_hash(doc)


def sync(session: Session, kb: KnowledgeBase, docs: Iterable[SourceDoc]) -> dict[str, int]:
    """让知识库里的文档和来源一致：新的加上，变了的更新，来源里没有的删掉。导入的文件不归文件夹管，不受影响。"""
    existing = {(d.source_id, d.lang): d for d in session.scalars(select(Document).where(Document.kb_id == kb.id, Document.origin == "folder"))}
    counts = {"added": 0, "updated": 0, "unchanged": 0, "removed": len(existing)}
    for doc in docs:
        digest = content_hash(doc)
        row = existing.pop((doc.source_id, doc.lang), None)
        if row is None:
            row = Document(kb_id=kb.id, source_id=doc.source_id, lang=doc.lang)
            session.add(row)
            counts["added"] += 1
        elif row.content_hash == digest:
            counts["unchanged"] += 1
            continue
        else:
            counts["updated"] += 1
        row.title, row.kind, row.markdown, row.content_hash = doc.title, doc.kind, doc.markdown, digest
    for row in existing.values():
        session.delete(row)
    counts["removed"] = len(existing)
    session.commit()
    return counts


def stale(session: Session, index: IndexVersion) -> list[Document]:
    """内容变了、这个索引还没跟上的文档。"""
    docs = session.scalars(select(Document).where(Document.kb_id == index.kb_id)).all()
    done = set(session.execute(select(Chunk.document_id, Chunk.doc_hash).where(Chunk.index_id == index.id).distinct()))
    return [d for d in docs if (d.id, d.content_hash) not in done]


def clear(session: Session, index: IndexVersion) -> None:
    """清掉这个索引的块，下一次 refresh 会全部重做，并把向量库里多余的点删掉。"""
    session.execute(delete(Chunk).where(Chunk.index_id == index.id))
    session.commit()


def refresh(
    session: Session, index: IndexVersion, embedder: Embedder, store: QdrantStore, kind: str = "update", should_stop: Callable[[], bool] = lambda: False
) -> IngestJob:
    """重切并重算内容变了的文档，最后删掉向量库里多余的点。should_stop 亮了就做完手头这篇停下，下次接着做。"""
    todo = stale(session, index)
    job = IngestJob(index_id=index.id, kind=kind, total=len(todo), progress={"chunk": 0, "embed": 0, "store": 0})
    session.add(job)
    session.commit()

    def step(name: str) -> None:
        job.progress = {**job.progress, name: job.progress[name] + 1}

    try:
        store.ensure(index.collection, embedder.dim)
        for doc in todo:
            if should_stop():
                job.status = "cancelled"
                return job
            session.execute(delete(Chunk).where(Chunk.index_id == index.id, Chunk.document_id == doc.id))
            pieces = CHUNKERS[index.chunker](doc.markdown, index.chunk_size, index.overlap)
            rows = [
                Chunk(index_id=index.id, document_id=doc.id, doc_hash=doc.content_hash, seq=n, heading_path=list(p.heading_path), text=p.text)
                for n, p in enumerate(pieces)
            ]
            session.add_all(rows)
            session.flush()
            step("chunk")
            if rows:
                texts = [titled(doc.title, r.heading_path, r.text) for r in rows]
                started = time.perf_counter()
                vectors = embedder.documents(texts)
                job.embed_ms += round((time.perf_counter() - started) * 1000)
                job.embedded_chunks += len(rows)
                step("embed")
                store.add(index.collection, [r.id for r in rows], vectors, texts)
            step("store")
            session.commit()  # 一篇一提交：断了重跑时，做完的不用重做
        kept = set(session.scalars(select(Chunk.id).where(Chunk.index_id == index.id)))
        store.keep_only(index.collection, kept)
        job.status = "done"
    except Exception as error:
        session.rollback()
        job.status, job.error = "failed", repr(error)
        raise
    finally:
        job.finished_at = datetime.now(UTC)
        session.commit()
    return job
