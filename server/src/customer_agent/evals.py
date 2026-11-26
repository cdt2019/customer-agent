"""评测：拿一批题跑检索（和可选的回答），算分并存下来。

检索的分数由代码直接算；回答是否合格由模型对照参考答案判断。
题目里有 evidence（原文片段）的按块判命中，没有的按文档判。
题集放在 evals/<知识库名>/questions.jsonl。
"""

import json
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from customer_agent import settings
from customer_agent.db import EvalResult, EvalRun, IndexVersion
from customer_agent.llm import ChatModel
from customer_agent.rag.metrics import first_rank, hit_rate, mrr
from customer_agent.rag.retrieval import Retrieved

JUDGE = """你在给客服助手的回答打分。对照「参考要点」判断「回答」是否合格。

合格的条件：说到了参考要点里的关键事实，没有和它矛盾，也没有编造资料以外的承诺。
参考要点说资料里没有时，回答也应该说没有查到，而不是给出具体答案。
只输出两个字：合格 或 不合格。"""

# 给一道题的问题，返回 (排好序的候选, 检索记录编号, 回答)。不检索的做法前两项为空。
Responder = Callable[[str], tuple[list[Retrieved], int | None, str]]


def question_path(kb_name: str) -> Path:
    return settings.EVALS_DIR / kb_name / "questions.jsonl"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def examples(questions: list[dict], limit: int = 4) -> list[str]:
    """挑几道能代表这个知识库的问题：每种题型轮流取，跳过刁钻题和资料里没答案的题。"""
    by_kind: dict[str, list[str]] = defaultdict(list)
    for q in questions:
        if q["kind"] != "trap" and q["expect_docs"]:
            by_kind[q["kind"]].append(q["q"])
    picked: list[str] = []
    for round_ in range(limit):
        picked += [items[round_] for items in by_kind.values() if round_ < len(items)]
    return picked[:limit]


def grade(question: dict, found: list[Retrieved], limit: int) -> tuple[int | None, float | None]:
    """返回 (第一块命中的排在第几, 前 limit 块里找齐了几成证据)。按文档判的题没有第二项。"""
    evidence = question.get("evidence")
    if not evidence:
        return first_rank(question["expect_docs"], list(dict.fromkeys(r.document.source_id for r in found))), None
    relevant = [r.document.source_id in question["expect_docs"] and any(e in r.chunk.text for e in evidence) for r in found]
    rank = relevant.index(True) + 1 if True in relevant else None
    given = "\n".join(r.chunk.text for r in found[:limit])
    return rank, sum(e in given for e in evidence) / len(evidence)


def summarize(ranks: list[int | None]) -> dict[str, float]:
    return {"n": len(ranks), "hit@1": hit_rate(ranks, 1), "hit@3": hit_rate(ranks, 3), "hit@5": hit_rate(ranks, 5), "mrr": mrr(ranks)}


def trend(base_rank: int | None, target_rank: int | None, base_correct: bool | None, target_correct: bool | None) -> str:
    """一道题从基准到对比是变好、变差还是没变。先看检索名次（没找到算最差），名次一样再看回答。"""
    missing = 10**6
    before, after = base_rank or missing, target_rank or missing
    if before != after:
        return "better" if after < before else "worse"
    if base_correct is not None and target_correct is not None and base_correct != target_correct:
        return "better" if target_correct else "worse"
    return "same"


def start(session: Session, index: IndexVersion, question_set: str, config: dict, total: int) -> EvalRun:
    """先记下一次评测，状态是进行中，后台页面马上能看到。"""
    evaluation = EvalRun(index_id=index.id, question_set=question_set, config=config, scores={}, status="running", total=total)
    session.add(evaluation)
    session.commit()
    return evaluation


def execute(
    session: Session, evaluation: EvalRun, questions: list[dict], respond: Responder, limit: int, judge: ChatModel | None, should_stop: Callable[[], bool] = lambda: False
) -> EvalRun:
    """逐题跑完并算分，每题提交一次好让进度看得见。limit 是交给模型的块数；judge 为空时只算检索分数。

    should_stop 亮了就停，这次评测记为已取消，不出分数。
    """
    ranks, by_kind, coverages, verdicts = [], defaultdict(list), [], []
    try:
        for q in questions:
            if should_stop():
                evaluation.status, evaluation.finished_at = "cancelled", datetime.now(UTC)
                session.commit()
                return evaluation
            found, trace_id, text = respond(q["q"])
            rank = coverage = correct = None
            if found and q["expect_docs"]:
                rank, coverage = grade(q, found, limit)
                ranks.append(rank)
                by_kind[q["kind"]].append(rank)
                if coverage is not None:
                    coverages.append(coverage)
            if judge and text:
                verdict = judge.complete(JUDGE, f"问题：{q['q']}\n\n参考要点：{q['answer']}\n\n回答：{text}").text
                correct = "不合格" not in verdict
                verdicts.append(correct)
            session.add(EvalResult(run_id=evaluation.id, question_id=q["id"], rank=rank, coverage=coverage, trace_id=trace_id, answer=text, correct=correct))
            evaluation.done += 1
            session.commit()
    except Exception as error:
        session.rollback()
        evaluation.status, evaluation.error = "failed", repr(error)
        session.commit()
        raise
    scores = {}
    if ranks:
        scores |= summarize(ranks) | {"by_kind": {kind: summarize(r) for kind, r in sorted(by_kind.items())}}
    if coverages:
        scores["evidence"] = sum(coverages) / len(coverages)
    if verdicts:
        scores |= {"answered": len(verdicts), "correct": sum(verdicts) / len(verdicts)}
    evaluation.scores = json.loads(json.dumps(scores), parse_float=lambda x: round(float(x), 3))
    evaluation.status, evaluation.finished_at = "done", datetime.now(UTC)
    session.commit()
    return evaluation
