"""按配置造出那几个重的部件。每个只造一次：模型加载要几十秒，命令行和后台接口都从这里取。"""

from functools import cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from customer_agent import settings
from customer_agent.channels.telegram import Telegram
from customer_agent.connectors.base import Shop
from customer_agent.connectors.http_shop import HttpShop
from customer_agent.db import Document, IndexVersion
from customer_agent.evals import Responder
from customer_agent.llm import ChatModel
from customer_agent.rag import answer
from customer_agent.rag.embedders import Embedder
from customer_agent.rag.rerankers import Reranker
from customer_agent.rag.retrieval import Recipe, Retriever
from customer_agent.rag.stores import QdrantStore

RERANK_MODEL = "bge-reranker-v2-m3"


class MissingKey(Exception):
    """没有配置回答模型的密钥。"""

    def __str__(self) -> str:
        return "没有模型密钥：请设置环境变量 DEEPSEEK_API_KEY（或 LLM_API_KEY）"


@cache
def store() -> QdrantStore:
    return QdrantStore(settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)


@cache
def embedder(model: str) -> Embedder:
    return Embedder(settings.MODELS_DIR / model)


@cache
def reranker() -> Reranker:
    return Reranker(settings.MODELS_DIR / RERANK_MODEL)


@cache
def chat_model(model: str = settings.LLM_MODEL) -> ChatModel:
    """默认用配置里的模型；评测时可以换一个同一家的模型来比。"""
    if not settings.LLM_API_KEY:
        raise MissingKey
    return ChatModel(settings.LLM_BASE_URL, model, settings.LLM_API_KEY, settings.LLM_EXTRA_BODY)


@cache
def shop() -> Shop:
    """当前的接入方：店铺接口地址和密钥来自配置，开发时是模拟店铺。"""
    return HttpShop(settings.SHOP_URL, settings.SHOP_API_KEY)


@cache
def telegram() -> Telegram | None:
    """Telegram 机器人（docs/10）；没配令牌时为空。"""
    return Telegram(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_PROXY) if settings.TELEGRAM_BOT_TOKEN else None


def retriever_for(index: IndexVersion, recipe: Recipe) -> Retriever:
    """只加载这个配方用得到的部件。"""
    return Retriever(
        embedder(index.embed_model),
        store(),
        reranker() if recipe.rerank else None,
        chat_model() if recipe.expand else None,
    )


def responder(session: Session, index: IndexVersion, recipe: Recipe, answers: str | None) -> tuple[Responder, ChatModel | None]:
    """评测用的答题函数和判分模型。answers：None 只检索，retrieve 检索后回答，full 把整个知识库交给模型。"""
    llm = chat_model() if answers else None
    if answers == "full":
        documents = session.scalars(select(Document).where(Document.kb_id == index.kb_id).order_by(Document.source_id)).all()
        return (lambda question: ([], None, answer.from_documents(llm, question, documents).text)), llm

    retriever = retriever_for(index, recipe)

    def respond(question: str):
        found, trace = retriever.retrieve(session, index, question, recipe)
        return found, trace.id, answer.from_chunks(llm, question, found[: recipe.limit]).text if llm else ""

    return respond, llm
