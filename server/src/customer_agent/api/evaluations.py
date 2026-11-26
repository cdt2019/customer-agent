"""评测：看历次记录、发起一次、逐题对比两次。"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from customer_agent import evals, runtime
from customer_agent.api.control import maintenance, stop
from customer_agent.api.deps import db
from customer_agent.api.playground import RecipeIn
from customer_agent.db import EvalResult, EvalRun, IndexVersion, KnowledgeBase, Session
from customer_agent.rag.retrieval import Recipe

router = APIRouter()


class KindScores(BaseModel):
    n: int
    hit1: float
    hit3: float
    hit5: float
    mrr: float


class Scores(BaseModel):
    retrieval: KindScores | None
    by_kind: dict[str, KindScores]
    evidence: float | None
    answered: int | None
    correct: float | None


class RunOut(BaseModel):
    id: int
    index_id: int
    index_name: str
    embed_model: str
    chunker: str
    chunk_size: int
    answers: str | None  # 空是只检索；retrieve 检索后回答；full 整库放进提示词
    recipe: RecipeIn | None  # 整库放进提示词时没有检索配方
    status: str
    done: int
    total: int
    error: str
    scores: Scores
    created_at: datetime


def kind_scores(raw: dict) -> KindScores:
    return KindScores(n=raw["n"], hit1=raw["hit@1"], hit3=raw["hit@3"], hit5=raw["hit@5"], mrr=raw["mrr"])


def run_out(run: EvalRun, index: IndexVersion) -> RunOut:
    s, c = run.scores, run.config
    return RunOut(
        id=run.id,
        index_id=index.id,
        index_name=index.name,
        embed_model=index.embed_model,
        chunker=index.chunker,
        chunk_size=index.chunk_size,
        answers=c.get("answers"),
        recipe=RecipeIn(**{k: c[k] for k in RecipeIn.model_fields}) if "dense" in c else None,
        status=run.status,
        done=run.done,
        total=run.total,
        error=run.error,
        scores=Scores(
            retrieval=kind_scores(s) if "n" in s else None,
            by_kind={kind: kind_scores(v) for kind, v in s.get("by_kind", {}).items()},
            evidence=s.get("evidence"),
            answered=s.get("answered"),
            correct=s.get("correct"),
        ),
        created_at=run.created_at,
    )


@router.get("/api/evals/runs")
def runs(kb_id: int, session: DbSession = Depends(db)) -> list[RunOut]:
    """这个知识库的评测记录，新的在前。"""
    rows = session.execute(select(EvalRun, IndexVersion).join(IndexVersion).where(IndexVersion.kb_id == kb_id).order_by(EvalRun.id.desc()))
    return [run_out(run, index) for run, index in rows]


class RunIn(BaseModel):
    index_id: int
    recipe: RecipeIn = RecipeIn()
    answers: bool = False  # 同时生成回答并判分，会调用模型、产生花费


def run_in_background(run_id: int, recipe: Recipe, answers: str | None) -> None:
    with Session() as session:
        evaluation = session.get(EvalRun, run_id)
        index = session.get(IndexVersion, evaluation.index_id)
        questions = evals.load(evals.question_path(evaluation.question_set))
        try:
            respond, llm = runtime.responder(session, index, recipe, answers)
        except Exception as error:  # 模型加载失败时 execute 还没开始，要在这里记下
            evaluation.status, evaluation.error = "failed", repr(error)
            session.commit()
            return
        try:
            evals.execute(session, evaluation, questions, respond, recipe.limit, llm, stop.is_set)
        except Exception:  # execute 已经把失败原因记进这次评测，页面上看得到
            return


def launch(session: DbSession, index: IndexVersion, recipe_in: RecipeIn, with_answers: bool, background: BackgroundTasks) -> EvalRun:
    """发起一次评测，在后台跑。显卡只有一张，同一时间只跑一次。"""
    if session.scalar(select(EvalRun.id).where(EvalRun.status == "running").limit(1)):
        raise HTTPException(409, "已经有一次评测在跑，等它结束再发起")
    if maintenance.locked():
        raise HTTPException(409, "索引正在更新，等它结束再评测")
    recipe = Recipe(**recipe_in.model_dump())
    if not (recipe.dense or recipe.keyword):
        raise HTTPException(422, "语义检索和关键词检索至少开一个")
    kb = session.get(KnowledgeBase, index.kb_id)
    path = evals.question_path(kb.name)
    if not path.exists():
        raise HTTPException(422, "这个知识库还没有评测题")
    if with_answers or recipe.expand:
        try:
            runtime.chat_model()
        except runtime.MissingKey as error:
            raise HTTPException(422, str(error)) from error
    answers = "retrieve" if with_answers else None
    evaluation = evals.start(session, index, kb.name, {**recipe_in.model_dump(), "answers": answers}, len(evals.load(path)))
    stop.clear()
    background.add_task(run_in_background, evaluation.id, recipe, answers)
    return evaluation


@router.post("/api/evals/runs", status_code=202)
def create_run(body: RunIn, background: BackgroundTasks, session: DbSession = Depends(db)) -> RunOut:
    index = session.get(IndexVersion, body.index_id)
    if index is None:
        raise HTTPException(404, "没有这个索引版本")
    return run_out(launch(session, index, body.recipe, body.answers, background), index)


class ResultOut(BaseModel):
    rank: int | None
    coverage: float | None
    correct: bool | None
    answer: str


class CompareRow(BaseModel):
    id: str
    question: str
    kind: str
    expect_docs: list[str]
    evidence: list[str]
    reference: str
    trend: str  # better / worse / same
    base: ResultOut | None
    target: ResultOut | None


def results_of(session: DbSession, run_id: int) -> dict[str, ResultOut]:
    rows = session.scalars(select(EvalResult).where(EvalResult.run_id == run_id))
    return {r.question_id: ResultOut(rank=r.rank, coverage=r.coverage, correct=r.correct, answer=r.answer) for r in rows}


@router.get("/api/evals/compare")
def compare(base: int, target: int, session: DbSession = Depends(db)) -> list[CompareRow]:
    """逐题对比两次评测。两次必须用的是同一个题集。"""
    first, second = session.get(EvalRun, base), session.get(EvalRun, target)
    if first is None or second is None:
        raise HTTPException(404, "没有这次评测")
    if first.question_set != second.question_set:
        raise HTTPException(422, "两次评测用的不是同一个题集")
    before, after = results_of(session, base), results_of(session, target)
    rows = []
    for q in evals.load(evals.question_path(first.question_set)):
        b, t = before.get(q["id"]), after.get(q["id"])
        change = evals.trend(b.rank, t.rank, b.correct, t.correct) if b and t else "same"
        rows.append(
            CompareRow(
                id=q["id"], question=q["q"], kind=q["kind"], expect_docs=q["expect_docs"], evidence=q.get("evidence", []),
                reference=q["answer"], trend=change, base=b, target=t,
            )
        )
    return rows
