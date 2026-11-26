"""导入和解析：上传文件 → 解析成 Markdown → 人看过、改过 → 确认进知识库。"""

import hashlib
import shutil
import uuid
from datetime import datetime
from pathlib import Path, PurePath
from threading import Lock

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from customer_agent import settings
from customer_agent.api import datasets
from customer_agent.api.deps import db
from customer_agent.db import IndexVersion, KnowledgeBase, Session, SourceFile
from customer_agent.rag import imports, ingest
from customer_agent.rag.parsers import PARSERS, pick, plain
from customer_agent.rag.sources import FIRST_HEADING, SourceDoc

router = APIRouter()

MAX_BYTES = 50 * 1024**2
MIN_FREE_BYTES = 1024**3
TEXT_SUFFIXES = (".md", ".txt", ".html")

parse_slot = Lock()  # Docling 很吃内存，一次只解析一份


class ParserOut(BaseModel):
    name: str
    label: str


class FileRow(BaseModel):
    id: int
    filename: str
    suffix: str
    size: int
    status: str  # queued / parsing / pending / confirmed / failed
    parser: str  # 这次用的解析器
    parsers: list[ParserOut]  # 这种文件能换的解析器，第一个是默认
    checks: list[str]
    warnings: list[str]
    error: str
    previewable: bool
    created_at: datetime


class FileDetail(FileRow):
    markdown: str


def row_of(file: SourceFile) -> dict:
    return {
        "id": file.id,
        "filename": file.filename,
        "suffix": file.suffix,
        "size": file.size,
        "status": file.status,
        "parser": file.parser,
        "parsers": [ParserOut(name=parser.name, label=parser.label) for parser in PARSERS[file.suffix]],
        "checks": file.checks,
        "warnings": file.warnings,
        "error": file.error,
        "previewable": file.suffix != ".docx",
        "created_at": file.created_at,
    }


def get_file(session: DbSession, file_id: int) -> SourceFile:
    file = session.get(SourceFile, file_id)
    if file is None:
        raise HTTPException(404, "没有这个文件")
    return file


def stored_path(file: SourceFile) -> Path:
    return settings.UPLOADS_DIR / f"{file.stored_name}{file.suffix}"


def parse_in_background(file_id: int) -> None:
    with parse_slot, Session() as session:
        file = session.get(SourceFile, file_id)
        if file is None:  # 排队时被移除了
            return
        file.status, file.error = "parsing", ""
        session.commit()
        try:
            report = imports.inspect(imports.parse_isolated(stored_path(file), file.parser), file.suffix)
        except imports.ParseError as error:
            file.status, file.error, file.markdown, file.checks, file.warnings = "failed", str(error), "", [], []
        else:
            file.status, file.markdown, file.checks, file.warnings = "pending", report.markdown, report.checks, report.warnings
        session.commit()


@router.get("/api/knowledge-bases/{kb_id}/imports")
def list_files(kb_id: int, session: DbSession = Depends(db)) -> list[FileRow]:
    files = session.scalars(select(SourceFile).where(SourceFile.kb_id == kb_id).order_by(SourceFile.id.desc()))
    return [FileRow(**row_of(file)) for file in files]


@router.post("/api/knowledge-bases/{kb_id}/imports", status_code=202)
def upload(kb_id: int, file: UploadFile, background: BackgroundTasks, session: DbSession = Depends(db)) -> FileRow:
    if session.get(KnowledgeBase, kb_id) is None:
        raise HTTPException(404, "没有这个知识库")
    # 文件名只用来显示，存盘用随机名，不让它碰路径
    filename = PurePath((file.filename or "未命名").replace("\\", "/")).name[:200]
    suffix = PurePath(filename).suffix.lower()
    if suffix not in PARSERS:
        raise HTTPException(415, "支持 Markdown、TXT、HTML、Word（.docx）和 PDF")
    if file.size is not None and file.size > MAX_BYTES:
        raise HTTPException(413, "单个文件最大 50MB")
    settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(settings.UPLOADS_DIR).free < MIN_FREE_BYTES:
        raise HTTPException(507, "磁盘剩余不到 1GB，先腾点空间再导入")

    stored = uuid.uuid4().hex
    target = settings.UPLOADS_DIR / f"{stored}{suffix}"
    digest, size = hashlib.sha256(), 0
    try:
        with target.open("wb") as out:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "单个文件最大 50MB")
                digest.update(chunk)
                out.write(chunk)
        same = session.scalars(select(SourceFile).where(SourceFile.kb_id == kb_id, SourceFile.sha256 == digest.hexdigest())).first()
        if same:
            raise HTTPException(409, f"这份文件已经导入过（{same.filename}）")
    except HTTPException:
        target.unlink(missing_ok=True)
        raise

    row = SourceFile(kb_id=kb_id, filename=filename, suffix=suffix, size=size, sha256=digest.hexdigest(), stored_name=stored, status="queued", parser=pick(suffix).name)
    session.add(row)
    session.commit()
    background.add_task(parse_in_background, row.id)
    return FileRow(**row_of(row))


@router.get("/api/imports/{file_id}")
def detail(file_id: int, session: DbSession = Depends(db)) -> FileDetail:
    file = get_file(session, file_id)
    return FileDetail(**row_of(file), markdown=file.markdown)


@router.get("/api/imports/{file_id}/original", response_model=None)
def original(file_id: int, session: DbSession = Depends(db)) -> Response:
    """看原文件。文本类一律按纯文本给（HTML 也是，里面的脚本不会运行），PDF 内嵌显示，Word 下载。"""
    file = get_file(session, file_id)
    path = stored_path(file)
    safe = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"}  # PDF 里的脚本拿不到后台的登录
    if file.suffix in TEXT_SUFFIXES:
        return PlainTextResponse(plain(path), headers=safe)
    inline = file.suffix == ".pdf"
    return FileResponse(
        path,
        media_type="application/pdf" if inline else "application/octet-stream",
        filename=file.filename,
        content_disposition_type="inline" if inline else "attachment",
        headers=safe,
    )


class EditIn(BaseModel):
    markdown: str = Field(min_length=1, max_length=2_000_000)


@router.patch("/api/imports/{file_id}")
def edit(file_id: int, body: EditIn, session: DbSession = Depends(db)) -> FileDetail:
    file = get_file(session, file_id)
    if file.status != "pending":
        raise HTTPException(409, "只有待确认的文件能修改")
    file.markdown = body.markdown
    session.commit()
    return FileDetail(**row_of(file), markdown=file.markdown)


class ReparseIn(BaseModel):
    parser: str | None = None  # 换一个解析器；不传就用原来的


@router.post("/api/imports/{file_id}/reparse", status_code=202)
def reparse(file_id: int, body: ReparseIn, background: BackgroundTasks, session: DbSession = Depends(db)) -> None:
    """重新解析，手动改过的内容会被覆盖。"""
    file = get_file(session, file_id)
    if file.status not in ("pending", "failed"):
        raise HTTPException(409, "这个文件现在不能重新解析")
    try:
        file.parser = pick(file.suffix, body.parser or file.parser).name
    except KeyError as error:
        raise HTTPException(422, "这种文件不能用这个解析器") from error
    file.status, file.error = "queued", ""
    session.commit()
    background.add_task(parse_in_background, file.id)


@router.delete("/api/imports/{file_id}", status_code=204)
def remove(file_id: int, session: DbSession = Depends(db)) -> None:
    """移除还没确认的文件。已经进知识库的不从这里删。"""
    file = get_file(session, file_id)
    if file.status not in ("pending", "failed"):
        raise HTTPException(409, "只能移除待确认或失败的文件")
    path = stored_path(file)
    session.delete(file)
    session.commit()
    path.unlink(missing_ok=True)


class ConfirmIn(BaseModel):
    file_ids: list[int] = Field(min_length=1, max_length=200)
    index_id: int  # 确认后更新哪个索引版本


@router.post("/api/knowledge-bases/{kb_id}/imports/confirm", status_code=202)
def confirm(kb_id: int, body: ConfirmIn, background: BackgroundTasks, session: DbSession = Depends(db)) -> None:
    """把看过的文件写进知识库，并开始切块、算向量。"""
    kb, index = session.get(KnowledgeBase, kb_id), session.get(IndexVersion, body.index_id)
    if kb is None or index is None or index.kb_id != kb_id:
        raise HTTPException(404, "没有这个知识库或索引版本")
    files = session.scalars(select(SourceFile).where(SourceFile.id.in_(body.file_ids), SourceFile.kb_id == kb_id, SourceFile.status == "pending")).all()
    if len(files) != len(set(body.file_ids)):
        raise HTTPException(409, "有文件不是待确认状态，刷新后再试")
    datasets.require_idle(session)  # 先确认能开工，免得文档写进去了索引却没更新
    for file in files:
        heading = FIRST_HEADING.search(file.markdown)
        title = heading[1].strip() if heading else PurePath(file.filename).stem
        ingest.save_upload(session, kb, SourceDoc(source_id=f"upload/{file.filename}", lang="zh", title=title[:300], kind="upload", markdown=file.markdown))
        file.status = "confirmed"
    session.commit()
    datasets.start(index.id, background, session, sync=False, rebuild=False, kind="update")
