import { useState } from "react";

import type { Usage } from "@/api/client";
import { tokens, yuan } from "@/lib/format";
import { cn } from "@/lib/utils";

/** 每天用量的柱子（输入 + 输出 token），虚线是每天上限。悬停看当天的数。 */
export function UsageChart({ usage }: { usage: Usage }) {
  const [hover, setHover] = useState<number | null>(null);
  const totals = usage.days.map((d) => d.input_tokens + d.output_tokens);
  const most = Math.max(usage.limit, ...totals) * 1.1;
  const shown = hover === null ? null : usage.days[hover];
  const last = usage.days.length - 1;

  return (
    <section aria-label="每天用量" className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
      <div className="flex flex-none items-baseline gap-2 px-4.5 pt-3.5 pb-1">
        <b className="text-[15px]">每天用量</b>
        <small className="text-xs text-ink-3">输入加输出 token，虚线是每天上限</small>
        <span className="flex-1" />
        {shown && (
          <span className="text-xs text-ink-2" aria-live="polite">
            {shown.day.slice(5)}：<b className="font-num text-ink">{tokens(shown.input_tokens + shown.output_tokens)}</b> token
            {shown.input_tokens > 0 && ` · 命中缓存 ${Math.round((shown.cached_tokens / shown.input_tokens) * 100)}%`}
            {usage.priced && ` · ${yuan(shown.cost)}`}
          </span>
        )}
      </div>
      <div className="relative mx-4.5 mt-6 mb-2 min-h-[180px] flex-1">
        <div className="absolute inset-x-0 top-0 bottom-5">
          <div className="absolute inset-x-0 border-t-[1.5px] border-dashed border-down/50" style={{ bottom: `${(usage.limit / most) * 100}%` }}>
            <span className="absolute -top-[18px] right-0 text-[11px] text-down">上限 {tokens(usage.limit)}</span>
          </div>
          <div className="absolute inset-0 border-b border-hair" />
        </div>
        <div className="absolute inset-0 flex gap-[2px]">
          {usage.days.map((day, i) => (
            <div
              key={day.day}
              className="flex min-w-0 flex-1 flex-col items-center justify-end"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              <div className="relative flex w-full flex-1 items-end justify-center">
                <i
                  className={cn("block w-full max-w-[28px] rounded-t-[4px]", i === last ? "bg-blue/45" : "bg-blue", hover === i && "bg-blue-deep")}
                  style={{ height: `${(totals[i] / most) * 100}%`, minHeight: totals[i] > 0 ? 2 : 0 }}
                />
              </div>
              <small className={cn("h-5 pt-1 text-[11px] whitespace-nowrap text-ink-3", usage.days.length > 20 && i % 3 !== last % 3 && "invisible")}>
                {i === last ? "今天" : `${Number(day.day.slice(8))}日`}
              </small>
            </div>
          ))}
        </div>
      </div>
      <table className="sr-only">
        <caption>每天用量</caption>
        <tbody>
          {usage.days.map((day, i) => (
            <tr key={day.day}>
              <th>{day.day}</th>
              <td>{totals[i]} token</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
