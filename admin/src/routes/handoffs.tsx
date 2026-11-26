import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";

import { api, errorText, type HandoffRow } from "@/api/client";
import { Button, buttonVariants } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { when } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/handoffs")({ component: Handoffs });

type Status = "open" | "unnotified" | "done";
const TABS: { key: Status; label: string }[] = [
  { key: "open", label: "待处理" },
  { key: "unnotified", label: "没通知到" },
  { key: "done", label: "已处理" },
];

function kindOf(row: HandoffRow): { label: string; tone: string; hint: string } {
  if (row.kind === "ticket") return { label: `工单 ${row.ticket_no}`, tone: "bg-blue-soft text-blue", hint: "在店铺的工单里回复" };
  if (row.email) return { label: "邮箱记录", tone: "bg-up/10 text-up", hint: `按买家留的邮箱 ${row.email} 回复` };
  return { label: "会员记录", tone: "bg-chip text-ink-2", hint: "买家是会员，有几张订单没说是哪张，在店铺里查他的订单" };
}

function HandoffCard({ row }: { row: HandoffRow }) {
  const queryClient = useQueryClient();
  const act = useMutation({
    mutationFn: async (action: "done" | "notify") => {
      const path = { params: { path: { handoff_id: row.id } } };
      const { error } = action === "done" ? await api.POST("/api/handoffs/{handoff_id}/done", path) : await api.POST("/api/handoffs/{handoff_id}/notify", path);
      if (error) throw error;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["handoffs"] }),
  });
  const kind = kindOf(row);
  return (
    <article className="rounded-2xl bg-tile px-4 py-3">
      <div className="flex items-center gap-2.5">
        <span className={cn("shrink-0 rounded-lg px-2 py-px text-xs font-semibold", kind.tone)}>{kind.label}</span>
        <b className="min-w-0 truncate text-[13.5px] font-semibold" title={row.visitor_id}>
          {row.visitor_id}
        </b>
        <span className="flex-1" />
        <small className="shrink-0 text-xs text-ink-3">{when(row.created_at)}</small>
      </div>
      <p className="my-2 text-[13px] whitespace-pre-line text-ink-2">{row.summary}</p>
      <p className="mb-2 text-xs text-ink-3">{kind.hint}</p>
      {row.status === "unnotified" && <p className="mb-2 rounded-lg bg-down/10 px-2.5 py-1 text-xs text-down">没通知到店铺，店主可能还不知道这条。</p>}
      <div className="flex items-center gap-2">
        <Link to="/chats" search={{ id: row.conversation_id }} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "border-0 bg-white shadow-sm")}>
          去回复
        </Link>
        {row.status === "unnotified" && (
          <Button variant="outline" size="sm" className="border-0 bg-white shadow-sm" disabled={act.isPending} onClick={() => act.mutate("notify")}>
            重新通知
          </Button>
        )}
        {row.status !== "done" && (
          <Button variant="outline" size="sm" className="border-0 bg-white shadow-sm" disabled={act.isPending} onClick={() => act.mutate("done")}>
            标为已处理
          </Button>
        )}
        {act.isError && <span className="text-xs text-down">{errorText(act.error)}</span>}
      </div>
    </article>
  );
}

function Handoffs() {
  const [status, setStatus] = useState<Status>("open");
  const list = useQuery({
    queryKey: ["handoffs", status],
    queryFn: async () => (await api.GET("/api/handoffs", { params: { query: { status } } })).data,
  });
  const rows = list.data?.rows ?? [];
  return (
    <main className="flex h-full min-w-0 flex-col px-5 py-3.5 max-md:h-auto max-md:px-3">
      <div className="mx-0.5 mb-3 flex flex-none items-center gap-2 max-md:flex-wrap">
        <h1 className="mr-1.5 text-[22px] leading-tight font-bold tracking-tight whitespace-nowrap">转人工</h1>
        <Tabs value={status} onValueChange={(value) => setStatus(value as Status)}>
          <TabsList className="h-[34px] rounded-xl bg-white/70">
            {TABS.map(({ key, label }) => (
              <TabsTrigger key={key} value={key} className="rounded-[9px] px-3 text-[13px] data-active:bg-white data-active:text-blue">
                {label}
                {key !== "done" && list.data ? ` ${list.data.counts[key] ?? 0}` : ""}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      <section className="min-h-0 flex-1 overflow-auto rounded-3xl bg-card p-3 shadow-card">
        {rows.length === 0 && <p className="px-2 py-3 text-ink-3">{list.isPending ? "正在读取" : "这里没有转人工。"}</p>}
        <div className="grid grid-cols-[minmax(0,1fr)] gap-2.5">
          {rows.map((row) => (
            <HandoffCard key={row.id} row={row} />
          ))}
        </div>
      </section>
      <p className="mt-2 flex-none text-[11.5px] text-ink-3">
        有订单的转人工在店铺里建了工单，到工单里回复；没订单的会通知店铺提醒店主，按买家留的邮箱回复。在对话里直接回复以后做。
      </p>
    </main>
  );
}
