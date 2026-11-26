import type { CompareRow, EvalRun } from "@/api/client";

export const KIND_LABEL: Record<string, string> = {
  fact: "事实",
  paraphrase: "换说法",
  exact: "精确标识符",
  multi: "多处合答",
  kb: "照资料",
  lookup: "要查的",
  handoff: "转人工",
  trap: "刁钻题",
};

export type Trend = CompareRow["trend"];
export const TREND_LABEL: Record<string, string> = { worse: "变差", better: "变好", all: "全部" };

/** 一次评测的配方，写成人看的短语。 */
export function recipeLabel(run: EvalRun): string {
  if (run.answers === "chat") return "完整对话";
  if (!run.recipe) return "整库放进提示词";
  const parts = [run.recipe.dense && "语义", run.recipe.keyword && "关键词", run.recipe.expand && "改写", run.recipe.rerank > 0 && `重排 ${run.recipe.rerank}`];
  return parts.filter(Boolean).join(" + ");
}

export function indexLabel(run: EvalRun): string {
  const chunker = run.chunker === "heading" ? "按标题" : "定长";
  return `${run.index_name} · ${chunker} ${run.chunk_size} 字 · ${run.embed_model}`;
}

export const percent = (value: number) => `${(value * 100).toFixed(1)}%`;

/** 默认对比：最新一次完成的，和它前一次完成的。 */
export function defaultPair(runs: EvalRun[]): { base: number | null; target: number | null } {
  const done = runs.filter((run) => run.status === "done");
  return { target: done[0]?.id ?? null, base: done[1]?.id ?? null };
}
