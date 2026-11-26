import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Download, Search } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import { Metric } from "@/components/shell/metric";
import { Picker } from "@/components/shell/picker";
import { buttonVariants } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChatList } from "@/features/chats/chat-list";
import { ChatView } from "@/features/chats/chat-view";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/chats")({
  component: Chats,
  // 从转人工页点「看对话」带着会话编号过来
  validateSearch: (search: Record<string, unknown>): { id?: string } => (typeof search.id === "string" ? { id: search.id } : {}),
});

type Show = "all" | "handoff" | "down" | "wrong";
const SHOWS: { key: Show; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "handoff", label: "转了人工" },
  { key: "down", label: "点了没用" },
  { key: "wrong", label: "标了答错" },
];
const RANGES = [
  { value: "1", label: "今天" },
  { value: "7", label: "最近 7 天" },
  { value: "30", label: "最近 30 天" },
  { value: "90", label: "最近 90 天" },
];

function Chats() {
  const [days, setDays] = useState(7);
  const [show, setShow] = useState<Show>("all");
  const [typed, setTyped] = useState("");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<string | null>(Route.useSearch().id ?? null);

  const list = useQuery({
    queryKey: ["chats", days, show, q],
    queryFn: async () => (await api.GET("/api/chats", { params: { query: { days, show, q } } })).data,
    placeholderData: keepPreviousData,
  });
  const rows = list.data?.rows ?? [];
  const current = picked ?? rows[0]?.id ?? null;
  const detail = useQuery({
    queryKey: ["chat", current],
    enabled: current !== null,
    queryFn: async () => (await api.GET("/api/chats/{conversation_id}", { params: { path: { conversation_id: current! } } })).data,
    refetchInterval: 15_000, // 客服接手时买家的新话过一会儿就能看到
  });
  const counts = list.data?.counts;
  const range = RANGES.find((item) => item.value === String(days))!.label;

  return (
    <main className="flex h-full min-w-0 flex-col px-5 py-3.5 max-md:h-auto max-md:px-3">
      <div className="mx-0.5 mb-3 flex flex-none items-center gap-2 max-md:flex-wrap">
        <h1 className="mr-1.5 text-[22px] leading-tight font-bold tracking-tight whitespace-nowrap">会话记录</h1>
        <Picker label="时间" value={String(days)} placeholder="" options={RANGES} onChange={(value) => {
            setDays(Number(value));
            setPicked(null);
          }} />
        <Tabs value={show} onValueChange={(value) => {
            setShow(value as Show);
            setPicked(null);
          }}>
          <TabsList className="h-[34px] rounded-xl bg-white/70">
            {SHOWS.map(({ key, label }) => (
              <TabsTrigger key={key} value={key} className="rounded-[9px] px-3 text-[13px] data-active:bg-white data-active:text-blue">
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <span className="flex-1" />
        <form
          role="search"
          className="flex h-[34px] items-center gap-1.5 rounded-xl bg-white px-3 text-ink-3 shadow-sm"
          onSubmit={(event) => {
            event.preventDefault();
            setQ(typed.trim());
            setPicked(null);
          }}
        >
          <Search className="size-[15px]" />
          <input
            value={typed}
            onChange={(event) => {
              setTyped(event.target.value);
              if (!event.target.value) setQ("");
            }}
            placeholder="搜买家的话或工单号，回车"
            aria-label="搜索会话"
            className="w-48 bg-transparent text-[13px] text-ink outline-none"
          />
        </form>
        <a
          href="/api/chats/export/wrong.jsonl"
          download
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-[34px] rounded-xl border-0 bg-white shadow-sm")}
          title="标了答错的回答连同买家的问题，按评测题的格式下载；标准答案和该命中的资料要自己补上"
        >
          <Download />
          导出答错为评测题
        </a>
      </div>

      <div className="mb-3 grid h-[64px] flex-none grid-cols-5 gap-3 max-md:grid-flow-col max-md:grid-cols-none max-md:auto-cols-[40%] max-md:overflow-x-auto max-md:[scrollbar-width:none]">
        <Metric hero label={`${range}的会话`} value={String(counts?.conversations ?? "—")} unit="个" />
        <Metric label="买家的消息" value={String(counts?.messages ?? "—")} unit="条" />
        <Metric label="转了人工" value={String(counts?.handoffs ?? "—")} unit="次" />
        <Metric label="点了没用" value={String(counts?.down ?? "—")} unit="条" />
        <Metric label="标了答错" value={String(counts?.wrong ?? "—")} unit="条" />
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[360px_minmax(0,1fr)] grid-rows-[minmax(0,1fr)] gap-3 max-[1240px]:grid-cols-[280px_minmax(0,1fr)] max-md:grid-cols-1 max-md:grid-rows-[50vh_80vh]">
        <ChatList rows={rows} picked={current} onPick={setPicked} loading={list.isPending} />
        {detail.data ? (
          <ChatView chat={detail.data} />
        ) : (
          <div className="grid place-items-center rounded-3xl bg-card text-ink-3 shadow-card">{current ? "正在读取" : "选一个会话看看"}</div>
        )}
      </div>
      {list.data && list.data.rows.length >= 200 && <p className="mt-2 flex-none text-[11.5px] text-ink-3">只列最近的 200 个会话，缩小时间或加条件看更早的。</p>}
    </main>
  );
}
