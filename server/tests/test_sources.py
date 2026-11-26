from customer_agent.rag.sources import clean, read_folder


def test_front_matter_and_language_suffix(tmp_path):
    (tmp_path / "faq").mkdir()
    (tmp_path / "faq/when.zh.md").write_text("---\ntitle: 多久到货: 说明\nkind: faq\nlang: zh\n---\n\n正文。\n", encoding="utf-8")
    (tmp_path / "faq/when.en.md").write_text("---\ntitle: When\nlang: en\n---\n\nBody.\n", encoding="utf-8")
    zh, en = sorted(read_folder(tmp_path), key=lambda d: d.lang, reverse=True)
    assert (zh.source_id, zh.lang, zh.title, zh.kind, zh.markdown) == ("faq/when", "zh", "多久到货: 说明", "faq", "正文。\n")
    assert (en.source_id, en.lang, en.kind) == ("faq/when", "en", "faq")


def test_plain_file_takes_title_from_first_heading(tmp_path):
    (tmp_path / "plan.md").write_text("# 路线图\r\n\r\n内容\r\n", encoding="utf-8", newline="")
    (tmp_path / "skip.png").write_bytes(b"x")
    [doc] = read_folder(tmp_path)
    assert (doc.source_id, doc.title, doc.lang) == ("plan", "路线图", "zh")
    assert "\r" not in doc.markdown


def test_clean():
    assert clean("甲  \n\n\n\n<!-- 页眉 -->乙\n") == "甲\n\n乙\n"


def test_same_name_with_different_formats_does_not_collide(tmp_path):
    (tmp_path / "手册.md").write_text("## 手册\n\n甲\n", encoding="utf-8")
    (tmp_path / "手册.txt").write_text("乙\n", encoding="utf-8")
    docs = {d.source_id: d.title for d in read_folder(tmp_path)}
    assert docs == {"手册": "手册", "手册.txt": "手册"}
