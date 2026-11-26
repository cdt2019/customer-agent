import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type ChatDetail, type ChatMessage, errorText, type HandoffRow } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ago, tokens, when } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ReplyBox } from "./reply-box";

const CHANNELS: Record<string, string> = { web: "网页", telegram: "Telegram", eval: "评测" };

const TOOL_NAMES: Record<string, string> = {
  search_knowledge: "查资料",
  lookup_product: "查商品",
  my_orders: "查订单",
  transfer_to_human: "转人工",
};

function toolName(name: string): string {
  return TOOL_NAMES[name] ?? name;
}

/** 工具参数里最能说明这一步的那个值：查了什么、哪张订单。 */
function argumentHint(args: Record<string, unknown>): string {
  const value = args.query ?? args.order_no;
  return typeof value === "string" && value ? `「${value}」` : args["补转"] ? "（代码补转）" : "";
}

function Steps({ message }: { message: ChatMessage }) {
  return (
    <div className="mt-2 rounded-xl bg-tile px-2.5 py-1.5 text-[12.5px] text-ink-2">
      {message.steps.map((step, i) => (
        <details key={i} className="py-0.5">
          <summary className="flex cursor-pointer gap-2 marker:content-none">
            <span className="min-w-0 truncate">
              {toolName(step.name)}
              {argumentHint(step.arguments)}
            </span>
            <em className="ml-auto shrink-0 text-ink-3 not-italic">{step.ms} 毫秒 ›</em>
          </summary>
          <pre className="mt-1 max-h-60 overflow-auto rounded-lg bg-white p-2 text-[11.5px] leading-relaxed whitespace-pre-wrap text-ink-2">{step.result}</pre>
        </details>
      ))}
      {message.sources.length > 0 && <p className="pt-0.5 text-ink-3">引用：{message.sources.map((s) => `[${s.n}] ${s.title}`).join("　")}</p>}
    </div>
  );
}

function WrongBox({ conversationId, message }: { conversationId: string; message: ChatMessage }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [reason, setReason] = useState(message.wrong_reason ?? "");
  const save = useMutation({
    mutationFn: async (next: string | null) => {
      const { error } = await api.PUT("/api/chats/{conversation_id}/messages/{message_id}/wrong", {
        params: { path: { conversation_id: conversationId, message_id: message.id } },
        body: { reason: next },
      });
      if (error) throw error;
    },
    onSuccess: () => {
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["chats"] });
      queryClient.invalidateQueries({ queryKey: ["chat", conversationId] });
    },
  });

  if (editing) {
    return (
      <form
        className="mt-2 flex items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate(reason.trim());
        }}
      >
        <Input autoFocus value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} placeholder="哪里答错了，比如：答成了付款到账时间" className="h-8 text-[13px]" />
        <Button type="submit" size="sm" disabled={save.isPending}>
          保存
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>
          取消
        </Button>
        {save.isError && <span className="shrink-0 text-xs text-down">{errorText(save.error)}</span>}
      </form>
    );
  }
  if (message.wrong_reason === null) {
    return (
      <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => setEditing(true)}>
        标为答错
      </Button>
    );
  }
  return (
    <div className="mt-2 flex items-center gap-2 rounded-xl bg-down/10 px-2.5 py-1.5 text-[12.5px] text-down">
      <b className="shrink-0">答错了</b>
      <span className="min-w-0 flex-1">{message.wrong_reason || "没写原因"}</span>
      <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => setEditing(true)}>
        改原因
      </Button>
      <Button variant="link" size="sm" className="h-auto p-0 text-xs text-ink-3" onClick={() => save.mutate(null)}>
        取消标记
      </Button>
    </div>
  );
}

function Answer({ conversationId, message }: { conversationId: string; message: ChatMessage }) {
  const [open, setOpen] = useState(false);
  const wrong = message.wrong_reason !== null;
  return (
    <div className={cn("max-w-[86%] self-start rounded-[5px_16px_16px_16px] bg-white px-3.5 pt-2.5 pb-2 shadow-sm", wrong && "ring-2 ring-down/40")}>
      <p className="whitespace-pre-wrap">{message.text}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-ink-3">
        {message.steps.length > 0 && <span>{message.steps.map((step) => toolName(step.name)).join(" · ")}</span>}
        <span>
          {tokens(message.tokens)} token{message.seconds !== null && ` · ${message.seconds} 秒`}
        </span>
        {message.feedback === 0 && <span className="rounded-md bg-warn-soft px-1.5 text-warn">买家点了没用</span>}
        {message.feedback === 1 && <span className="rounded-md bg-up/10 px-1.5 text-up">买家点了有用</span>}
        <span className="flex-1" />
        {(message.steps.length > 0 || message.sources.length > 0) && (
          <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "收起过程" : "看过程"}
          </Button>
        )}
        {!wrong && <WrongBox conversationId={conversationId} message={message} />}
      </div>
      {open && <Steps message={message} />}
      {wrong && <WrongBox conversationId={conversationId} message={message} />}
    </div>
  );
}

/** 消息和转人工记录按时间排在一起。 */
function timeline(chat: ChatDetail): (ChatMessage | HandoffRow)[] {
  return [...chat.messages, ...chat.handoffs].sort((a, b) => a.created_at.localeCompare(b.created_at));
}

export function ChatView({ chat }: { chat: ChatDetail }) {
  const turns = chat.messages.filter((m) => m.role === "user").length;
  const latest = chat.handoffs.at(-1);
  return (
    <section aria-label="会话内容" className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
      <div className="flex flex-none items-center gap-2.5 border-b border-hair px-4.5 py-3.5">
        <div className="min-w-0">
          <b className="block truncate text-[15px]" title={chat.visitor_id}>
            {chat.visitor_id} · {CHANNELS[chat.channel] ?? chat.channel}
          </b>
          <small className="text-xs text-ink-3">
            {when(chat.created_at)} 开始 · {turns} 轮 · 用量 {tokens(chat.tokens)} token
          </small>
        </div>
        <span className="flex-1" />
        {chat.visitor_seen_at && <span className="shrink-0 text-xs text-ink-3">买家 {ago(chat.visitor_seen_at)}在看</span>}
        {chat.status === "staff" && <span className="shrink-0 rounded-lg bg-blue-soft px-2 py-0.5 text-xs font-semibold text-blue">客服接手中</span>}
        {latest && (
          <span className="shrink-0 rounded-lg bg-up/10 px-2 py-0.5 text-xs font-semibold text-up">
            已转人工{latest.ticket_no ? ` · 工单 ${latest.ticket_no}` : latest.email ? ` · ${latest.email}` : ""}
          </span>
        )}
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-auto bg-background px-4.5 py-3.5 text-[14px]">
        {timeline(chat).map((item) =>
          "kind" in item ? (
            <div key={`h${item.id}`} className="rounded-xl bg-up/10 px-3 py-2 text-[13px] text-up">
              <b>已转人工</b>　{item.ticket_no ? `工单 ${item.ticket_no}` : item.email ? `留了邮箱 ${item.email}` : "会员，没说是哪张订单"} · {when(item.created_at)}
              {item.status === "unnotified" && <span className="ml-2 text-down">没通知到店铺</span>}
            </div>
          ) : item.role === "user" && item.image ? (
            <a key={item.id} href={`/api/chats/images/${item.image.id}`} target="_blank" rel="noreferrer" className="max-w-[60%] self-end overflow-hidden rounded-[16px_16px_5px_16px] shadow-sm" title="买家发的图片，点开看原图">
              <img src={`/api/chats/images/${item.image.id}`} alt="买家发的图片" className="block max-h-72 w-auto" />
            </a>
          ) : item.role === "user" ? (
            <div key={item.id} className="max-w-[72%] self-end rounded-[16px_16px_5px_16px] bg-blue px-3.5 py-2 whitespace-pre-wrap text-white">
              {item.text}
            </div>
          ) : item.role === "assistant" ? (
            <Answer key={item.id} conversationId={chat.id} message={item} />
          ) : item.role === "staff" ? (
            <div key={item.id} className="max-w-[86%] self-start rounded-[5px_16px_16px_16px] bg-blue-soft px-3.5 pt-1.5 pb-2">
              <small className="block text-[11px] font-semibold text-blue">客服 · {when(item.created_at)}</small>
              <p className="whitespace-pre-wrap">{item.text}</p>
            </div>
          ) : (
            <p key={item.id} className="self-center text-xs text-ink-3">
              {item.text}
            </p>
          ),
        )}
      </div>
      <ReplyBox chat={chat} />
    </section>
  );
}
