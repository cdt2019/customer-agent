"""知识库和索引版本。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from customer_agent import evals
from customer_agent.api.deps import db
from customer_agent.db import Chunk, Document, IndexVersion, KnowledgeBase

router = APIRouter()


def question_count(kb_name: str) -> int:
    path = evals.question_path(kb_name)
    return len(evals.load(path)) if path.exists() else 0


class IndexOut(BaseModel):
    id: int
    name: str
    chunker: str
    chunk_size: int
    overlap: int
    embed_model: str
    chunks: int


class KnowledgeBaseOut(BaseModel):
    id: int
    name: str
    documents: int
    questions: int  # 这个知识库的评测题数，没有题集时是 0
    indexes: list[IndexOut]


@router.get("/api/knowledge-bases/{kb_id}/example-questions")
def example_questions(kb_id: int, session: DbSession = Depends(db)) -> list[str]:
    """测试台初始状态给的示例问题，没有题集时为空。"""
    kb = session.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "没有这个知识库")
    path = evals.question_path(kb.name)
    return evals.examples(evals.load(path)) if path.exists() else []


@router.get("/api/knowledge-bases")
def knowledge_bases(session: DbSession = Depends(db)) -> list[KnowledgeBaseOut]:
    documents = dict(session.execute(select(Document.kb_id, func.count()).group_by(Document.kb_id)).all())
    chunks = dict(session.execute(select(Chunk.index_id, func.count()).group_by(Chunk.index_id)).all())
    indexes = session.scalars(select(IndexVersion).order_by(IndexVersion.id)).all()
    return [
        KnowledgeBaseOut(
            id=kb.id,
            name=kb.name,
            documents=documents.get(kb.id, 0),
            questions=question_count(kb.name),
            indexes=[
                IndexOut(id=i.id, name=i.name, chunker=i.chunker, chunk_size=i.chunk_size, overlap=i.overlap, embed_model=i.embed_model, chunks=chunks.get(i.id, 0))
                for i in indexes
                if i.kb_id == kb.id
            ],
        )
        for kb in session.scalars(select(KnowledgeBase).order_by(KnowledgeBase.id))
    ]
