from customer_agent.rag.chunkers import CHUNKERS, by_heading, fixed, overlaps, sections

DOC = """# 质保规则

开头的话。

## 质保范围

质保期从交付时间开始计算。每个商品的质保天数写在商品页。

| 商品 | 质保 |
|---|---|
| Plus 月卡 | 30 天 |
| Go 月卡 | 30 天 |

```
# 这不是标题
```

### 例外

礼品卡未使用可换。

## 申请流程

在订单页点「申请售后」。
"""


def test_sections_track_heading_trail():
    paths = [path for path, _ in sections(DOC)]
    assert paths == [("质保规则",), ("质保规则", "质保范围"), ("质保规则", "质保范围", "例外"), ("质保规则", "申请流程")]


def test_code_fence_is_not_a_heading():
    body = dict(sections(DOC))[("质保规则", "质保范围")]
    assert "# 这不是标题" in body


def test_small_sections_stay_whole():
    chunks = by_heading(DOC, 400, 0)
    assert len(chunks) == 4
    assert chunks[3].text == "在订单页点「申请售后」。"


def test_table_is_not_split_and_size_is_respected():
    chunks = by_heading(DOC, 60, 0)
    table = [c for c in chunks if "Plus 月卡" in c.text]
    assert len(table) == 1 and "Go 月卡" in table[0].text and "|---|" in table[0].text
    assert all(len(c.text) <= 60 for c in chunks)


def test_overlap_repeats_the_tail_of_the_previous_chunk():
    text = "## 段\n\n" + "".join(f"第{i}句话在这里。" for i in range(20))
    plain = by_heading(text, 50, 0)
    lapped = by_heading(text, 50, 10)
    assert "".join(c.text for c in plain) == text.split("\n\n")[1]
    assert lapped[1].text.startswith(lapped[0].text[-10:])


def test_oversized_piece_is_hard_split():
    chunks = by_heading("## 长\n\n" + "字" * 250, 100, 0)
    assert [len(c.text) for c in chunks] == [100, 100, 50]


def test_fixed_windows_cover_the_text():
    chunks = fixed("甲" * 250, 100, 20)
    assert [len(c.text) for c in chunks] == [100, 100, 90]
    assert all(c.heading_path == () for c in chunks)


def test_registry():
    assert set(CHUNKERS) == {"heading", "fixed"}


def test_repeated_punctuation_is_not_lost():
    text = "真的吗？！可以！！好的"
    assert by_heading(f"## 段\n\n{text}\n", 100, 0)[0].text == text


def test_overlaps_counts_the_shared_prefix():
    text = "## 段\n\n" + "".join(f"第{i}句话在这里。" for i in range(20))
    plain = by_heading(text, 50, 0)
    assert set(overlaps(text, [c.text for c in plain])) == {0}
    lapped = by_heading(text, 50, 10)
    assert overlaps(text, [c.text for c in lapped])[0] == 0
    assert set(overlaps(text, [c.text for c in lapped])[1:]) == {10}
