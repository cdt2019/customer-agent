import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ChartColumn,
  Database,
  FlaskConical,
  Headset,
  ListChecks,
  LogOut,
  type LucideIcon,
  MessageCircle,
  PanelLeft,
  Plug,
  Scissors,
  Sparkles,
  Upload,
  Wallet,
} from "lucide-react";

import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type Item = { label: string; icon: LucideIcon; to: "/datasets" | "/imports" | "/chunk-lab" | "/jobs" | "/playground" | "/evals" | "/chats" | "/handoffs" | "/usage" | "/shop" };
/** 菜单项后面的条数；alert 时标红。 */
type Badge = { count: number; alert: boolean };

const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: "知识库",
    items: [
      { label: "数据集", icon: Database, to: "/datasets" },
      { label: "导入和解析", icon: Upload, to: "/imports" },
      { label: "切块实验室", icon: Scissors, to: "/chunk-lab" },
      { label: "任务", icon: ListChecks, to: "/jobs" },
    ],
  },
  {
    title: "检索与评测",
    items: [
      { label: "检索测试台", icon: FlaskConical, to: "/playground" },
      { label: "评测", icon: ChartColumn, to: "/evals" },
    ],
  },
  {
    title: "客服运营",
    items: [
      { label: "会话记录", icon: MessageCircle, to: "/chats" },
      { label: "转人工", icon: Headset, to: "/handoffs" },
    ],
  },
  {
    title: "用量与接入",
    items: [
      { label: "用量和花费", icon: Wallet, to: "/usage" },
      { label: "接入方", icon: Plug, to: "/shop" },
    ],
  },
];

const ROW = "flex h-9 items-center gap-2.5 rounded-xl px-2.5 whitespace-nowrap text-ink-2 transition-colors";

function MenuItem({ item, folded, badge }: { item: Item; folded: boolean; badge?: Badge }) {
  const Icon = item.icon;
  const tone = badge?.alert ? "bg-down text-white" : "bg-blue text-white";
  const row = (
    <Link
      to={item.to}
      className={cn(ROW, folded && "relative w-9 justify-center px-0", "outline-none hover:bg-ink/5 hover:text-ink focus-visible:ring-2 focus-visible:ring-ring")}
      activeProps={{ className: "bg-blue-soft font-semibold text-blue hover:bg-blue-soft hover:text-blue", "aria-current": "page" }}
    >
      <Icon className="size-[17px] shrink-0" strokeWidth={1.8} />
      {!folded && <span className="min-w-0 flex-1 truncate">{item.label}</span>}
      {badge && (folded ? <span className={cn("absolute top-1 right-1 size-2 rounded-full", tone)} /> : <span className={cn("rounded-full px-1.5 font-num text-[11px] leading-[18px] font-semibold", tone)}>{badge.count}</span>)}
    </Link>
  );
  if (!folded) return row;
  return (
    <Tooltip>
      <TooltipTrigger render={row} />
      <TooltipContent side="right">{badge ? `${item.label}（${badge.count} 条待处理）` : item.label}</TooltipContent>
    </Tooltip>
  );
}

async function logout() {
  await api.POST("/api/logout");
  location.href = "/login";
}

export function Sidebar({ folded, onToggle }: { folded: boolean; onToggle: () => void }) {
  const me = useQuery({ queryKey: ["me"], queryFn: async () => (await api.GET("/api/me")).data ?? null });
  const shop = useQuery({ queryKey: ["shop"], queryFn: async () => (await api.GET("/api/shop")).data ?? null, staleTime: 5 * 60_000 });
  const shopName = shop.data?.name ?? (shop.isPending ? "" : "接入方连不上");
  // 和转人工页共用 ["handoffs", …] 前缀：那边处理完一条，这里跟着刷新
  const handoffs = useQuery({ queryKey: ["handoffs", "counts"], queryFn: async () => (await api.GET("/api/handoffs/counts")).data ?? null, refetchInterval: 60_000 });
  // 待处理、没通知到店铺，加上客服接手中买家说了话还没回的
  const waiting = (handoffs.data?.open ?? 0) + (handoffs.data?.unnotified ?? 0) + (handoffs.data?.replies ?? 0);
  const badges: Partial<Record<Item["to"], Badge>> = waiting > 0 ? { "/handoffs": { count: waiting, alert: (handoffs.data?.unnotified ?? 0) > 0 } } : {};
  return (
    <nav
      aria-label="主导航"
      className={cn("relative z-10 flex h-full min-w-0 flex-col border-r border-hair bg-white/65 pt-3.5 pb-2.5 backdrop-blur-xl", folded ? "items-center px-2" : "px-2.5")}
    >
      <div className={cn("flex items-center gap-2 pb-3", folded ? "flex-col" : "pr-1 pl-1.5")}>
        <div className="bg-brand grid size-[30px] shrink-0 place-items-center rounded-[10px] text-white shadow-blue">
          <Sparkles className="size-4" />
        </div>
        {!folded && <b className="min-w-0 flex-1 truncate text-base font-bold tracking-tight">Customer Agent</b>}
        <Button variant="ghost" size="icon-sm" className="text-ink-3" onClick={onToggle} aria-expanded={!folded} aria-label={folded ? "展开菜单" : "收起菜单"}>
          <PanelLeft />
        </Button>
      </div>

      <div className={cn("mb-2 flex items-center gap-2.5 rounded-xl bg-white shadow-card", folded ? "p-1.5" : "px-2.5 py-1.5")}>
        <span className="grid size-7 shrink-0 place-items-center rounded-[9px] bg-blue-soft text-[13px] font-bold text-blue" title={shopName}>
          {shop.data?.name?.[0] ?? "·"}
        </span>
        {!folded && (
          <span className="min-w-0 flex-1 text-[11px] leading-tight text-ink-3">
            当前接入方
            <b className="block truncate text-[13.5px] font-semibold text-ink">{shopName}</b>
          </span>
        )}
      </div>

      <div className={cn("min-h-0 flex-1 overflow-y-auto", folded && "w-full")}>
        {GROUPS.map((group) => (
          <div key={group.title} className={cn(folded && "flex flex-col items-center border-t border-hair pt-1.5 first:border-0 first:pt-0", "mb-1.5")}>
            {!folded && <h6 className="mx-2 mt-3 mb-1 text-[11px] font-semibold tracking-wider text-ink-3">{group.title}</h6>}
            {group.items.map((item) => (
              <MenuItem key={item.label} item={item} folded={folded} badge={badges[item.to]} />
            ))}
          </div>
        ))}
      </div>

      <div className={cn("mt-2 flex items-center gap-2 rounded-xl bg-white text-[13px] text-ink-2 shadow-sm", folded ? "p-1" : "px-2.5 py-1.5")}>
        <span className="bg-brand grid size-[26px] shrink-0 place-items-center rounded-full text-xs font-semibold text-white">管</span>
        {!folded && <span className="min-w-0 flex-1 truncate">{me.data?.username ?? "管理员"}</span>}
        {!folded && (
          <Button variant="ghost" size="icon-sm" className="text-ink-3" onClick={logout} aria-label="退出登录" title="退出登录">
            <LogOut />
          </Button>
        )}
      </div>
    </nav>
  );
}
