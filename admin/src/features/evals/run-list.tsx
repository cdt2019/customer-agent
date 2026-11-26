import type { EvalRun } from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { indexLabel, percent, recipeLabel } from "./model";

function headline(run: EvalRun): string {
  if (run.status === "running") return `${run.done}/${run.total}`;
  if (run.status === "failed") return "失败";
  if (run.status === "cancelled") return "已取消";
  if (run.scores.retrieval) return percent(run.scores.retrieval.hit5);
  return run.scores.correct === null ? "—" : percent(run.scores.correct);
}

export function RunList({ runs, base, target, onPick }: { runs: EvalRun[]; base: number | null; target: number | null; onPick: (id: number) => void }) {
  return (
    <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
      <h2 className="flex-none px-4.5 pt-3.5 pb-2 text-[15px] font-bold">
        评测记录<small className="ml-1.5 text-xs font-normal text-ink-3">点一条作为基准</small>
      </h2>
      <div className="min-h-0 flex-1 overflow-auto px-2.5 pb-2.5">
        {runs.length === 0 && <p className="px-2 py-3 text-ink-3">这个知识库还没有评测记录。</p>}
        {runs.map((run) => {
          const role = run.id === target ? "对比" : run.id === base ? "基准" : "";
          const pickable = run.status === "done" && run.id !== target;
          return (
            <Button
              key={run.id}
              variant="ghost"
              disabled={!pickable && run.id !== target}
              aria-pressed={role !== ""}
              onClick={() => pickable && onPick(run.id)}
              className={cn(
                "mb-1.5 grid h-auto w-full grid-cols-[minmax(0,1fr)_auto] gap-x-2 gap-y-px rounded-2xl bg-tile px-3 py-2.5 text-left font-normal whitespace-normal ring-[1.5px] ring-transparent ring-inset hover:bg-blue-soft active:translate-y-0 disabled:opacity-100",
                run.id === target && "bg-blue-soft ring-blue",
                run.id === base && "bg-white ring-input",
              )}
            >
              <b className="truncate font-semibold text-ink">
                #{run.id} {recipeLabel(run)}
              </b>
              <span className={cn("text-right font-num text-[17px] leading-tight font-bold", run.status === "failed" ? "text-down" : run.status === "running" ? "text-blue" : "text-ink")}>
                {headline(run)}
              </span>
              <span className="truncate text-xs text-ink-3">
                {indexLabel(run)}
                {run.answers && " · 含回答"}
              </span>
              <span className={cn("text-right text-[11px] font-bold", role === "对比" ? "text-blue" : "text-ink-3")}>{run.status === "running" ? "进行中" : role}</span>
            </Button>
          );
        })}
      </div>
    </section>
  );
}
