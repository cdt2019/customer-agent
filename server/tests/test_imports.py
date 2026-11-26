import pytest

from customer_agent.rag.imports import ParseError, inspect, parse_isolated
from customer_agent.rag.parsers import plain


def test_inspect_reports_what_was_found():
    raw = "---\ntitle: 手册\n---\n\n# 售后手册\n\n## 质保\n\n质保期从交付时间开始计算，每个商品不同。\n\n| 商品 | 质保 |\n|---|---|\n| Plus | 30 天 |\n\n<!-- image -->\n"
    report = inspect(raw, ".docx")
    assert report.checks[:2] == ["标题 2 个", "表格 1 张"]
    assert report.warnings == ["有 1 张图片，图片里的内容不会进知识库"]
    assert "image" not in report.markdown and "title:" not in report.markdown


def test_scanned_pdf_is_refused():
    with pytest.raises(ParseError, match="扫描件"):
        inspect("<!-- image -->\n\n<!-- image -->\n", ".pdf")
    with pytest.raises(ParseError, match="没有解析出"):
        inspect("   \n", ".txt")


def test_flat_pdf_headings_are_flagged():
    text = "## 一\n\n这里是足够长的一段正文内容，用来通过字数检查。\n\n## 二\n\n这里也是一段正文。\n"
    assert any("层级" in w for w in inspect(text, ".pdf").warnings)
    assert not any("层级" in w for w in inspect(text, ".docx").warnings)


def test_no_heading_is_flagged():
    assert any("没有识别出标题" in w for w in inspect("只有一段正文，没有任何标题，但是字数足够通过检查。", ".txt").warnings)


def test_plain_reads_utf8_bom_and_gbk(tmp_path):
    (tmp_path / "a.txt").write_bytes("\ufeff中文".encode())
    (tmp_path / "b.txt").write_bytes("中文".encode("gbk"))
    assert plain(tmp_path / "a.txt") == "中文"
    assert plain(tmp_path / "b.txt") == "中文"


def test_parse_runs_in_a_separate_process(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text("# 标题\n\n正文\n", encoding="utf-8")
    assert parse_isolated(source, "plain") == "# 标题\n\n正文\n"
    assert not (tmp_path / "doc.md.parsed").exists()


def test_parser_crash_becomes_a_readable_error(tmp_path):
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"not a pdf")
    with pytest.raises(ParseError, match="解析器出错"):
        parse_isolated(source, "pdf_text")


def test_the_worker_is_reused_and_restarts_after_dying(tmp_path):
    """同一个子进程接着解析下一份（模型不用重新加载）；子进程没了就重新起一个。出错之后也接着用。"""
    from customer_agent.rag import imports

    source = tmp_path / "doc.md"
    source.write_text("正文\n", encoding="utf-8")
    parse_isolated(source, "plain")
    first = imports._worker.process.pid
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    with pytest.raises(ParseError):
        parse_isolated(tmp_path / "broken.pdf", "pdf_text")
    assert parse_isolated(source, "plain") == "正文\n" and imports._worker.process.pid == first
    imports._worker.process.kill()
    imports._worker.process.wait()
    assert parse_isolated(source, "plain") == "正文\n" and imports._worker.process.pid != first


def test_each_kind_of_file_has_its_parsers():
    """PDF 可以换成只取文字；别的文件只有一个解析器，指定别的会被拒。"""
    from customer_agent.rag.parsers import PARSERS, pick

    assert [p.name for p in PARSERS[".pdf"]] == ["docling", "pdf_text"] and pick(".pdf").name == "docling"
    assert pick(".md").name == "plain" and pick(".pdf", "pdf_text").name == "pdf_text"
    with pytest.raises(KeyError):
        pick(".docx", "pdf_text")


@pytest.fixture
def two_files(tmp_path, monkeypatch):
    """一个 HTML、一个 PDF，都待确认；接口用内存库。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from customer_agent import settings
    from customer_agent.api import deps, imports as imports_api
    from customer_agent.db import Base, KnowledgeBase, SourceFile

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    monkeypatch.setattr(settings, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(imports_api, "parse_in_background", lambda file_id: None)
    (tmp_path / "a.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")
    with Session() as session:
        session.add(KnowledgeBase(id=1, name="t"))
        session.add_all([
            SourceFile(id=1, kb_id=1, filename="a.html", suffix=".html", size=1, sha256="a", stored_name="a", status="pending", parser="docling"),
            SourceFile(id=2, kb_id=1, filename="b.pdf", suffix=".pdf", size=1, sha256="b", stored_name="b", status="pending", parser="docling"),
        ])
        session.commit()
    app = FastAPI()
    app.include_router(imports_api.router)

    def db():
        with Session() as session:
            yield session

    app.dependency_overrides[deps.db] = db
    return TestClient(app)


def test_original_files_are_served_inert(two_files):
    """看原文件：HTML 按纯文本给，PDF 放进沙箱，里面的脚本都拿不到后台的登录。"""
    client = two_files
    html = client.get("/api/imports/1/original")
    assert html.headers["content-type"].startswith("text/plain") and html.headers["x-content-type-options"] == "nosniff"
    pdf = client.get("/api/imports/2/original")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.headers["content-security-policy"] == "sandbox"


def test_reparse_can_switch_the_parser(two_files):
    """PDF 能换成只取文字再解析一遍，记住换了哪个；HTML 没得换。"""
    client = two_files
    assert [p["name"] for p in client.get("/api/imports/2").json()["parsers"]] == ["docling", "pdf_text"]
    assert client.post("/api/imports/2/reparse", json={"parser": "pdf_text"}).status_code == 202
    assert client.get("/api/imports/2").json()["parser"] == "pdf_text"
    assert client.post("/api/imports/1/reparse", json={"parser": "pdf_text"}).status_code == 422
