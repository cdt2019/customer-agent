"""导入、检索、评测串起来的测试。

数据库用内存里的 SQLite；向量用按字计数的假模型；向量库用本机的 Qdrant（关键词检索要它来分词），
集合名带随机前缀，测完删掉。Qdrant 没开时这组测试跳过。
"""

import uuid

import numpy as np
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from customer_agent import evals, settings
from customer_agent.db import Base, Chunk, Document, EvalResult, IndexVersion, KnowledgeBase, RetrievalTrace
from customer_agent.rag import ingest
from customer_agent.rag.retrieval import Recipe, Retriever, rrf
from customer_agent.rag.sources import SourceDoc
from customer_agent.rag.stores import Hit, QdrantStore


class CharEmbedder:
    """每个字一个维度，文字里出现几次就是几。字面相近的向量就相近。"""

    dim = 512

    def documents(self, texts: list[str]) -> np.ndarray:
        return np.stack([self.query(t) for t in texts])

    def query(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim)
        for char in text:
            vector[ord(char) % self.dim] += 1
        return vector / (np.linalg.norm(vector) or 1)


class SplitInTwo:
    """假的回答模型：不管问什么，都给出固定的两条改写。"""

    def complete(self, system: str, user: str):
        return type("Reply", (), {"text": "- 质保期如何计算\n- USDT-BEP20 转账"})()


class KeywordReranker:
    """含「质保」的排前面，用来确认重排真的改了顺序。"""

    def scores(self, query: str, texts: list[str]) -> list[float]:
        return [float("质保" in text) for text in texts]


def doc(source_id: str, body: str) -> SourceDoc:
    return SourceDoc(source_id=source_id, lang="zh", title=source_id, kind="faq", markdown=body)


DOCS = [
    doc("delivery", "## 到货\n\n付款到账后一分钟内自动发货。\n"),
    doc("warranty", "## 质保\n\n质保期从交付时间开始计算。\n"),
    doc("usdt", "## 链上付款\n\n使用 USDT-BEP20 转账，网络确认需要几分钟。\n"),
]


@pytest.fixture
def world():
    store = QdrantStore(settings.QDRANT_URL, namespace=f"test_{uuid.uuid4().hex[:8]}_")
    engine = create_engine("sqlite://")
    # SQLite 默认不执行外键的级联删除，PostgreSQL 会；打开它，行为才一致
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        kb = KnowledgeBase(name="test")
        session.add(kb)
        session.flush()
        index = IndexVersion(kb_id=kb.id, name="v1", chunker="heading", chunk_size=200, overlap=0, embed_model="fake")
        session.add(index)
        session.commit()
        embedder = CharEmbedder()
        try:
            store.ensure(index.collection, embedder.dim)
        except Exception:
            pytest.skip("本机的 Qdrant 没有开")
        yield session, kb, index, Retriever(embedder, store, KeywordReranker(), SplitInTwo())
        store.drop(index.collection)


def build(world) -> None:
    session, kb, index, retriever = world
    ingest.sync(session, kb, DOCS)
    ingest.refresh(session, index, retriever.embedder, retriever.store)


def test_rrf_rewards_chunks_found_by_both_routes():
    fused = rrf([[Hit(1, 0.9), Hit(2, 0.8)], [Hit(3, 12.0), Hit(2, 7.0)]])
    assert [h.chunk_id for h in fused] == [2, 1, 3]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 62)


def test_sync_reports_what_changed(world):
    session, kb, *_ = world
    assert ingest.sync(session, kb, DOCS) == {"added": 3, "updated": 0, "unchanged": 0, "removed": 0}
    assert ingest.sync(session, kb, DOCS) == {"added": 0, "updated": 0, "unchanged": 3, "removed": 0}
    changed = [doc("delivery", "## 到货\n\n周末也发货。\n")]
    assert ingest.sync(session, kb, changed) == {"added": 0, "updated": 1, "unchanged": 0, "removed": 2}


def test_sync_leaves_uploaded_documents_alone(world):
    session, kb, *_ = world
    ingest.sync(session, kb, DOCS)
    ingest.save_upload(session, kb, doc("upload/手册.pdf", "## 手册\n\n正文。\n"))
    session.commit()
    assert ingest.sync(session, kb, DOCS) == {"added": 0, "updated": 0, "unchanged": 3, "removed": 0}
    ingest.save_upload(session, kb, doc("upload/手册.pdf", "## 手册\n\n改过了。\n"))
    session.commit()
    rows = session.scalars(select(Document).where(Document.origin == "upload")).all()
    assert len(rows) == 1 and "改过了" in rows[0].markdown


def test_refresh_only_redoes_changed_documents_and_cleans_the_store(world):
    session, kb, index, retriever = world
    ingest.sync(session, kb, DOCS)
    first = ingest.refresh(session, index, retriever.embedder, retriever.store)
    assert (first.status, first.total, first.progress) == ("done", 3, {"chunk": 3, "embed": 3, "store": 3})
    assert ingest.refresh(session, index, retriever.embedder, retriever.store).total == 0

    ingest.sync(session, kb, [doc("delivery", "## 到货\n\n周末也发货。\n")])
    assert ingest.refresh(session, index, retriever.embedder, retriever.store).total == 1
    assert session.scalar(select(func.count()).select_from(Chunk)) == 1
    found, _ = retriever.retrieve(session, index, "质保期怎么算", Recipe())
    assert [r.document.source_id for r in found] == ["delivery"]  # 删掉的文档在向量库里也没了


def test_stale_and_clear(world):
    session, kb, index, retriever = world
    build(world)
    assert ingest.stale(session, index) == []
    ingest.sync(session, kb, [doc("delivery", "## 到货\n\n周末也发货。\n"), *DOCS[1:]])
    assert [d.source_id for d in ingest.stale(session, index)] == ["delivery"]
    ingest.clear(session, index)
    assert session.scalar(select(func.count()).select_from(Chunk)) == 0
    assert ingest.refresh(session, index, retriever.embedder, retriever.store).total == 3
    assert session.scalar(select(func.count()).select_from(Chunk)) == 3


def test_dense_retrieval_records_a_trace(world):
    session, _, index, retriever = world
    build(world)
    found, trace = retriever.retrieve(session, index, "质保期从什么时候开始", Recipe(limit=1))
    assert found[0].document.source_id == "warranty"
    assert found[0].text == "warranty › 质保\n质保期从交付时间开始计算。"
    saved = session.get(RetrievalTrace, trace.id)
    assert [s["name"] for s in saved.stages] == ["dense", "select"]
    assert saved.stages[0]["hits"][0]["document"] == "warranty"
    assert saved.stages[1]["chunk_ids"] == [found[0].chunk.id]
    assert saved.config == {"dense": True, "keyword": False, "expand": False, "rerank": 0, "candidates": 20, "limit": 1}


def test_keyword_route_finds_exact_terms_in_chinese_and_latin(world):
    session, _, index, retriever = world
    build(world)
    only_keyword = Recipe(dense=False, keyword=True)
    found, trace = retriever.retrieve(session, index, "BEP20", only_keyword)
    assert [r.document.source_id for r in found] == ["usdt"]
    found, _ = retriever.retrieve(session, index, "质保", only_keyword)
    assert [r.document.source_id for r in found] == ["warranty"]
    assert [s["name"] for s in trace.stages] == ["keyword", "select"]


def test_hybrid_fuses_and_rerank_reorders(world):
    session, _, index, retriever = world
    build(world)
    found, trace = retriever.retrieve(session, index, "付款后多久发货", Recipe(keyword=True, rerank=20))
    assert [s["name"] for s in trace.stages] == ["dense", "keyword", "fuse", "rerank", "select"]
    assert found[0].document.source_id == "warranty" and found[0].score == 1.0


def test_rerank_only_touches_the_top_n(world):
    session, _, index, retriever = world
    build(world)
    plain, _ = retriever.retrieve(session, index, "付款后多久发货", Recipe())
    assert plain[0].document.source_id == "delivery"
    found, trace = retriever.retrieve(session, index, "付款后多久发货", Recipe(rerank=1))
    assert [r.chunk.id for r in found] == [r.chunk.id for r in plain]  # 只排第一块，顺序不会变
    assert len(trace.stages[-2]["hits"]) == 1


def test_expand_searches_every_rewritten_query(world):
    session, _, index, retriever = world
    build(world)
    found, trace = retriever.retrieve(session, index, "质保和链上付款", Recipe(dense=False, keyword=True, expand=True))
    assert trace.stages[0]["queries"] == ["质保和链上付款", "质保期如何计算", "USDT-BEP20 转账"]
    assert [s["name"] for s in trace.stages] == ["expand", "keyword", "keyword", "keyword", "fuse", "select"]
    assert {r.document.source_id for r in found[:2]} == {"warranty", "usdt"}


def test_eval_grades_by_document_and_by_evidence(world):
    session, _, index, retriever = world
    build(world)
    questions = [
        {"id": "q1", "kind": "kb", "q": "质保期怎么计算", "expect_docs": ["warranty"], "answer": ""},
        {"id": "q2", "kind": "kb", "q": "付款后多久发货", "expect_docs": ["missing"], "answer": ""},
        {"id": "q3", "kind": "kb", "q": "能开发票吗", "expect_docs": [], "answer": ""},
        {"id": "q4", "kind": "multi", "q": "质保期怎么计算", "expect_docs": ["warranty", "usdt"], "evidence": ["从交付时间开始", "不存在的片段"], "answer": ""},
    ]

    def respond(question: str):
        found, trace = retriever.retrieve(session, index, question, Recipe())
        return found, trace.id, ""

    evaluation = evals.start(session, index, "test", {}, len(questions))
    assert (evaluation.status, evaluation.total, evaluation.done) == ("running", 4, 0)
    result = evals.execute(session, evaluation, questions, respond, limit=1, judge=None)
    assert (result.status, result.done) == ("done", 4) and result.finished_at is not None
    assert result.scores["n"] == 3 and result.scores["hit@1"] == 0.667 and result.scores["mrr"] == 0.667
    assert result.scores["by_kind"]["multi"] == {"n": 1, "hit@1": 1.0, "hit@3": 1.0, "hit@5": 1.0, "mrr": 1.0}
    assert result.scores["evidence"] == 0.5
    graded = {r.question_id: (r.rank, r.coverage) for r in session.scalars(select(EvalResult))}
    assert graded == {"q1": (1, None), "q2": (None, None), "q3": (None, None), "q4": (1, 0.5)}


def test_eval_failure_is_recorded(world):
    session, _, index, _ = world

    def broken(_: str):
        raise RuntimeError("模型挂了")

    evaluation = evals.start(session, index, "test", {}, 1)
    with pytest.raises(RuntimeError):
        evals.execute(session, evaluation, [{"id": "q1", "kind": "kb", "q": "问", "expect_docs": [], "answer": ""}], broken, 5, None)
    assert evaluation.status == "failed" and "模型挂了" in evaluation.error


@pytest.mark.parametrize(
    ("base", "target", "correct", "expected"),
    [
        (3, 1, (None, None), "better"),
        (1, 4, (None, None), "worse"),
        (None, 5, (None, None), "better"),
        (2, None, (None, None), "worse"),
        (2, 2, (False, True), "better"),
        (2, 2, (True, False), "worse"),
        (2, 2, (True, True), "same"),
        (None, None, (None, True), "same"),
    ],
)
def test_trend(base, target, correct, expected):
    assert evals.trend(base, target, *correct) == expected


def test_refresh_can_stop_and_resume(world):
    session, kb, index, retriever = world
    ingest.sync(session, kb, DOCS)
    answers = iter([False, True])
    job = ingest.refresh(session, index, retriever.embedder, retriever.store, should_stop=lambda: next(answers))
    assert (job.status, job.progress["store"]) == ("cancelled", 1) and job.finished_at is not None
    assert len(ingest.stale(session, index)) == 2
    assert ingest.refresh(session, index, retriever.embedder, retriever.store).total == 2
    assert ingest.stale(session, index) == []


def test_eval_can_stop(world):
    session, _, index, retriever = world
    build(world)
    questions = [{"id": f"q{n}", "kind": "kb", "q": "质保", "expect_docs": ["warranty"], "answer": ""} for n in range(3)]
    answers = iter([False, True])

    def respond(question: str):
        found, trace = retriever.retrieve(session, index, question, Recipe())
        return found, trace.id, ""

    evaluation = evals.start(session, index, "test", {}, 3)
    result = evals.execute(session, evaluation, questions, respond, 5, None, lambda: next(answers))
    assert (result.status, result.done, result.scores) == ("cancelled", 1, {}) and result.finished_at is not None


def test_examples_rotate_through_kinds_and_skip_traps():
    questions = [
        {"q": "事实一", "kind": "fact", "expect_docs": ["a"]},
        {"q": "事实二", "kind": "fact", "expect_docs": ["a"]},
        {"q": "套话", "kind": "trap", "expect_docs": ["a"]},
        {"q": "没答案", "kind": "kb", "expect_docs": []},
        {"q": "换说法", "kind": "paraphrase", "expect_docs": ["b"]},
    ]
    assert evals.examples(questions, 3) == ["事实一", "换说法", "事实二"]
