"""把一次评测的结果排成人工复核表（Markdown）：判不合格的放前面，每题留一行给人写结论。

用法：python lab/review_sheet.py <评测编号> <题集> > 复核表.md
在服务器上塞进客服服务的容器里跑：
  docker compose exec -T api python - 4 /app/evals/shop-help/questions.jsonl < ../server/lab/review_sheet.py > 复核表.md
"""

import json
import sys

from sqlalchemy import select

from customer_agent.db import EvalResult, EvalRun, Session

KINDS = {"kb": "知识库", "handoff": "该转人工", "lookup": "查订单商品", "trap": "刁钻题"}


def quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in (text or "（空）").strip().splitlines())


def main() -> None:
    run_id, path = int(sys.argv[1]), sys.argv[2]
    questions = {q["id"]: q for q in map(json.loads, open(path, encoding="utf-8"))}
    with Session() as session:
        run = session.get(EvalRun, run_id)
        results = session.scalars(select(EvalResult).where(EvalResult.run_id == run_id)).all()
    results = sorted(results, key=lambda r: (r.correct is not False, questions[r.question_id]["kind"], r.question_id))
    wrong = sum(r.correct is False for r in results)
    print(f"# 评测 #{run_id} 人工复核表\n")
    print(f"题集 `{path}`，{len(results)} 题，模型判不合格 {wrong} 题。分数：`{json.dumps(run.scores, ensure_ascii=False)}`\n")
    print("怎么用：看「AI 的回答」是否说对了「参考答案」里的关键事实、该转人工的有没有转、刁钻题有没有守住。在每题最后一行写「同意」或「不同意：原因」。判不合格的排在最前面。\n")
    for r in results:
        q = questions[r.question_id]
        mark = "✗ 不合格" if r.correct is False else "✓ 合格"
        print(f"## {r.question_id} · {KINDS.get(q['kind'], q['kind'])} · 模型判 {mark}\n")
        print(f"**问**：{q['q']}\n")
        if q.get("note"):
            print(f"**出题说明**：{q['note']}\n")
        print(f"**参考答案**：{q.get('answer', '')}\n")
        print(f"**AI 的回答**：\n\n{quote(r.answer)}\n")
        print("**人工**：\n")


if __name__ == "__main__":
    main()
