import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type ChatDetail, errorText } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ago, when } from "@/lib/format";

const AWAY_MINUTES = 2; // 聊天窗每 5 秒来拉一次，超过这么久没来就算买家离开了

/** 客服直接回复买家（docs/07）。发第一句就由客服接手，AI 不再回答；交还后 AI 接着答。
 *  「AI 起草」按对话、资料和订单起草一条填进框里，客服改完再发（docs/08）。 */
export function ReplyBox({ chat }: { chat: ChatDetail }) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["chat", chat.id] });
    queryClient.invalidateQueries({ queryKey: ["chats"] });
    queryClient.invalidateQueries({ queryKey: ["handoffs"] });
  };
  const send = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/chats/{conversation_id}/reply", { params: { path: { conversation_id: chat.id } }, body: { text: text.trim() } });
      if (error) throw error;
    },
    onSuccess: () => {
      setText("");
      refresh();
    },
  });
  const release = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/chats/{conversation_id}/release", { params: { path: { conversation_id: chat.id } } });
      if (error) throw error;
    },
    onSuccess: refresh,
  });
  const draft = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/chats/{conversation_id}/draft", { params: { path: { conversation_id: chat.id } } });
      if (error) throw error;
      return data;
    },
    onSuccess: (data) => setText(data.text),
  });
  const pending = text.includes("【待确认");
  const seen = chat.visitor_seen_at;
  // Telegram 的回复直接推到买家手机上，不用管买家在不在看（docs/10）
  const away = chat.channel !== "telegram" && (!seen || Date.now() - new Date(seen).getTime() > AWAY_MINUTES * 60_000);
  const latest = chat.handoffs.at(-1);
  const failure = send.error ?? release.error ?? draft.error;

  return (
    <div className="flex-none border-t border-hair bg-card px-4.5 py-3">
      {away && (
        <p className="mb-2 rounded-lg bg-warn-soft px-2.5 py-1.5 text-xs text-warn">
          买家{seen ? `最后一次在看是 ${ago(seen)}` : "没有打开聊天窗"}，可能看不到回复
          {latest?.ticket_no ? `，到工单 ${latest.ticket_no} 里回复更稳` : latest?.email ? `，按买家留的邮箱 ${latest.email} 回复更稳` : ""}。
        </p>
      )}
      <form
        className="flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (text.trim()) send.mutate();
        }}
      >
        <Textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && text.trim()) send.mutate();
          }}
          maxLength={4000}
          placeholder={chat.status === "staff" ? "回复买家，Ctrl+Enter 发送" : "直接回复买家，发出后由你接手，AI 不再回答"}
          aria-label="回复买家"
          className="max-h-40 min-h-[44px] flex-1 resize-none rounded-xl border-0 bg-tile text-[13.5px] shadow-none"
        />
        <div className="flex flex-col gap-1">
          <Button type="button" variant="secondary" className="h-8 rounded-lg px-3 text-xs" disabled={draft.isPending} onClick={() => draft.mutate()}>
            {draft.isPending ? "起草中…" : "AI 起草"}
          </Button>
          <Button type="submit" className="h-8 rounded-lg px-3 text-xs" disabled={!text.trim() || send.isPending}>
            发送
          </Button>
        </div>
      </form>
      {draft.data && text && (
        <p className="mt-1.5 text-xs text-ink-3">
          起草用到：{draft.data.sources.map((s) => s.title).join("、") || "没查到资料"}
          {draft.data.orders_at && `；订单信息是 ${when(draft.data.orders_at)} 查的，到店铺核对最新状态`}
          <Button variant="link" size="sm" className="ml-2 h-auto p-0 text-xs" onClick={() => navigator.clipboard.writeText(text)}>
            复制
          </Button>
        </p>
      )}
      <div className="mt-1.5 flex items-center gap-2 text-xs text-ink-3">
        {pending && <span className="font-semibold text-warn">还有【待确认】没改</span>}
        {failure ? <span className="text-down">{errorText(failure)}</span> : <span>{chat.status === "staff" ? "你在接手，AI 不回答；30 分钟不说话会自动交还" : "AI 在回答"}</span>}
        <span className="flex-1" />
        {chat.status === "staff" && (
          <Button variant="link" size="sm" className="h-auto p-0 text-xs" disabled={release.isPending} onClick={() => release.mutate()}>
            交还给 AI
          </Button>
        )}
      </div>
    </div>
  );
}
