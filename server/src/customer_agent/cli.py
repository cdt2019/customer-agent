"""命令行：把各块积木拼成同步、建索引、提问、评测四件事。

  agent sync  <知识库> <文件夹>
  agent index <知识库> <索引名> [--chunker heading --size 400 --overlap 40 --model bge-m3]
  agent ask   <知识库> <索引名> <问题> [检索配方] [--no-answer]
  agent eval  <知识库> <索引名> <题目文件> [检索配方] [--answers retrieve|full]

检索配方：--no-dense 关语义，--keyword 开关键词，--expand 先改写拆分问题，--rerank N 重排前 N 块，
--candidates 每路取几块，--limit 交给模型几块。
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from customer_agent import evals, kb_sources, model_files, retention, runtime, settings
from customer_agent.chat import evaluate as chat_evaluate, tools as chat_tools
from customer_agent.db import IndexVersion, KnowledgeBase, Session
from customer_agent.rag import answer, ingest
from customer_agent.rag.retrieval import Recipe


def get_index(session: DbSession, kb_name: str, index_name: str) -> IndexVersion:
    query = select(IndexVersion).join(KnowledgeBase).where(KnowledgeBase.name == kb_name, IndexVersion.name == index_name)
    return session.scalars(query).one()


def recipe_of(args: argparse.Namespace) -> Recipe:
    return Recipe(dense=args.dense, keyword=args.keyword, expand=args.expand, rerank=args.rerank, candidates=args.candidates, limit=args.limit)


def cmd_sync(session: DbSession, args: argparse.Namespace) -> None:
    kb = session.scalars(select(KnowledgeBase).where(KnowledgeBase.name == args.kb)).one_or_none()
    if kb is None:
        kb = KnowledgeBase(name=args.kb)
        session.add(kb)
        session.flush()
    kb.source = args.source if args.source == kb_sources.SHOP else Path(args.source).resolve().as_posix()
    print(ingest.sync(session, kb, kb_sources.documents(kb.source)))


def cmd_index(session: DbSession, args: argparse.Namespace) -> None:
    kb = session.scalars(select(KnowledgeBase).where(KnowledgeBase.name == args.kb)).one()
    index = session.scalars(select(IndexVersion).where(IndexVersion.kb_id == kb.id, IndexVersion.name == args.index)).one_or_none()
    if index is None:
        index = IndexVersion(kb_id=kb.id, name=args.index, chunker=args.chunker, chunk_size=args.size, overlap=args.overlap, embed_model=args.model)
        session.add(index)
        session.commit()
    job = ingest.refresh(session, index, runtime.embedder(index.embed_model), runtime.store())
    print(f"索引编号 {index.id}，{job.status}：处理 {job.total} 篇 {job.progress}")


def cmd_ask(session: DbSession, args: argparse.Namespace) -> None:
    index, recipe = get_index(session, args.kb, args.index), recipe_of(args)
    found, trace = runtime.retriever_for(index, recipe).retrieve(session, index, args.question, recipe)
    session.commit()
    for n, r in enumerate(found[: recipe.limit], 1):
        print(f"[{n}] {r.score:.3f}  {r.document.source_id}  {' › '.join(r.chunk.heading_path)}")
    steps = "，".join(f"{s['name']} {s['ms']} ms" for s in trace.stages if "ms" in s)
    print(f"检索 {trace.took_ms} ms（{steps}），记录编号 {trace.id}")
    if args.answer:
        reply = answer.from_chunks(runtime.chat_model(), args.question, found[: recipe.limit])
        print(f"\n{reply.text}\n\n读入 {reply.input_tokens} token，写出 {reply.output_tokens} token")


def cmd_eval(session: DbSession, args: argparse.Namespace) -> None:
    index, recipe = get_index(session, args.kb, args.index), recipe_of(args)
    questions = evals.load(args.questions)
    respond, llm = runtime.responder(session, index, recipe, args.answers)
    config = {"answers": args.answers} if args.answers == "full" else {**asdict(recipe), "answers": args.answers}
    evaluation = evals.start(session, index, args.questions.parent.name, config, len(questions))
    result = evals.execute(session, evaluation, questions, respond, recipe.limit, llm)
    print(f"评测 #{result.id} {json.dumps(result.config, ensure_ascii=False)}\n{json.dumps(result.scores, ensure_ascii=False)}")


def cmd_chat_eval(session: DbSession, args: argparse.Namespace) -> None:
    index = get_index(session, args.kb, args.index)
    questions = evals.load(args.questions)
    if args.only:
        questions = [q for q in questions if q["kind"] in args.only.split(",")]
    retriever = runtime.retriever_for(index, chat_tools.RECIPE)
    result = chat_evaluate.run(session, index, args.questions.parent.name, questions, retriever, runtime.shop(), runtime.chat_model(args.model), runtime.chat_model(), args.visitor_token)
    print(f"评测 #{result.id}\n{json.dumps(result.scores, ensure_ascii=False)}")


def cmd_cleanup(session: DbSession, args: argparse.Namespace) -> None:
    cleaned = retention.clean(session, args.days)
    print(f"删了 {cleaned.conversations} 个会话、{cleaned.traces} 条检索过程（早于 {args.days} 天）")


def add_recipe(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-dense", dest="dense", action="store_false", help="不用语义检索")
    parser.add_argument("--keyword", action="store_true", help="加上关键词检索")
    parser.add_argument("--expand", action="store_true", help="先让模型改写、拆分问题")
    parser.add_argument("--rerank", type=int, default=0, metavar="N", help="重排前 N 块")
    parser.add_argument("--candidates", type=int, default=20, help="每一路取多少块")
    parser.add_argument("--limit", type=int, default=5, help="交给模型多少块")


def cmd_fetch_model(_session: DbSession, args: argparse.Namespace) -> None:
    print(f"完成：{model_files.fetch(args.repo, settings.MODELS_DIR, settings.HF_ENDPOINT)}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent")
    commands = parser.add_subparsers(required=True)

    sync = commands.add_parser("sync", help="把资料同步进知识库：一个文件夹，或 shop（接入方的帮助文章）")
    sync.add_argument("kb")
    sync.add_argument("source", help="文件夹路径，或 shop")
    sync.set_defaults(run=cmd_sync)

    index = commands.add_parser("index", help="建索引，或让已有的索引跟上文档的变化")
    index.add_argument("kb")
    index.add_argument("index")
    index.add_argument("--chunker", default="heading")
    index.add_argument("--size", type=int, default=400)
    index.add_argument("--overlap", type=int, default=40)
    index.add_argument("--model", default="bge-m3")
    index.set_defaults(run=cmd_index)

    ask = commands.add_parser("ask", help="问一个问题")
    ask.add_argument("kb")
    ask.add_argument("index")
    ask.add_argument("question")
    ask.add_argument("--no-answer", dest="answer", action="store_false", help="只看检索，不生成回答")
    add_recipe(ask)
    ask.set_defaults(run=cmd_ask)

    evaluate = commands.add_parser("eval", help="跑评测题")
    evaluate.add_argument("kb")
    evaluate.add_argument("index")
    evaluate.add_argument("questions", type=Path)
    evaluate.add_argument("--answers", choices=["retrieve", "full"], help="同时生成回答并打分：retrieve 用检索到的块，full 把整个知识库交给模型")
    add_recipe(evaluate)
    evaluate.set_defaults(run=cmd_eval)

    chat_eval = commands.add_parser("chat-eval", help="走完整对话跑评测题，看该答的答、该转的转、该拒的拒")
    chat_eval.add_argument("kb")
    chat_eval.add_argument("index")
    chat_eval.add_argument("questions", type=Path)
    chat_eval.add_argument("--only", help="只跑这几类题，逗号分隔，比如 handoff,trap")
    chat_eval.add_argument("--model", default=settings.LLM_MODEL, help="答题用的模型，打分始终用配置里的模型；用来比大小模型")
    chat_eval.add_argument("--visitor-token", help="答题时的访客令牌，由接入方签发；模拟店铺用 demo-shop token member-a")
    chat_eval.set_defaults(run=cmd_chat_eval)

    cleanup = commands.add_parser("cleanup", help="删掉到期的聊天记录和检索过程。服务每天也会自己清一次")
    cleanup.add_argument("--days", type=int, default=retention.KEEP_DAYS)
    cleanup.set_defaults(run=cmd_cleanup)

    fetch = commands.add_parser("fetch-model", help="下载向量或重排模型到 MODELS_DIR，按官方 sha256 核对")
    fetch.add_argument("repo", help="比如 BAAI/bge-m3")
    fetch.set_defaults(run=cmd_fetch_model)

    args = parser.parse_args()
    try:
        with Session() as session:
            args.run(session, args)
    except (runtime.MissingKey, model_files.BadFile) as error:
        raise SystemExit(str(error)) from error
