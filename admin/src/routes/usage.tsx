import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { api } from "@/api/client";
import { Metric } from "@/components/shell/metric";
import { Picker } from "@/components/shell/picker";
import { SettingsForm } from "@/features/usage/settings-form";
import { UsageChart } from "@/features/usage/usage-chart";
import { tokens, yuan } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/usage")({ component: UsagePage });

const RANGES = [
  { value: "14", label: "最近 14 天" },
  { value: "30", label: "最近 30 天" },
  { value: "90", label: "最近 90 天" },
];

function UsagePage() {
  const [days, setDays] = useState(14);
  const usage = useQuery({
    queryKey: ["usage", days],
    queryFn: async () => (await api.GET("/api/usage", { params: { query: { days } } })).data,
    refetchInterval: 60_000,
  });
  const settings = useQuery({ queryKey: ["service-settings"], queryFn: async () => (await api.GET("/api/service-settings")).data });
  const data = usage.data;
  const today = data?.days.at(-1);
  const money = (value: number | undefined) => (data?.priced && value !== undefined ? yuan(value) : "—");

  return (
    <main className="flex h-full min-w-0 flex-col px-5 py-3.5 max-md:h-auto max-md:px-3">
      <div className="mx-0.5 mb-3 flex flex-none items-center gap-2 max-md:flex-wrap">
        <h1 className="mr-1.5 text-[22px] leading-tight font-bold tracking-tight whitespace-nowrap">用量和花费</h1>
        <Picker label="时间" value={String(days)} placeholder="" options={RANGES} onChange={(value) => setDays(Number(value))} />
        <span className="flex-1" />
        {data && (
          <span className={cn("rounded-xl px-3 py-1.5 text-[13px] font-semibold", data.open_now ? "bg-up/10 text-up" : "bg-down/10 text-down")}>
            ● {data.open_now ? "聊天窗在线" : "聊天窗已暂停"}
          </span>
        )}
      </div>

      <div className="mb-3 grid h-[64px] flex-none grid-cols-5 gap-3 max-md:grid-flow-col max-md:grid-cols-none max-md:auto-cols-[40%] max-md:overflow-x-auto max-md:[scrollbar-width:none]">
        <Metric hero label="今天用量 / 上限" value={data ? tokens(data.used_today) : "—"} unit={data ? `/ ${tokens(data.limit)} token` : undefined} />
        <Metric label="今天估算花费" value={money(today?.cost)} />
        <Metric label="本月估算花费" value={money(data?.cost_month)} />
        <Metric label="今天平均每条回答" value={data && data.turns_today > 0 ? tokens(Math.round(data.used_today / data.turns_today)) : "—"} unit="token" />
        <Metric
          label="今天命中缓存"
          value={today && today.input_tokens > 0 ? String(Math.round((today.cached_tokens / today.input_tokens) * 100)) : "—"}
          unit="%"
        />
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_340px] grid-rows-[minmax(0,1fr)] gap-3 max-md:grid-cols-1 max-md:grid-rows-[320px_auto]">
        {data ? <UsageChart usage={data} /> : <div className="grid place-items-center rounded-3xl bg-card text-ink-3 shadow-card">正在读取</div>}
        {settings.data && <SettingsForm state={settings.data} />}
      </div>
      {data && !data.priced && <p className="mt-2 flex-none text-[11.5px] text-ink-3">还没填单价，花费先不估算。在右边填上模型供应商官网的单价。</p>}
    </main>
  );
}
