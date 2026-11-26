"""任务：把建索引和评测放在一张列表里看，能取消进行中的，能重试没做完的。"""

from datetime import datetime
from typing import Literal

import torch
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from customer_agent.api import control, datasets, evaluations
from customer_agent.api.deps import db
from customer_agent.api.playground import RecipeIn
from customer_agent.db import EvalRun, IndexVersion, IngestJob, KnowledgeBase

router = APIRouter()

LIMIT = 100
JOB_TITLE = {"update": "更新索引", "sync": "同步资料", "rebuild": "重建索引", "build": "建索引"}
STAGE_LABEL = {"chunk": "切块", "embed": "向量化", "store": "入库"}


class TaskStage(BaseModel):
    name: str
    done: int
    total: int


class TaskOut(BaseModel):
    type: Literal["index", "eval"]
    id: int
    title: str
    knowledge_base: str
    index_id: int
    index_name: str
    status: str  # running / done / failed / cancelled
    done: int
    total: int
    stages: list[TaskStage]
    error: str
    retryable: bool
    started_at: datetime
    finished_at: datetime | None


class TasksOut(BaseModel):
    tasks: list[TaskOut]
    device: str
    embed_speed: float | None  # 最近一次建索引的向量化速度，块/秒


@router.get("/api/tasks")
def tasks(session: DbSession = Depends(db)) -> TasksOut:
    """最近的任务，新的在前。"""
    indexes = {index.id: index for index in session.scalars(select(IndexVersion))}
    kbs = {kb.id: kb.name for kb in session.scalars(select(KnowledgeBase))}
    out, seen = [], set()  # 只有每个索引最新的一个任务才值得接着做，更早失败的已经被后来的任务补上了
    for job in session.scalars(select(IngestJob).order_by(IngestJob.id.desc()).limit(LIMIT)):
        index = indexes[job.index_id]
        progress = job.progress or {}
        latest = index.id not in seen
        seen.add(index.id)
        out.append(
            TaskOut(
                type="index",
                id=job.id,
                title=JOB_TITLE[job.kind],
                knowledge_base=kbs[index.kb_id],
                index_id=index.id,
                index_name=index.name,
                status=job.status,
                done=progress.get("store", 0),
                total=job.total,
                stages=[TaskStage(name=label, done=progress.get(key, 0), total=job.total) for key, label in STAGE_LABEL.items()],
                error=job.error,
                retryable=latest and job.status in ("failed", "cancelled"),
                started_at=job.started_at,
                finished_at=job.finished_at,
            )
        )
    for run in session.scalars(select(EvalRun).order_by(EvalRun.id.desc()).limit(LIMIT)):
        index = indexes[run.index_id]
        out.append(
            TaskOut(
                type="eval",
                id=run.id,
                title="评测" + ("（含回答）" if run.config.get("answers") else ""),
                knowledge_base=kbs[index.kb_id],
                index_id=index.id,
                index_name=index.name,
                status=run.status,
                done=run.done,
                total=run.total,
                stages=[TaskStage(name="答题", done=run.done, total=run.total)],
                error=run.error,
                # 整库放进提示词很贵，只能从命令行发起
                retryable=run.status in ("failed", "cancelled") and "dense" in run.config,
                started_at=run.created_at,
                finished_at=run.finished_at,
            )
        )
    out.sort(key=lambda task: task.started_at, reverse=True)
    speed = session.scalars(select(IngestJob).where(IngestJob.embed_ms > 0).order_by(IngestJob.id.desc()).limit(1)).first()
    return TasksOut(
        tasks=out[:LIMIT],
        device=torch.cuda.get_device_name(0) if torch.cuda.is_available() else "处理器",
        embed_speed=round(speed.embedded_chunks / speed.embed_ms * 1000, 1) if speed else None,
    )


@router.post("/api/tasks/cancel", status_code=202)
def cancel(session: DbSession = Depends(db)) -> None:
    """让进行中的任务做完手头这一篇或这一题就停。"""
    evaluating = session.scalar(select(EvalRun.id).where(EvalRun.status == "running").limit(1))
    if not (evaluating or control.maintenance.locked()):
        raise HTTPException(409, "现在没有进行中的任务")
    control.stop.set()


@router.post("/api/tasks/index/{job_id}/retry", status_code=202)
def retry_index(job_id: int, background: BackgroundTasks, session: DbSession = Depends(db)) -> None:
    """接着做：做完的文档不重算。同步失败的会重新读一遍资料。"""
    job = session.get(IngestJob, job_id)
    if job is None or job.status not in ("failed", "cancelled"):
        raise HTTPException(409, "这个任务不需要重试")
    datasets.start(job.index_id, background, session, sync=job.kind == "sync", rebuild=False, kind=job.kind)


@router.post("/api/tasks/eval/{run_id}/retry", status_code=202)
def retry_eval(run_id: int, background: BackgroundTasks, session: DbSession = Depends(db)) -> None:
    """按同样的配方新跑一次评测。"""
    run = session.get(EvalRun, run_id)
    if run is None or run.status not in ("failed", "cancelled") or "dense" not in run.config:
        raise HTTPException(409, "这次评测不能从页面重试")
    recipe = RecipeIn(**{key: run.config[key] for key in RecipeIn.model_fields})
    evaluations.launch(session, session.get(IndexVersion, run.index_id), recipe, bool(run.config.get("answers")), background)
