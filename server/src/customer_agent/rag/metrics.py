"""检索的分数：只看该找到的文档排在第几，不用模型打分。"""


def first_rank(expected: list[str], retrieved: list[str]) -> int | None:
    """期望的文档里，最早出现的那篇排第几（从 1 起）。一篇都没找到返回 None。"""
    ranks = [retrieved.index(doc) + 1 for doc in expected if doc in retrieved]
    return min(ranks, default=None)


def hit_rate(ranks: list[int | None], k: int) -> float:
    """前 k 名里找到至少一篇期望文档的题占多少。"""
    return sum(r is not None and r <= k for r in ranks) / len(ranks)


def mrr(ranks: list[int | None]) -> float:
    """名次倒数的平均：都排第 1 是 1.0，排得越靠后越低，没找到算 0。"""
    return sum(1 / r for r in ranks if r) / len(ranks)
