"""量线上延迟：像买家一样经过店铺转发提问，记下几个时刻（从发出算起）：
第一次调工具、开始出字、回答完。每题一个新浏览器（新访客），不受每人每天的次数限制。

用法：python lab/latency.py <店铺地址> <题集> [题数]
在服务器上可以塞进客服服务的容器里跑（那里有题集和 httpx）：
  docker compose exec -T api python - http://demo:8100 /app/evals/shop-help/questions.jsonl 10 < ../server/lab/latency.py
"""

import json
import statistics
import sys
import time

import httpx


def one(base: str, question: str) -> dict:
    with httpx.Client(base_url=base, timeout=180, trust_env=False) as client:
        client.get("/api/chat/config")
        cid = client.post("/api/chat/conversations").json()["id"]
        marks, started, event = {}, time.perf_counter(), ""
        with client.stream("POST", f"/api/chat/conversations/{cid}/messages", json={"text": question}) as response:
            for line in response.iter_lines():
                if line.startswith("event: "):
                    event = line[7:]
                    key = {"status": "tool", "text": "text", "done": "done"}.get(event)
                    if key and key not in marks:
                        marks[key] = time.perf_counter() - started
    return marks


def main() -> None:
    base, path = sys.argv[1], sys.argv[2]
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    questions = [q["q"] for q in map(json.loads, open(path, encoding="utf-8")) if q.get("kind") == "kb"][:count]
    rows = []
    for q in questions:
        marks = one(base, q)
        rows.append(marks)
        print(f"{marks.get('tool', 0):5.1f} {marks.get('text', 0):5.1f} {marks.get('done', 0):5.1f}  {q}", flush=True)
    for key, label in (("tool", "第一次调工具"), ("text", "开始出字"), ("done", "回答完")):
        values = sorted(r[key] for r in rows if key in r)
        if values:
            print(f"{label}：中位 {statistics.median(values):.1f} 秒，最慢 {values[-1]:.1f} 秒（{len(values)} 题）")


if __name__ == "__main__":
    main()
