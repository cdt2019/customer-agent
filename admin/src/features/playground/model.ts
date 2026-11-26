import type { ChunkInfo, PlaygroundResult, Recipe } from "@/api/client";

/** 对话里的一问一答。result 和 error 都没有时表示还在等结果。 */
export type Turn = { id: number; question: string; recipe: Recipe; result?: PlaygroundResult; error?: string };

/** 结果列表的一种排法：最终排名，或某一步自己的排名。 */
export type View = { key: string; label: string; query?: string; order: number[]; scores: Map<number, number> };

const LABEL: Record<string, string> = { dense: "语义检索", keyword: "关键词", fuse: "融合", rerank: "重排" };
const SHORT: Record<string, string> = { dense: "语义", keyword: "关键词", fuse: "融合", rerank: "重排" };

/** 最终排名在前，后面是各步各自的排名。开了扩展问题时同一种检索会出现几次，按查询编号区分。 */
export function viewsOf(result: PlaygroundResult): View[] {
  const stages = result.stages.filter((stage) => stage.name !== "expand");
  const repeated = stages.filter((stage) => stage.name === "dense").length > 1 || stages.filter((stage) => stage.name === "keyword").length > 1;
  const seen: Record<string, number> = {};
  const steps = stages.map((stage, position): View & { short: string } => {
    seen[stage.name] = (seen[stage.name] ?? 0) + 1;
    const suffix = repeated && stage.query ? ` ${seen[stage.name]}` : "";
    return {
      key: `${stage.name}-${position}`,
      label: LABEL[stage.name] + suffix,
      short: SHORT[stage.name] + suffix,
      query: stage.query ?? undefined,
      order: stage.hits.map((hit) => hit.chunk_id),
      scores: new Map(stage.hits.map((hit) => [hit.chunk_id, hit.score])),
    };
  });
  // 最终的分数取最后一步给的；只重排了前几块时，没排到的块沿用上一步的分数
  const finalScores = new Map<number, number>();
  for (const step of steps) for (const [id, score] of step.scores) finalScores.set(id, score);
  return [{ key: "final", label: "最终排名", order: result.chunks.map((chunk) => chunk.id), scores: finalScores }, ...steps];
}

/** 一块在各步里各排第几（没出现的步不列）。 */
export function ranksOf(chunkId: number, views: View[]): { label: string; rank: number }[] {
  return views
    .slice(1)
    .map((view) => ({ label: view.label, rank: view.order.indexOf(chunkId) + 1 }))
    .filter((item) => item.rank > 0);
}

/** 重排把这块挪了几名，正数是往前挪；最后一步不是重排、或这块没参加重排时没有。 */
export function moveOf(chunkId: number, views: View[]): number | null {
  const [final, ...steps] = views;
  if (steps.length < 2 || !steps.at(-1)!.key.startsWith("rerank")) return null;
  const before = steps.at(-2)!.order.indexOf(chunkId);
  const after = steps.at(-1)!.order.indexOf(chunkId);
  return before < 0 || after < 0 ? null : before - final.order.indexOf(chunkId);
}

export function chunkMap(result: PlaygroundResult): Map<number, ChunkInfo> {
  return new Map(result.chunks.map((chunk) => [chunk.id, chunk]));
}

/** 分数的量级随步骤不同（相似度 0–1，BM25 十几，RRF 零点零几），按大小决定保留几位。 */
export function formatScore(score: number): string {
  if (score >= 10) return score.toFixed(1);
  if (score >= 0.1) return score.toFixed(3);
  return score.toFixed(4);
}
