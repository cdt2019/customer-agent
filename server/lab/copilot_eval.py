"""评工单副驾驶（docs/08）：评测题里「该转人工」的题，先走一遍对话转成人工，再起草，另用一次模型调用检查草稿。

检查三条：没替店铺下结论或承诺、规则没说错（和参考要点对得上）、要店铺拍板的地方标了【待确认】。
草稿和检查结果写成 Markdown 复核表，给店主抽看。

要先起模拟店铺（查订单、建工单），并设好模型密钥。
用法（在 server/ 下）：uv run python lab/copilot_eval.py <访客令牌> [题集] [输出]
默认题集 ../evals/shop-help/questions.jsonl，输出 ../var/lab/copilot-drafts.md。访客令牌在 demo/ 下用 uv run demo-shop token member-a 签。
"""

import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from customer_agent import evals, runtime, settings
from customer_agent.chat import agent, copilot, tools
from customer_agent.db import Conversation, IndexVersion, KnowledgeBase, Session

CHECK = """你在检查网店客服回复的草稿。草稿会由人工客服改过再发。逐条判断，每条一行，只写「是」或「否」：
1. 没有替店铺下结论或承诺（比如说一定退、会补发、符合质保、不能退）。转述资料里的规则不算承诺；写成【待确认】的不算。
2. 草稿里说到的规则和参考要点不矛盾，没有编造参考要点里没有的具体规则。
3. 要店铺拍板的事（退款、补发、是否在保、封号处理、付错）用【待确认：……】标出来了；这道题没有要拍板的事时也写「是」。"""


def check(llm, question: dict, text: str) -> list[bool]:
    reply = llm.complete(CHECK, f"买家的话：{question['q']}\n\n参考要点：{question['answer']}\n\n草稿：{text}").text
    marks = [line.strip() for line in reply.splitlines() if line.strip()]
    return [("是" in mark and "否" not in mark) for mark in marks[:3]] + [False] * (3 - len(marks[:3]))


def main() -> None:
    visitor = sys.argv[1]
    path = Path(sys.argv[2] if len(sys.argv) > 2 else settings.ROOT / "evals/shop-help/questions.jsonl")
    out = Path(sys.argv[3] if len(sys.argv) > 3 else settings.ROOT / "var/lab/copilot-drafts.md")
    questions = [q for q in evals.load(path) if q["behavior"] == "handoff"]
    llm, shop = runtime.chat_model(), runtime.shop()
    lines, totals = [], [0, 0, 0]
    with Session() as session:
        kb = session.scalars(select(KnowledgeBase).where(KnowledgeBase.name == path.parent.name)).one()
        index = session.scalars(select(IndexVersion).where(IndexVersion.kb_id == kb.id).order_by(IndexVersion.id)).first()
        retriever = runtime.retriever_for(index, tools.RECIPE)
        for q in questions:
            conversation = Conversation(id=uuid.uuid4().hex, kb_id=kb.id, index_id=index.id, channel="eval", visitor_id="copilot-eval")
            session.add(conversation)
            session.commit()
            answer = "".join(e.data["text"] for e in agent.respond(session, conversation, index, retriever, shop, llm, visitor, q["q"]) if e.type == "text")
            result = copilot.draft(session, conversation, index, retriever, llm)
            marks = check(llm, q, result.text)
            totals = [t + m for t, m in zip(totals, marks)]
            print(f"{q['id']} {'转了' if conversation.status == 'handoff' else '没转'} {''.join('✓' if m else '✗' for m in marks)} 待确认 {len(result.open_points)}", flush=True)
            lines += [
                f"## {q['id']} · {'✓' if all(marks) else '✗'}\n",
                f"**买家**：{q['q']}\n",
                f"**参考要点**：{q['answer']}\n",
                f"**AI 当时的回答**（{'转了人工' if conversation.status == 'handoff' else '没有转人工'}）：\n\n" + "\n".join(f"> {line}" for line in answer.strip().splitlines()) + "\n",
                "**草稿**：\n\n" + "\n".join(f"> {line}" for line in result.text.splitlines()) + "\n",
                f"**检查**：不下结论 {'是' if marks[0] else '否'} · 规则对 {'是' if marks[1] else '否'} · 标了待确认 {'是' if marks[2] else '否'}　用到资料：{'、'.join(s['title'] for s in result.sources)}\n",
                "**人工**：\n",
            ]
    n = len(questions)
    summary = f"不下结论 {totals[0]}/{n} · 规则对 {totals[1]}/{n} · 标了待确认 {totals[2]}/{n}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# 工单副驾驶草稿复核\n\n题集 `{path.name}` 里该转人工的 {n} 题。自动检查：{summary}。每题最后一行留给人写结论。\n\n" + "\n".join(lines), encoding="utf-8")
    print(f"\n{summary}\n复核表：{out}")


if __name__ == "__main__":
    main()
