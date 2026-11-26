"""对话循环的测试：模型是写好台词的假模型，店铺用模拟数据。"""

import json
import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from customer_agent.chat import agent
from customer_agent.chat.guard import claims_handoff, offers_handoff, redact
from customer_agent.connectors.base import Notice, OrderSummary, ShopInfo
from customer_agent.db import Base, ChatMessage, Conversation, Document, Handoff, IndexVersion, KnowledgeBase, ToolCallLog, UsageDaily
from customer_agent.llm import Finished, Reply, ToolRequest



class FakeShop:
    """接入方的替身：两位会员，订单里没有卡密。访客令牌就是身份名。"""

    ORDERS = {
        "member-a": [OrderSummary("EX1001", "ChatGPT Plus 月卡", "已交付", True, True, date(2026, 12, 21), None), OrderSummary("EX1002", "ChatGPT Go 月卡", "待付款", False, False, None, None)],
        "member-b": [OrderSummary("EX2001", "工具会员 月卡", "处理中", True, False, None, "T20260001")],
    }

    def __init__(self, online=True, notify_fails=False):
        self.tickets, self.notified = [], []
        self.online, self.notify_fails = online, notify_fails

    def info(self):
        return ShopInfo("店", "Telegram：@support", 12, self.online, "下班了，明早回复。")

    def notify(self, notice: Notice):
        if self.notify_fails:
            raise ConnectionError("店铺连不上")
        self.notified.append(notice)

    def products(self, query):
        return []

    def orders(self, visitor):
        return self.ORDERS.get(visitor or "", [])

    def create_ticket(self, visitor, order_no, summary):
        if order_no not in {o.order_no for o in self.orders(visitor)}:
            raise PermissionError(order_no)
        self.tickets.append({"order_no": order_no, "summary": summary})
        return f"T{len(self.tickets):04d}"


class ScriptedModel:
    """按顺序说台词。每句台词是文字，或 (工具名, 参数)。"""

    def __init__(self, *script, verdict="否"):
        self.script, self.calls, self.verdict = list(script), [], verdict

    def complete(self, system, user):
        return Reply(self.verdict, 5, 1)

    def stream(self, messages, tools, tool_choice=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "tool_choice": tool_choice})
        line = self.script.pop(0)
        if isinstance(line, str):
            yield line
            yield Finished(line, [], 100, 10, 40)
        else:
            yield Finished("", [ToolRequest(uuid.uuid4().hex, line[0], json.dumps(line[1], ensure_ascii=False))], 100, 10, 40)


class FakeRetriever:
    def retrieve(self, session, index, query, recipe):
        from customer_agent.db import Chunk, RetrievalTrace
        from customer_agent.rag.retrieval import Retrieved

        doc = session.scalars(select(Document)).first()
        chunk = session.scalars(select(Chunk)).first()
        if chunk is None:
            chunk = Chunk(index_id=index.id, document_id=doc.id, doc_hash="h", seq=0, heading_path=["到货"], text="付款后一分钟内发货。")
            session.add(chunk)
        trace = RetrievalTrace(index_id=index.id, query=query, config={}, stages=[], took_ms=1)
        session.add(trace)
        session.flush()
        return [Retrieved(chunk, doc, 0.9)], trace


@pytest.fixture
def world():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        kb = KnowledgeBase(name="test")
        session.add(kb)
        session.flush()
        index = IndexVersion(kb_id=kb.id, name="v1", chunker="heading", chunk_size=400, overlap=40, embed_model="fake")
        doc = Document(kb_id=kb.id, source_id="faq/when", lang="zh", title="多久到货", kind="faq", markdown="付款后一分钟内发货。", content_hash="h")
        session.add_all([index, doc])
        session.flush()
        conversation = Conversation(id=uuid.uuid4().hex, kb_id=kb.id, index_id=index.id, channel="web", visitor_id="v")
        session.add(conversation)
        session.commit()
        yield session, conversation, index, FakeShop()


def talk(world, llm, text, visitor="member-a"):
    session, conversation, index, shop = world
    return list(agent.respond(session, conversation, index, FakeRetriever(), shop, llm, visitor, text))


def done(events):
    return next(e for e in events if e.type == "done").data


@pytest.mark.parametrize("raw", ["我的密码是 Qwe!2345", "账号 a@b.com 密码 Qwe!2345", "验证码：123456", "卡密是ABCD-1234", '{"accessToken":"eyJhbGciOi.abc.def"}'])
def test_secrets_are_masked(raw):
    masked = redact(raw)
    assert "••••••" in masked
    for secret in ("Qwe!2345", "123456", "ABCD-1234", "eyJhbGciOi"):
        assert secret not in masked


@pytest.mark.parametrize("plain", ["把我上一单的卡密再发一遍", "忘记密码怎么办", "卡密在哪看", "验证码收不到"])
def test_ordinary_questions_are_not_masked(plain):
    assert redact(plain) == plain


def test_claims_handoff():
    assert claims_handoff("已为你转人工，请稍等") and claims_handoff("已经转给客服了")
    assert not claims_handoff("可以帮你转人工，要转吗？")


def test_answer_with_citation_and_usage(world):
    session, conversation, *_ = world
    llm = ScriptedModel(("search_knowledge", {"query": "多久到货"}), "付款后一分钟内发货[1]。")
    events = talk(world, llm, "多久到货")
    assert [e.type for e in events] == ["user", "status", "text", "done"]
    assert events[1].data == {"tool": "search_knowledge"}
    assert done(events)["sources"] == [{"n": 1, "title": "多久到货", "document": "faq/when"}]
    assert done(events)["input_tokens"] == 200
    assert session.scalars(select(ToolCallLog)).one().trace_id is not None
    usage = session.get(UsageDaily, (conversation.kb_id, date.today()))
    assert (usage.calls, usage.input_tokens, usage.cached_tokens) == (2, 200, 80)


def test_secret_never_reaches_the_model_or_the_database(world):
    session, *_ = world
    llm = ScriptedModel("这些信息不用发给我。")
    talk(world, llm, "我的密码是 Qwe!2345")
    assert "Qwe!2345" not in json.dumps(llm.calls[0]["messages"], ensure_ascii=False)
    assert "Qwe!2345" not in session.scalars(select(ChatMessage).where(ChatMessage.role == "user")).one().text


def test_orders_are_scoped_to_the_visitor_and_have_no_card_secret(world):
    llm = ScriptedModel(("my_orders", {}), "你的订单已交付。")
    talk(world, llm, "我的订单呢", visitor="member-a")
    result = llm.calls[1]["messages"][-1]["content"]
    assert "EX1001" in result and "EX2001" not in result
    assert "2026-12-21 到期" in result or "已过期" in result


def test_warranty_days_are_counted_by_code():
    """质保还剩几天由代码算好，模型照着说。"""
    from customer_agent.chat.tools import warranty

    today = date(2026, 11, 25)
    assert warranty(date(2026, 12, 21), today) == "还剩 26 天，2026-12-21 到期"
    assert warranty(today, today) == "今天到期（2026-11-25）"
    assert warranty(date(2026, 10, 2), today) == "已过期，2026-10-02 到期"
    assert warranty(None, today).startswith("没有质保期")


def test_a_visitor_cannot_transfer_on_someone_elses_order(world):
    session, _, _, shop = world
    llm = ScriptedModel(("transfer_to_human", {"summary": "要退款", "order_no": "EX2001"}), "请留一个邮箱。")
    talk(world, llm, "EX2001 退款", visitor="guest")
    assert shop.tickets == [] and session.scalars(select(Handoff)).first() is None
    assert "邮箱" in llm.calls[1]["messages"][-1]["content"]


def test_transfer_creates_a_ticket_once(world):
    session, conversation, _, shop = world
    llm = ScriptedModel(("transfer_to_human", {"summary": "号被封了", "order_no": "EX1001"}), "已转人工。")
    events = talk(world, llm, "号被封了要退款")
    assert next(e for e in events if e.type == "handoff").data["kind"] == "ticket"
    assert conversation.status == "handoff" and len(shop.tickets) == 1
    again = ScriptedModel(("transfer_to_human", {"summary": "还是要退"}), "已经转过了。")
    talk(world, again, "快点")
    assert len(shop.tickets) == 1 and len(session.scalars(select(Handoff)).all()) == 1


def test_guest_transfer_needs_an_email(world):
    session, conversation, *_ = world
    llm = ScriptedModel(("transfer_to_human", {"summary": "售前咨询", "email": "不是邮箱"}), "请留个邮箱。")
    talk(world, llm, "转人工", visitor=None)
    assert conversation.status == "open"
    llm = ScriptedModel(("transfer_to_human", {"summary": "售前咨询", "email": "a@example.com"}), "已转人工。")
    talk(world, llm, "a@example.com", visitor=None)
    handoff = session.scalars(select(Handoff)).one()
    assert (handoff.kind, handoff.email, conversation.status) == ("record", "a@example.com", "handoff")


def test_claiming_a_transfer_without_the_tool_does_it_for_real(world):
    _, conversation, _, shop = world
    talk(world, ScriptedModel("已为你转人工，请等待。", "已转人工，工单已建。"), "我要退款", visitor="member-b")
    assert conversation.status == "handoff" and shop.tickets[0]["order_no"] == "EX2001"


def test_claiming_a_transfer_with_no_way_to_do_it_asks_for_an_email(world):
    _, conversation, *_ = world
    llm = ScriptedModel("已为你转人工。", "还需要一个邮箱才能转，方便留一下吗？")
    events = talk(world, llm, "我要退款", visitor=None)
    assert conversation.status == "open"
    assert "邮箱" in llm.calls[1]["messages"][-1]["content"]
    assert [e.type for e in events].count("clear") == 1


def test_tool_rounds_are_capped(world):
    llm = ScriptedModel(*[("search_knowledge", {"query": "x"})] * 3, "只能根据这些回答。")
    talk(world, llm, "问题")
    assert len(llm.calls) == 4 and llm.calls[-1]["tools"] is None


def test_bad_tool_arguments_do_not_break_the_turn(world):
    session, *_ = world
    class Broken(ScriptedModel):
        def stream(self, messages, tools, tool_choice=None):
            if len(self.calls) == 0:
                self.calls.append({"messages": messages, "tools": tools})
                yield Finished("", [ToolRequest("1", "search_knowledge", "{不是 JSON")], 1, 1, 0)
            else:
                yield from super().stream(messages, tools)
    events = talk(world, Broken("没有查到。"), "问题")
    assert events[-1].type == "done"


def test_whitespace_survives_and_preamble_is_withdrawn(world):
    session, *_ = world

    class Chatty(ScriptedModel):
        def stream(self, messages, tools, tool_choice=None):
            self.calls.append({"messages": messages, "tools": tools})
            if len(self.calls) == 1:
                yield "我先查一下"
                yield Finished("我先查一下", [ToolRequest("1", "my_orders", "{}")], 1, 1, 0)
            else:
                yield from ("第一行", "\n", "第二行")
                yield Finished("第一行\n第二行", [], 1, 1, 0)

    events = talk(world, Chatty(), "订单呢")
    assert [e.type for e in events] == ["user", "text", "clear", "status", "text", "text", "text", "done"]
    assert session.get(ChatMessage, done(events)["message_id"]).text == "第一行\n第二行"


def test_talking_about_a_session_token_is_not_a_secret():
    assert redact("do you store my session token anywhere?") == "do you store my session token anywhere?"


def test_member_with_several_orders_can_transfer_without_an_email(world):
    session, conversation, *_ = world
    talk(world, ScriptedModel(("transfer_to_human", {"summary": "要人工"}), "已转人工。"), "找人工", visitor="member-a")
    assert conversation.status == "handoff" and session.scalars(select(Handoff)).one().kind == "record"
    assert "没有工单号" in session.scalars(select(ToolCallLog)).one().result


@pytest.mark.parametrize("plain", ["我的密码是多少", "验证码：收不到", "不需要账号密码：只要贴登录资料"])
def test_sentences_about_secrets_are_not_masked(plain):
    assert redact(plain) == plain


@pytest.mark.parametrize("text", ["要我现在帮你转人工吗？", "要不要我帮你转人工核实？", "需要转给客服确认吗？", "你告诉我订单号，或者我直接帮你转过去？", "我帮你转一下？", "Would you like me to pass this to a human?"])
def test_offers_handoff(text):
    assert offers_handoff(text)


@pytest.mark.parametrize("text", ["已转人工，请等待。", "这件事由客服确认。"])
def test_not_an_offer(text):
    assert not offers_handoff(text)


def test_offer_on_a_real_problem_is_transferred_by_code(world):
    session, conversation, _, shop = world
    llm = ScriptedModel("能不能补发要客服确认，要我帮你转人工吗？", "已转人工，工单已建，客服会核实。", verdict="是")
    events = talk(world, llm, "号掉了给我补一个", visitor="member-b")
    assert conversation.status == "handoff" and len(shop.tickets) == 1
    assert llm.calls[-1]["tools"] is None
    assert session.get(ChatMessage, done(events)["message_id"]).text == "已转人工，工单已建，客服会核实。"
    assert done(events)["input_tokens"] == 205


def test_offer_on_a_plain_question_is_left_to_the_buyer(world):
    _, conversation, _, shop = world
    events = talk(world, ScriptedModel("资料里没有写，要转人工问问吗？"), "客服几点上班", visitor="member-b")
    assert conversation.status == "open" and shop.tickets == []
    assert "clear" not in [e.type for e in events]


def test_a_sent_secret_forces_a_search_first(world):
    llm = ScriptedModel(("search_knowledge", {"query": "怎么开通"}), "开通不需要密码，请自己到兑换页操作[1]。")
    talk(world, llm, "我的密码是 Qwe!2345 帮我开通")
    assert llm.calls[0]["tool_choice"]["function"]["name"] == "search_knowledge"
    assert llm.calls[1]["tool_choice"] is None
    assert any(m["role"] == "system" and "已被系统遮住" in m["content"] for m in llm.calls[0]["messages"])


def test_an_ordinary_question_is_not_forced(world):
    llm = ScriptedModel("你好。")
    talk(world, llm, "忘记密码怎么办")
    assert llm.calls[0]["tool_choice"] is None


def test_two_unanswered_replies_in_a_row_go_to_a_human(world):
    _, conversation, _, shop = world
    talk(world, ScriptedModel("资料里没有查到这个。"), "你们几点下班", visitor="member-b")
    assert conversation.status == "open"
    llm = ScriptedModel("这个也没有查到。", "已转人工，客服会回复你。")
    events = talk(world, llm, "那周末呢", visitor="member-b")
    assert conversation.status == "handoff" and len(shop.tickets) == 1
    assert "clear" in [e.type for e in events]


def test_an_unanswered_reply_after_a_thumbs_down_goes_to_a_human(world):
    session, conversation, _, shop = world
    first = done(talk(world, ScriptedModel("可以在订单页申请。"), "怎么退", visitor="member-b"))["message_id"]
    session.get(ChatMessage, first).feedback = 0
    session.commit()
    talk(world, ScriptedModel("没有查到更多。", "已转人工。"), "还是不懂", visitor="member-b")
    assert conversation.status == "handoff"


def test_the_buyers_words_come_back_masked(world):
    events = talk(world, ScriptedModel("不用发给我。"), "我的密码是 Qwe!2345")
    assert events[0].type == "user" and "Qwe!2345" not in events[0].data["text"]


def test_a_record_handoff_tells_the_shop_owner(world):
    session, conversation, _, shop = world
    talk(world, ScriptedModel(("transfer_to_human", {"summary": "售前", "email": "a@example.com"}), "已转人工。"), "转人工", visitor=None)
    assert [(n.kind, n.conversation_id, n.email) for n in shop.notified] == [("handoff", conversation.id, "a@example.com")]
    assert session.scalars(select(Handoff)).one().status == "open"


def test_a_ticket_handoff_needs_no_extra_notice(world):
    _, _, _, shop = world
    talk(world, ScriptedModel(("transfer_to_human", {"summary": "退款"}), "已转人工。"), "退款", visitor="member-b")
    assert shop.tickets and not shop.notified


def test_a_failed_notice_is_marked_not_lost(world):
    session, conversation, _, shop = world
    shop.notify_fails = True
    talk(world, ScriptedModel(("transfer_to_human", {"summary": "售前", "email": "a@example.com"}), "已转人工。"), "转人工", visitor=None)
    assert conversation.status == "handoff"
    assert session.scalars(select(Handoff)).one().status == "unnotified"


def test_after_hours_the_model_is_told_to_say_so(world):
    _, _, _, shop = world
    shop.online = False
    llm = ScriptedModel(("transfer_to_human", {"summary": "退款"}), "已转人工，下班了明早回复。")
    talk(world, llm, "退款", visitor="member-b")
    assert "下班了，明早回复。" in llm.calls[1]["messages"][-1]["content"]



def test_ai_sees_what_staff_said_after_hand_back(world):
    """交还给 AI 之后，客服说过的话也在模型看到的历史里。"""
    session, conversation, *_ = world
    session.add(ChatMessage(conversation_id=conversation.id, role="staff", text="已经给你补发了"))
    session.commit()
    llm = ScriptedModel("好的。")
    talk(world, llm, "收到了吗")
    assert {"role": "assistant", "content": "（人工客服）已经给你补发了"} in llm.calls[0]["messages"]


def test_citations_without_a_source_this_turn_are_dropped(world):
    """照着历史抄来的 [编号]，这一轮没查到对应资料：去掉，并让前端换成去掉后的文字。"""
    session, *_ = world
    llm = ScriptedModel("在订单页复制代码 [1]。兑换前确认地区 [3]。")
    events = talk(world, llm, "礼品卡怎么兑换")
    assert [e.type for e in events][-3:] == ["clear", "text", "done"]
    assert events[-2].data["text"] == "在订单页复制代码。兑换前确认地区。"
    assert done(events)["sources"] == []
