import type { ChatRow } from "@/api/client";
import { when } from "@/lib/format";
import { cn } from "@/lib/utils";

function tags(row: ChatRow): { label: string; tone: string }[] {
  return [
    row.status === "staff" && { label: "客服接手中", tone: "bg-blue-soft text-blue" },
    row.status === "handoff" && { label: "转了人工", tone: "bg-up/10 text-up" },
    row.down && { label: "点了没用", tone: "bg-warn-soft text-warn" },
    row.wrong && { label: "标了答错", tone: "bg-down/10 text-down" },
  ].filter((tag) => tag !== false);
}

export function ChatList({ rows, picked, onPick, loading }: { rows: ChatRow[]; picked: string | null; onPick: (id: string) => void; loading: boolean }) {
  return (
    <section aria-label="会话列表" className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
      <div className="min-h-0 flex-1 overflow-auto p-2">
        {rows.length === 0 && <p className="px-3 py-3 text-ink-3">{loading ? "正在读取" : "这段时间没有符合条件的会话。"}</p>}
        {rows.map((row) => (
          <button
            key={row.id}
            type="button"
            onClick={() => onPick(row.id)}
            aria-current={row.id === picked}
            className={cn("mb-1 block w-full rounded-2xl px-3 py-2.5 text-left outline-none hover:bg-tile focus-visible:ring-2 focus-visible:ring-ring", row.id === picked && "bg-blue-soft hover:bg-blue-soft")}
          >
            <span className="flex items-baseline gap-2">
              <b className="min-w-0 truncate text-[13.5px] font-semibold" title={row.visitor_id}>
                {row.visitor_id}
              </b>
              <span className="shrink-0 text-xs text-ink-3">{row.turns} 轮</span>
              <small className="ml-auto shrink-0 text-xs text-ink-3">{when(row.created_at)}</small>
            </span>
            <span className="mt-0.5 mb-1 block truncate text-[13px] text-ink-2">{row.first || "（还没说话）"}</span>
            <span className="flex flex-wrap gap-1.5">
              {tags(row).map((tag) => (
                <span key={tag.label} className={cn("rounded-md px-1.5 text-[11.5px]", tag.tone)}>
                  {tag.label}
                </span>
              ))}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
