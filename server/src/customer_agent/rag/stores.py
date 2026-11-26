"""向量库：每块存一个语义向量和一份关键词索引，按任一种找最相关的块。

只存向量和块的编号，原文在数据库里。关键词那一路的分词和打分交给 Qdrant 自己做（BM25）。
"""

from dataclasses import dataclass

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Document,
    Modifier,
    OptimizersConfigDiff,
    PointStruct,
    SparseVectorParams,
    VectorParams,
    WalConfigDiff,
)


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    score: float


def _bm25(text: str) -> Document:
    return Document(text=text, model="qdrant/bm25", options={"tokenizer": "multilingual"})


class QdrantStore:
    def __init__(self, url: str, namespace: str = "", api_key: str | None = None):
        """namespace 加在每个集合名前面，让测试和正式数据互不相干。"""
        self._client = QdrantClient(url=url, api_key=api_key, trust_env=False)
        self._namespace = namespace

    def ensure(self, collection: str, dim: int) -> None:
        name = self._namespace + collection
        if self._client.collection_exists(name):
            return
        self._client.create_collection(
            name,
            vectors_config={"dense": VectorParams(size=dim, distance=Distance.COSINE)},
            sparse_vectors_config={"bm25": SparseVectorParams(modifier=Modifier.IDF)},
            # 默认按处理器核数预分配分段，空集合就占 470MB 磁盘；我们的量级 1 段足够，实测降到 70MB
            optimizers_config=OptimizersConfigDiff(default_segment_number=1),
            wal_config=WalConfigDiff(wal_capacity_mb=1, wal_segments_ahead=0),
        )

    def drop(self, collection: str) -> None:
        self._client.delete_collection(self._namespace + collection)

    def add(self, collection: str, chunk_ids: list[int], vectors: np.ndarray, texts: list[str]) -> None:
        points = [
            PointStruct(id=i, vector={"dense": v.tolist(), "bm25": _bm25(t)})
            for i, v, t in zip(chunk_ids, vectors, texts, strict=True)
        ]
        self._client.upsert(self._namespace + collection, points=points, wait=True)

    def keep_only(self, collection: str, chunk_ids: set[int]) -> int:
        """删掉不在 chunk_ids 里的点，返回删了几个。用来让向量库和数据库对齐。"""
        name = self._namespace + collection
        stored, offset = [], None
        while True:
            points, offset = self._client.scroll(name, limit=1000, offset=offset, with_payload=False)
            stored += [p.id for p in points]
            if offset is None:
                break
        extra = [i for i in stored if i not in chunk_ids]
        if extra:
            self._client.delete(name, points_selector=extra, wait=True)
        return len(extra)

    def dense(self, collection: str, vector: np.ndarray, limit: int) -> list[Hit]:
        return self._query(collection, vector.tolist(), "dense", limit)

    def keyword(self, collection: str, text: str, limit: int) -> list[Hit]:
        return self._query(collection, _bm25(text), "bm25", limit)

    def _query(self, collection: str, query, using: str, limit: int) -> list[Hit]:
        points = self._client.query_points(self._namespace + collection, query=query, using=using, limit=limit).points
        return [Hit(p.id, p.score) for p in points]
