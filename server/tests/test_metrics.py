from customer_agent.rag.metrics import first_rank, hit_rate, mrr


def test_first_rank():
    assert first_rank(["b", "z"], ["a", "b", "z"]) == 2
    assert first_rank(["x"], ["a", "b"]) is None


def test_scores():
    ranks = [1, 2, None, 6]
    assert hit_rate(ranks, 5) == 0.5
    assert mrr(ranks) == (1 + 1 / 2 + 1 / 6) / 4
