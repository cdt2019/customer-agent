"""量一个向量模型或重排模型在本机的速度和显存，结果追加到 var/bench.jsonl。

用法（在 server/ 下）：
  uv run python lab/bench_models.py embed  BAAI/bge-m3 cuda fp16
  uv run python lab/bench_models.py rerank BAAI/bge-reranker-v2-m3 cpu fp32
"""

import json
import sys
import time
from pathlib import Path

import torch
from sentence_transformers import CrossEncoder, SentenceTransformer

ROOT = Path(__file__).parents[2]
QUERY = "Plus 月卡付款后多久能收到？"
DTYPES = {"fp32": torch.float32, "fp16": torch.float16}


def passages(limit: int) -> list[str]:
    """真实的帮助文章，按空行切成段，凑成 300 字左右的块。"""
    blocks, buf = [], ""
    for path in sorted((ROOT / "demo/data/posts").rglob("*.zh.md")):
        for para in path.read_text(encoding="utf-8").split("\n\n"):
            buf += para.strip() + "\n"
            if len(buf) >= 300:
                blocks.append(buf)
                buf = ""
    return blocks[:limit]


def timed(fn, repeat: int) -> float:
    """跑 repeat 次取中位数，单位毫秒。"""
    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        times.append((time.perf_counter() - start) * 1000)
    return sorted(times)[len(times) // 2]


def bench_embed(name: str, device: str, dtype: torch.dtype) -> dict:
    model = SentenceTransformer(name, device=device, model_kwargs={"torch_dtype": dtype})
    docs = passages(64)
    model.encode([QUERY])  # 预热
    query_ms = timed(lambda: model.encode([QUERY]), 9)
    batch_ms = timed(lambda: model.encode(docs, batch_size=8), 3)
    return {
        "dim": model.get_embedding_dimension(),
        "query_ms": round(query_ms, 1),
        "chunks_per_s": round(len(docs) / batch_ms * 1000, 1),
        "chunks": len(docs),
    }


def bench_rerank(name: str, device: str, dtype: torch.dtype) -> dict:
    model = CrossEncoder(name, device=device, model_kwargs={"torch_dtype": dtype})
    docs = passages(20)
    model.predict([(QUERY, docs[0])])  # 预热
    result = {}
    for n in (5, 10, 20):
        pairs = [(QUERY, d) for d in docs[:n]]
        result[f"rerank{n}_ms"] = round(timed(lambda: model.predict(pairs, batch_size=4), 3), 1)
    return result


if __name__ == "__main__":
    kind, name, device, dtype = sys.argv[1:5]
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    load_start = time.perf_counter()
    result = {"embed": bench_embed, "rerank": bench_rerank}[kind](name, device, DTYPES[dtype])
    record = {
        "kind": kind,
        "model": name,
        "device": torch.cuda.get_device_name(0) if device == "cuda" else f"cpu x{torch.get_num_threads()}",
        "dtype": dtype,
        **result,
        "total_s": round(time.perf_counter() - load_start, 1),
        "vram_peak_mb": round(torch.cuda.max_memory_allocated() / 2**20) if device == "cuda" else None,
    }
    line = json.dumps(record, ensure_ascii=False)
    print(line)
    with (ROOT / "var/bench.jsonl").open("a", encoding="utf-8") as f:
        f.write(line + "\n")
