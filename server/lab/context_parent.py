"""实验：给每块加上下文说明、父子分段，各自比「按标题 400 字」好多少。只用语义检索（bge-m3），每次只换一处。

- 基线：按标题切 400 字（重叠 40），算向量用「文章标题 › 小节标题 + 正文」，交给模型前 5 块。
- 上下文说明：同样的块，模型读整篇文章，给每块写一两句「这块在讲什么、在文中哪里」，放在块前面一起算向量；交给模型的仍是原文。
- 父子分段：按标题切 800 字当父块，父块再切 200 字当子块；用子块检索，命中后交整个父块，交出去的总字数和基线差不多（2000 字）。

分数和 evals.py 一样：有原文片段的题，按「期望文档里含片段的块」排第几判命中；证据找齐 = 交给模型的文字里含了几成片段。

用法（在 server/ 下）：uv run python lab/context_parent.py [知识库] [题集]
默认 shop-help 和 ../evals/shop-help/questions.jsonl。上下文说明缓存在 var/lab/contexts.jsonl，重跑不再花钱。
"""

import hashlib
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from sqlalchemy import select

from customer_agent import runtime, settings
from customer_agent.db import Document, KnowledgeBase, Session
from customer_agent.rag.chunkers import atoms, by_heading, pack, titled

BUDGET = 2000  # 交给模型的字数，和基线前 5 块大致相当
CACHE = settings.ROOT / "var/lab/contexts.jsonl"
PROMPT = """下面先给一整篇文档，再给其中的一个片段。用一两句中文说明这个片段在整篇文档里的位置和它讲的是什么，帮助检索时找到它。只输出这一两句，不要复述片段。"""


def load(kb_name: str) -> list[Document]:
    with Session() as session:
        kb = session.scalars(select(KnowledgeBase).where(KnowledgeBase.name == kb_name)).one()
        return list(session.scalars(select(Document).where(Document.kb_id == kb.id).order_by(Document.id)))


def contexts_for(docs: list[Document], chunks: dict[str, list]) -> dict[str, str]:
    """每块的上下文说明。先看缓存；同一篇文档第一块先单独问，让整篇进模型的缓存，其余并发。"""
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    cached = {row["key"]: row["context"] for row in map(json.loads, CACHE.open(encoding="utf-8"))} if CACHE.exists() else {}
    llm = runtime.chat_model()
    spent = {"in": 0, "out": 0}

    def key(doc: Document, text: str) -> str:
        return hashlib.sha256(f"{doc.source_id}\n{text}".encode()).hexdigest()

    def ask(doc: Document, text: str) -> tuple[str, str]:
        reply = llm.complete(PROMPT, f"<文档 标题=\"{doc.title}\">\n{doc.markdown}\n</文档>\n\n<片段>\n{text}\n</片段>")
        spent["in"] += reply.input_tokens
        spent["out"] += reply.output_tokens
        return key(doc, text), reply.text.strip()

    with CACHE.open("a", encoding="utf-8") as out, ThreadPoolExecutor(8) as pool:
        for doc in docs:
            todo = [c.text for c in chunks[doc.source_id] if key(doc, c.text) not in cached]
            if not todo:
                continue
            started = time.perf_counter()
            results = [ask(doc, todo[0])] + list(pool.map(lambda t: ask(doc, t), todo[1:]))
            for k, context in results:
                cached[k] = context
                out.write(json.dumps({"key": k, "context": context}, ensure_ascii=False) + "\n")
            out.flush()
            print(f"  上下文 {doc.source_id}：{len(todo)} 块，{time.perf_counter() - started:.0f} 秒", flush=True)
    print(f"  上下文共花 输入 {spent['in']} / 输出 {spent['out']} token", flush=True)
    return {(doc.source_id, c.text): cached[key(doc, c.text)] for doc in docs for c in chunks[doc.source_id]}


def grade(question: dict, units: list[tuple[str, str]]) -> tuple[int | None, float | None]:
    """units 是按名次排好的 (文档编号, 交出去的文字)。返回 (命中排第几, 预算内证据找齐几成)。"""
    evidence = question.get("evidence")
    if evidence:
        hits = [doc in question["expect_docs"] and any(e in text for e in evidence) for doc, text in units]
    else:
        seen = list(dict.fromkeys(doc for doc, _ in units))
        hits = [doc in question["expect_docs"] for doc in seen]
    rank = hits.index(True) + 1 if True in hits else None
    given, total = [], 0
    for _, text in units:
        if total and total + len(text) > BUDGET:
            break
        given.append(text)
        total += len(text)
    joined = "\n".join(given)
    return rank, (sum(e in joined for e in evidence) / len(evidence) if evidence else None)


def run(name: str, questions: list[dict], vectors: np.ndarray, units: list[tuple[str, str]], embedder, collapse: list[int] | None = None) -> dict:
    """collapse[i] 是第 i 个检索单位交出去时归到哪一个（父子分段：子块归到父块）。"""
    by_kind, ranks, coverage = defaultdict(list), [], []
    for q in questions:
        scores = vectors @ embedder.query(q["q"])
        order = np.argsort(-scores)[:60]
        picked = list(dict.fromkeys(collapse[i] if collapse else i for i in order))[:10]
        rank, cov = grade(q, [units[i] for i in picked])
        ranks.append(rank)
        by_kind[q["kind"]].append(rank)
        if cov is not None:
            coverage.append(cov)

    def hit(rs: list, k: int) -> float:
        return sum(r is not None and r <= k for r in rs) / len(rs)

    row = {"name": name, "hit@1": hit(ranks, 1), "hit@5": hit(ranks, 5), "coverage": sum(coverage) / len(coverage), "by_kind": {k: hit(v, 5) for k, v in by_kind.items()}}
    print(f"{name:12s} 第1命中 {row['hit@1']:.1%}  前5命中 {row['hit@5']:.1%}  证据找齐 {row['coverage']:.1%}  " + "  ".join(f"{k} {v:.0%}" for k, v in sorted(row["by_kind"].items())), flush=True)
    return row


def main() -> None:
    kb_name = sys.argv[1] if len(sys.argv) > 1 else "shop-help"
    path = Path(sys.argv[2] if len(sys.argv) > 2 else settings.ROOT / "evals/shop-help/questions.jsonl")
    questions = [json.loads(line) for line in path.open(encoding="utf-8")]
    docs = load(kb_name)
    embedder = runtime.embedder("bge-m3")

    chunks = {d.source_id: by_heading(d.markdown, 400, 40) for d in docs}
    base_units = [(d.source_id, c.text) for d in docs for c in chunks[d.source_id]]
    base_embed = [titled(d.title, c.heading_path, c.text) for d in docs for c in chunks[d.source_id]]
    print(f"{len(docs)} 篇，{len(base_units)} 块，{len(questions)} 题", flush=True)
    rows = [run("基线", questions, embedder.documents(base_embed), base_units, embedder)]

    contexts = contexts_for(docs, chunks)
    with_context = [contexts[(d.source_id, c.text)] + "\n" + titled(d.title, c.heading_path, c.text) for d in docs for c in chunks[d.source_id]]
    rows.append(run("上下文说明", questions, embedder.documents(with_context), base_units, embedder))

    parents, children, collapse, child_embed = [], [], [], []
    for d in docs:
        for p in by_heading(d.markdown, 800, 0):
            parents.append((d.source_id, p.text))
            for text in pack(atoms(p.text, 200), 200, 20):
                children.append(text)
                collapse.append(len(parents) - 1)
                child_embed.append(titled(d.title, p.heading_path, text))
    print(f"父块 {len(parents)}，子块 {len(children)}", flush=True)
    child_vectors = embedder.documents(child_embed)
    rows.append(run("父子分段", questions, child_vectors, parents, embedder, collapse))

    out = settings.ROOT / "var/lab/context_parent.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"记录：{out}")


if __name__ == "__main__":
    main()
