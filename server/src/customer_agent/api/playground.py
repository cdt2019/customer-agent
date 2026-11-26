"""检索测试台：跑一次检索和回答，返回每一步的结果。"""

import time
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from customer_agent import runtime
from customer_agent.api.deps import db
from customer_agent.db import IndexVersion
from customer_agent.rag import answer
from customer_agent.rag.retrieval import Recipe

router = APIRouter()


class RecipeIn(BaseModel):
    dense: bool = True
    keyword: bool = True
    expand: bool = False
    rerank: int = Field(0, ge=0, le=40)
    candidates: int = Field(20, ge=1, le=50)
    limit: int = Field(5, ge=1, le=20)


class PlaygroundIn(BaseModel):
    index_id: int
    question: str = Field(min_length=1, max_length=500)
    recipe: RecipeIn = RecipeIn()
    answer: bool = True


class HitOut(BaseModel):
    chunk_id: int
    score: float


class StageOut(BaseModel):
    name: str  # expand / dense / keyword / fuse / rerank
    ms: int
    query: str | None = None  # 这一路用的查询（开了扩展问题时各路不同）
    queries: list[str] | None = None  # expand 这一步给出的全部查询
    hits: list[HitOut]


class ChunkOut(BaseModel):
    id: int
    document: str
    title: str
    kind: str
    heading_path: list[str]
    text: str


class AnswerOut(BaseModel):
    text: str
    ms: int
    input_tokens: int
    output_tokens: int


class PlaygroundOut(BaseModel):
    trace_id: int
    recipe: RecipeIn
    retrieval_ms: int
    stages: list[StageOut]
    selected: list[int]  # 交给模型的块，按顺序
    chunks: list[ChunkOut]  # 各步里出现过的全部块
    answer: AnswerOut | None
    answer_error: str | None


@router.post("/api/playground")
def playground(body: PlaygroundIn, session: DbSession = Depends(db)) -> PlaygroundOut:
    """跑一次检索（和可选的回答），返回每一步的结果。"""
    index = session.get(IndexVersion, body.index_id)
    if index is None:
        raise HTTPException(404, "没有这个索引版本")
    recipe = Recipe(**body.recipe.model_dump())
    if not (recipe.dense or recipe.keyword):
        raise HTTPException(422, "语义检索和关键词检索至少开一个")
    try:
        retriever = runtime.retriever_for(index, recipe)
    except runtime.MissingKey as error:
        raise HTTPException(422, f"扩展问题用不了：{error}") from error
    found, trace = retriever.retrieve(session, index, body.question, recipe)
    session.commit()

    reply = error = None
    if body.answer:
        started = time.perf_counter()
        try:
            result = answer.from_chunks(runtime.chat_model(), body.question, found[: recipe.limit])
            reply = AnswerOut(text=result.text, ms=round((time.perf_counter() - started) * 1000), input_tokens=result.input_tokens, output_tokens=result.output_tokens)
        except Exception as failure:  # 回答失败不该丢掉已经做完的检索结果
            error = str(failure)

    *steps, select_step = trace.stages
    return PlaygroundOut(
        trace_id=trace.id,
        recipe=RecipeIn(**asdict(recipe)),
        retrieval_ms=trace.took_ms,
        stages=[StageOut(**{k: v for k, v in s.items() if k in StageOut.model_fields}) for s in steps],
        selected=select_step["chunk_ids"],
        chunks=[
            ChunkOut(id=r.chunk.id, document=r.document.source_id, title=r.document.title, kind=r.document.kind, heading_path=r.chunk.heading_path, text=r.chunk.text)
            for r in found
        ],
        answer=reply,
        answer_error=error,
    )
