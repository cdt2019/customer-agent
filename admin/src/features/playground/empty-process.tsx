import { Send } from "lucide-react";

import type { Recipe } from "@/api/client";
import { Metric } from "@/components/shell/metric";
import { cn } from "@/lib/utils";

/** 这个配方会走哪几步，和有结果时的标签页一一对应。 */
function stepsOf(recipe: Recipe): string[] {
  const routes = Number(recipe.dense) + Number(recipe.keyword);
  return [
    "最终排名",
    ...(recipe.dense ? ["语义检索"] : []),
    ...(recipe.keyword ? ["关键词"] : []),
    ...(routes > 1 || recipe.expand ? ["融合"] : []),
    ...(recipe.rerank > 0 ? ["重排"] : []),
  ];
}

function GhostRow({ rank, picked, steps }: { rank: number; picked: boolean; steps: string[] }) {
  return (
    <div className="mb-2 grid grid-cols-[38px_minmax(0,1fr)_56px] items-start gap-x-3.5 rounded-[18px] bg-tile px-4 py-3">
      <span className={cn("row-span-3 grid size-[38px] place-items-center rounded-[13px] font-num text-[15px] font-bold", picked ? "bg-blue-soft text-blue" : "bg-white text-ink-3 shadow-sm")}>{rank}</span>
      <span className="mt-1 h-3.5 rounded-full bg-chip" style={{ width: `${62 - rank * 5}%` }} />
      <span className="mt-1 h-3.5 rounded-full bg-chip" />
      <span className="col-span-2 mt-2.5 h-2.5 rounded-full bg-chip/70" style={{ width: `${94 - rank * 3}%` }} />
      <span className="col-span-2 col-start-2 mt-2.5 flex flex-wrap gap-1.5">
        {steps.slice(1).map((step) => (
          <span key={step} className="rounded-[9px] bg-chip/80 px-2 text-xs text-ink-3">
            {step} 第 —
          </span>
        ))}
      </span>
    </div>
  );
}

/** 还没有结果时的检索过程：版面和有结果时一样，让人知道这里会出现什么。 */
export function EmptyProcess({ recipe, waiting }: { recipe: Recipe; waiting: boolean }) {
  const steps = stepsOf(recipe);
  return (
    <>
      <div className="mb-3 grid h-[72px] flex-none grid-cols-[minmax(150px,1.3fr)_repeat(4,minmax(0,1fr))] gap-2.5 max-md:grid-flow-col max-md:grid-cols-none max-md:auto-cols-[40%] max-md:overflow-x-auto max-md:[scrollbar-width:none]">
        <div className="bg-hero flex min-w-0 items-center gap-3 overflow-hidden rounded-[18px] px-3.5 text-white shadow-blue">
          <span className="grid size-10 shrink-0 place-items-center rounded-[13px] bg-white text-blue-deep">
            <Send className="size-[19px]" />
          </span>
          <span className="min-w-0 text-xs leading-snug text-white/85">
            交给模型
            <b className="block font-num text-[17px] leading-tight font-bold whitespace-nowrap text-white">前 {recipe.limit} 块</b>
          </span>
        </div>
        <Metric label="候选" value="—" />
        <Metric label="检索" value="—" />
        <Metric label="回答" value="—" />
        <Metric label="读入 / 写出" value="—" />
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
        <div className="flex flex-none items-center gap-6 border-b border-hair px-5 pt-3">
          {steps.map((step, n) => (
            <span key={step} className={cn("border-b-2 px-0.5 pb-2.5 text-[15px] whitespace-nowrap", n === 0 ? "border-blue font-semibold text-blue" : "border-transparent text-ink-3")}>
              {step}
            </span>
          ))}
          <span className="ml-auto pb-2.5 text-[12.5px] whitespace-nowrap text-ink-3">{waiting ? "正在检索和回答" : "提问后显示每一步的结果"}</span>
        </div>
        <div aria-hidden="true" className={cn("min-h-0 flex-1 overflow-hidden px-3.5 pt-3", waiting && "animate-pulse")}>
          {Array.from({ length: recipe.limit + 2 }, (_, n) => (
            <div key={n}>
              <GhostRow rank={n + 1} picked={n < recipe.limit} steps={steps} />
              {n + 1 === recipe.limit && (
                <div className="mx-2 mt-0.5 mb-3 flex items-center gap-2.5 text-xs font-semibold whitespace-nowrap text-blue before:h-px before:flex-1 before:bg-blue/25 after:h-px after:flex-1 after:bg-blue/25">
                  以上 {recipe.limit} 块交给模型
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
