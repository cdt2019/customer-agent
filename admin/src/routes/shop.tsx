import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { api } from "@/api/client";
import { SuggestionsForm } from "@/features/shop/suggestions-form";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/shop")({ component: ShopPage });

function ShopPage() {
  const shop = useQuery({ queryKey: ["shop"], queryFn: async () => (await api.GET("/api/shop")).data ?? null });
  const system = useQuery({ queryKey: ["system"], queryFn: async () => (await api.GET("/api/system")).data ?? null });
  const widget = useQuery({ queryKey: ["widget-settings"], queryFn: async () => (await api.GET("/api/widget-settings")).data ?? null });
  const info = shop.data;
  const reachable = info?.name != null;
  const state = shop.isPending ? "正在连接" : !reachable ? "连不上接入方" : info.online ? "在客服时间" : "不在客服时间";

  return (
    <main className="flex h-full min-w-0 flex-col overflow-auto px-5 py-3.5 max-md:h-auto max-md:px-3">
      <div className="mx-0.5 mb-3 flex flex-none items-center gap-2">
        <h1 className="text-[22px] leading-tight font-bold tracking-tight whitespace-nowrap">接入方</h1>
        <span className="ml-1 text-[13px] text-ink-2">店铺信息从接入方的店铺接口读；聊天窗的设置在这里改</span>
      </div>
      <div className="grid max-w-[920px] gap-3">
        <section className="flex items-center gap-3 rounded-3xl bg-card px-5 py-4 shadow-card">
          <span className="grid size-10 shrink-0 place-items-center rounded-[13px] bg-blue-soft text-lg font-bold text-blue">{info?.name?.[0] ?? "·"}</span>
          <span className="min-w-0 flex-1">
            <b className="block truncate text-[16px]">{info?.name ?? "—"}</b>
            <small className="text-xs text-ink-3">名字、联系方式、客服时间都在接入方那边改</small>
          </span>
          <span className={cn("shrink-0 rounded-xl px-3 py-1.5 text-[13px] font-semibold", !reachable ? "bg-down/10 text-down" : info.online ? "bg-up/10 text-up" : "bg-chip text-ink-2")}>● {state}</span>
        </section>
        {widget.data && <SuggestionsForm state={widget.data} />}
        {system.data && (
          <section className="rounded-3xl bg-card px-5 py-4 shadow-card">
            <h2 className="text-[15px] font-bold">运行信息</h2>
            <p className="mb-2 text-xs text-ink-3">只读。这些在服务器的环境变量里，改了要重启服务，见部署说明。</p>
            <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-6 gap-y-1.5 text-[13.5px]">
              <dt className="text-ink-3">回答用的模型</dt>
              <dd className="font-num">{system.data.llm_model}</dd>
              <dt className="text-ink-3">业务时区</dt>
              <dd>
                {system.data.timezone}
                <small className="ml-2 text-xs text-ink-3">每天的限额和统计从这里的零点算</small>
              </dd>
              <dt className="text-ink-3">Telegram 机器人</dt>
              <dd className={system.data.telegram ? "text-up" : "text-ink-2"}>
                {system.data.telegram ?? "没配置"}
                {system.data.telegram === "" && "已配置，还没连上 Telegram"}
                <small className="ml-2 text-xs text-ink-3">令牌和用哪个索引在服务器的环境变量里（docs/10）</small>
              </dd>
              <dt className="text-ink-3">服务密钥</dt>
              <dd className={system.data.service_key_set ? "text-up" : "text-down"}>
                {system.data.service_key_set ? "已配置" : "没有配置，接入方调不通对话接口"}
                <small className="ml-2 text-xs text-ink-3">接入方后端调对话接口时用，密钥本身不在页面上显示</small>
              </dd>
            </dl>
          </section>
        )}
      </div>
    </main>
  );
}
