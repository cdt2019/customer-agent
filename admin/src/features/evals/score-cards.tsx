import type { EvalRun } from "@/api/client";
import { cn } from "@/lib/utils";

import { percent } from "./model";

type Metric = { label: string; note: string; read: (run: EvalRun) => number | null | undefined; format: (value: number) => string; hero?: boolean };

const METRICS: Metric[] = [
  { label: "前 5 命中", note: "该找到的在不在", read: (run) => run.scores.retrieval?.hit5, format: percent, hero: true },
  { label: "第 1 命中", note: "第一块就是对的", read: (run) => run.scores.retrieval?.hit1, format: percent },
  { label: "MRR", note: "排得靠不靠前", read: (run) => run.scores.retrieval?.mrr, format: (value) => value.toFixed(3) },
  { label: "证据找齐", note: "交给模型的够不够", read: (run) => run.scores.evidence, format: percent },
  { label: "回答合格", note: "模型判分", read: (run) => run.scores.correct, format: percent },
];

function Delta({ before, after, percentage, hero }: { before: number; after: number; percentage: boolean; hero?: boolean }) {
  const change = after - before;
  if (Math.abs(change) < 0.0005) return <em className={cn("ml-1.5 text-xs font-semibold not-italic", hero ? "text-white/85" : "text-ink-3")}>持平</em>;
  const text = percentage ? (Math.abs(change) * 100).toFixed(1) : Math.abs(change).toFixed(3);
  return <em className={cn("ml-1.5 text-xs font-semibold whitespace-nowrap not-italic", hero ? "text-white" : change > 0 ? "text-up" : "text-down")}>{change > 0 ? "▲" : "▼"} {text}</em>;
}

export function ScoreCards({ base, target }: { base?: EvalRun; target: EvalRun }) {
  return (
    <div className="grid flex-none grid-cols-5 gap-2.5 max-[1240px]:grid-cols-3">
      {METRICS.map((metric) => {
        const after = metric.read(target);
        const before = base ? metric.read(base) : undefined;
        return (
          <div key={metric.label} className={cn("min-w-0 rounded-[18px] px-3.5 py-2.5", metric.hero ? "bg-hero text-white shadow-blue" : "bg-card shadow-card")}>
            <span className={cn("block text-xs whitespace-nowrap", metric.hero ? "text-white/85" : "text-ink-3")}>{metric.label}</span>
            <b className="font-num text-[23px] leading-tight font-bold">{after === null || after === undefined ? "—" : metric.format(after)}</b>
            {after !== null && after !== undefined && before !== null && before !== undefined && <Delta before={before} after={after} percentage={metric.label !== "MRR"} hero={metric.hero} />}
            <small className={cn("block truncate text-[11.5px]", metric.hero ? "text-white/85" : "text-ink-3")}>{metric.note}</small>
          </div>
        );
      })}
    </div>
  );
}
