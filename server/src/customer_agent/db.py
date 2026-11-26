"""数据表。向量在 Qdrant 里，这里存原件和记录；Qdrant 的内容随时能从这里重建。"""

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from customer_agent import settings

engine = create_engine(settings.DATABASE_URL)
Session = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}  # 时间都带时区，不管服务器和数据库在哪个时区


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    source: Mapped[str | None] = mapped_column(String(500))  # 上次从哪同步的：shop（接入方的帮助文章）或文件夹路径


class Document(Base):
    """一篇资料的原件。同一篇的不同语言是不同的行。"""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("kb_id", "source_id", "lang"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    source_id: Mapped[str] = mapped_column(String(300))
    lang: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(50))
    origin: Mapped[str] = mapped_column(String(20), default="folder", server_default="folder")  # folder 来自同步的文件夹；upload 来自导入
    markdown: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))


class SourceFile(Base):
    """上传的原文件和它的解析结果。人确认之后才写进 documents。"""

    __tablename__ = "source_files"
    __table_args__ = (UniqueConstraint("kb_id", "sha256"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(200))  # 只用来显示
    suffix: Mapped[str] = mapped_column(String(10))
    size: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    stored_name: Mapped[str] = mapped_column(String(32))  # 磁盘上的随机文件名
    status: Mapped[str] = mapped_column(String(20))  # queued / parsing / pending / confirmed / failed
    parser: Mapped[str] = mapped_column(String(20))  # 用哪个解析器，见 rag/parsers.py
    markdown: Mapped[str] = mapped_column(Text, default="")
    checks: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IndexVersion(Base):
    """一组切块和向量设置。一个知识库可以有多个，各自对应 Qdrant 里的一个集合。"""

    __tablename__ = "index_versions"
    __table_args__ = (UniqueConstraint("kb_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    chunker: Mapped[str] = mapped_column(String(30))
    chunk_size: Mapped[int]
    overlap: Mapped[int]
    embed_model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    @property
    def collection(self) -> str:
        return f"index_{self.id}"


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    index_id: Mapped[int] = mapped_column(ForeignKey("index_versions.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    doc_hash: Mapped[str] = mapped_column(String(64))  # 切这一块时文档的内容指纹，用来判断要不要重切
    seq: Mapped[int]
    heading_path: Mapped[list[str]] = mapped_column(JSON)
    text: Mapped[str] = mapped_column(Text)


class IngestJob(Base):
    """一次建索引或更新索引。progress 记每一步做完了多少篇。"""

    __tablename__ = "ingest_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    index_id: Mapped[int] = mapped_column(ForeignKey("index_versions.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20), default="update", server_default="update")  # update / sync / rebuild / build
    status: Mapped[str] = mapped_column(String(20), default="running")  # running / done / failed / cancelled
    total: Mapped[int] = mapped_column(default=0)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    embedded_chunks: Mapped[int] = mapped_column(default=0, server_default="0")
    embed_ms: Mapped[int] = mapped_column(default=0, server_default="0")  # 只算向量模型的耗时
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]


class RetrievalTrace(Base):
    """一次检索的全过程，检索测试台和评测页看的就是它。"""

    __tablename__ = "retrieval_traces"
    id: Mapped[int] = mapped_column(primary_key=True)
    index_id: Mapped[int] = mapped_column(ForeignKey("index_versions.id", ondelete="CASCADE"))
    query: Mapped[str] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSON)
    stages: Mapped[list] = mapped_column(JSON)
    took_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    index_id: Mapped[int] = mapped_column(ForeignKey("index_versions.id", ondelete="CASCADE"))
    question_set: Mapped[str] = mapped_column(String(300))
    config: Mapped[dict] = mapped_column(JSON)
    scores: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), server_default="done")  # running / done / failed / cancelled
    total: Mapped[int] = mapped_column(server_default="0")
    done: Mapped[int] = mapped_column(default=0, server_default="0")
    error: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]


class EvalResult(Base):
    __tablename__ = "eval_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(50))
    rank: Mapped[int | None]  # 第一块命中的排第几；没找到或这题不看检索时为空
    coverage: Mapped[float | None]  # 交给模型的块里找齐了几成证据；题目没给证据时为空
    trace_id: Mapped[int | None] = mapped_column(ForeignKey("retrieval_traces.id", ondelete="SET NULL"))
    answer: Mapped[str] = mapped_column(Text, default="")
    correct: Mapped[bool | None]  # 回答是否合格；没生成回答时为空


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # 随机编号，猜不到
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    index_id: Mapped[int] = mapped_column(ForeignKey("index_versions.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(20), default="web")
    visitor_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open AI 答 / handoff 转了人工、AI 照答 / staff 客服接手、AI 不答（docs/07）
    visitor_seen_at: Mapped[datetime | None]  # 买家的聊天窗最近一次来拉消息
    staff_at: Mapped[datetime | None]  # 客服最近一次说话，太久没说就自动交还给 AI
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user / assistant / staff / system
    text: Mapped[str] = mapped_column(Text)  # 存之前已打码
    sources: Mapped[list] = mapped_column(JSON, default=list)
    feedback: Mapped[int | None]  # 1 有用，0 没用
    wrong_reason: Mapped[str | None] = mapped_column(Text)  # 后台标了答错时写的原因；没标为空
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cached_tokens: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class Image(Base):
    """买家在聊天里发的一张图（docs/09）。文件在 IMAGES_DIR，已重新编码、去掉元数据；随会话一起删。"""

    __tablename__ = "images"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    stored_name: Mapped[str] = mapped_column(String(50))  # 磁盘上的随机文件名，带后缀
    width: Mapped[int]
    height: Mapped[int]
    size: Mapped[int]  # 字节
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ToolCallLog(Base):
    __tablename__ = "tool_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    arguments: Mapped[dict] = mapped_column(JSON)
    result: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[int | None] = mapped_column(ForeignKey("retrieval_traces.id", ondelete="SET NULL"))
    ms: Mapped[int]


class Handoff(Base):
    __tablename__ = "handoffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # ticket 建了工单；record 留了邮箱
    ticket_no: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open 待处理 / unnotified 没通知到接入方 / done 已处理
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class UsageDaily(Base):
    __tablename__ = "usage_daily"
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    calls: Mapped[int] = mapped_column(default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cached_tokens: Mapped[int] = mapped_column(BigInteger, default=0)


class ServiceSettings(Base):
    """总开关、限额和单价，只有一行（id=1）。默认值见产品需求 §5.8 和 docs/05 §20。"""

    __tablename__ = "service_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    per_visitor_day: Mapped[int] = mapped_column(default=30)
    per_conversation: Mapped[int] = mapped_column(default=20)
    max_message_chars: Mapped[int] = mapped_column(default=500, server_default="500")  # 买家一条消息最多几个字
    daily_token_limit: Mapped[int] = mapped_column(BigInteger, default=5_000_000)
    price_input: Mapped[float] = mapped_column(default=0)  # 每百万 token 的价格（元），0 表示没填
    price_cached_input: Mapped[float] = mapped_column(default=0)
    price_output: Mapped[float] = mapped_column(default=0)
    cap_notified_on: Mapped[date | None]  # 哪天已经提醒过店主「到上限了」
    suggestions: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    telegram_offset: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")  # Telegram 的消息处理到哪了，重启后不重复回  # 聊天窗的常见问题，按语言：{"zh": [...], "en": [...]}

