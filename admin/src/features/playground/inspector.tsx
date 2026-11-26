import { Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { KnowledgeBase, PlaygroundResult, Recipe } from "@/api/client";
import { Metric } from "@/components/shell/metric";
import { Button } from "@/components/ui/button";
import { indexDetail, Picker } from "@/components/shell/picker";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

import { EmptyProcess } from "./empty-process";
import { chunkMap, formatScore, moveOf, ranksOf, viewsOf } from "./model";

/** 重排前后名次的变化：▲ 往前、▼ 往后。 */
function Move({ by }: { by: number | null }) {
  if (by === null) return null;
  const text = by > 0 ? `▲${by}` : by < 0 ? `▼${-by}` : "持平";
  return <small className={cn("block text-xs font-semibold", by > 0 ? "text-up" : by < 0 ? "text-down" : "text-ink-3")}>{text}</small>;
}

export function Inspector({
  knowledgeBases,
  indexId,
  onIndex,
  question,
  result,
  recipe,
  waiting,
  focus,
}: {
  knowledgeBases: KnowledgeBase[];
  indexId: number | null;
  onIndex: (id: number) => void;
  question?: string;
  result?: PlaygroundResult;
  /** 还没有结果时，按当前配方画出会走的步骤 */
  recipe: Recipe;
  waiting: boolean;
  /** 要定位并高亮的块（点了回答里的出处编号）。seq 每点一次加一，同一块也能再次触发。 */
  focus: { chunkId: number; seq: number } | null;
}) {
  const kb = knowledgeBases.find((item) => item.indexes.some((index) => index.id === indexId)) ?? knowledgeBases[0];
  const [view, setView] = useState("final");
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [flash, setFlash] = useState<number | null>(null);
  const rows = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setView("final");
    setOpen(new Set());
  }, [result?.trace_id]);

  useEffect(() => {
    if (!focus) return;
    setView("final");
    setFlash(focus.chunkId);
    const timer = setTimeout(() => setFlash(null), 1400);
    requestAnimationFrame(() => rows.current?.querySelector(`[data-chunk="${focus.chunkId}"]`)?.scrollIntoView({ block: "nearest" }));
    return () => clearTimeout(timer);
  }, [focus]);

  const views = result ? viewsOf(result) : [];
  const current = views.find((item) => item.key === view) ?? views[0];
  const chunks = result ? chunkMap(result) : new Map();
  const given = result ? result.selected.reduce((sum, id) => sum + (chunks.get(id)?.text.length ?? 0), 0) : 0;
  const expand = result?.stages.find((stage) => stage.name === "expand");

  return (
    <aside aria-label="检索过程" className="flex h-full min-w-0 flex-col py-3.5 pr-4.5">
      <div className="mx-1 mb-2.5 flex items-center gap-2">
        <h2 className="text-[22px] leading-tight font-bold tracking-tight whitespace-nowrap">检索过程</h2>
        <span className="ml-1.5 min-w-0 flex-1 truncate text-[13px] text-ink-2" title={question}>
          {question}
        </span>
        <Picker
          label="知识库"
          value={kb ? String(kb.id) : null}
          placeholder="没有知识库"
          options={knowledgeBases.map((item) => ({ value: String(item.id), label: item.name, disabled: item.indexes.length === 0 }))}
          onChange={(value) => {
            const next = knowledgeBases.find((item) => String(item.id) === value);
            if (next?.indexes[0]) onIndex(next.indexes[0].id);
          }}
        />
        <Picker
          label="索引"
          ariaLabel="索引版本"
          value={indexId === null ? null : String(indexId)}
          placeholder="没有索引"
          options={(kb?.indexes ?? []).map((index) => ({ value: String(index.id), label: index.name, detail: indexDetail(index) }))}
          onChange={(value) => onIndex(Number(value))}
        />
      </div>

      {!result || !current ? (
        <EmptyProcess recipe={recipe} waiting={waiting} />
      ) : (
        <>
          <div className="mb-3 grid h-[72px] flex-none grid-cols-[minmax(150px,1.3fr)_repeat(4,minmax(0,1fr))] gap-2.5 max-md:grid-flow-col max-md:grid-cols-none max-md:auto-cols-[40%] max-md:overflow-x-auto max-md:[scrollbar-width:none]">
            <div className="bg-hero flex min-w-0 items-center gap-3 overflow-hidden rounded-[18px] px-3.5 text-white shadow-blue">
              <span className="grid size-10 shrink-0 place-items-center rounded-[13px] bg-white text-blue-deep">
                <Send className="size-[19px]" />
              </span>
              <span className="min-w-0 text-xs leading-snug text-white/85">
                交给模型
                <b className="block font-num text-[17px] leading-tight font-bold whitespace-nowrap text-white">
                  {result.selected.length} 块 · {given} 字
                </b>
              </span>
            </div>
            <Metric label="候选" value={String(result.chunks.length)} unit="块" />
            <Metric label="检索" value={String(result.retrieval_ms)} unit="ms" />
            <Metric label="回答" value={result.answer ? (result.answer.ms / 1000).toFixed(1) : "—"} unit={result.answer ? "s" : undefined} />
            <Metric label="读入 / 写出" value={result.answer ? `${result.answer.input_tokens} / ${result.answer.output_tokens}` : "—"} unit={result.answer ? "token" : undefined} />
          </div>

          {expand?.queries && (
            <p className="mx-1 mb-2.5 flex flex-wrap gap-1.5 text-[12.5px] text-ink-2">
              改写成 {expand.queries.length - 1} 条查询：
              {expand.queries.slice(1).map((item) => (
                <span key={item} className="rounded-lg bg-white/80 px-2">
                  {item}
                </span>
              ))}
            </p>
          )}

          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
            <Tabs value={current.key} onValueChange={(value) => setView(String(value))} className="flex-none border-b border-hair px-5 pt-2.5">
              <TabsList variant="line" className="h-auto gap-6 overflow-x-auto p-0">
                {views.map((item) => (
                  <TabsTrigger key={item.key} value={item.key} className="px-0.5 pb-2.5 text-[15px] text-ink-3 data-active:font-semibold data-active:text-blue">
                    {item.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            {current.query && current.query !== question && <p className="flex-none px-5 pt-2 text-[12.5px] text-ink-3">查询：{current.query}</p>}

            <div ref={rows} className="min-h-0 flex-1 overflow-auto px-3.5 pt-3 pb-3.5">
              {current.order.map((id, position) => {
                const chunk = chunks.get(id);
                if (!chunk) return null;
                const picked = result.selected.includes(id);
                const expanded = open.has(id);
                return (
                  <div key={id}>
                    <Button
                      variant="ghost"
                      data-chunk={id}
                      aria-expanded={expanded}
                      onClick={() => setOpen((before) => new Set(expanded ? [...before].filter((item) => item !== id) : [...before, id]))}
                      className={cn(
                        "mb-2 grid h-auto w-full grid-cols-[38px_minmax(0,1fr)_auto] items-start gap-x-3.5 gap-y-px rounded-[18px] bg-tile px-4 py-3 text-left font-normal whitespace-normal hover:bg-blue-soft active:translate-y-0",
                        flash === id && "bg-blue-soft",
                      )}
                    >
                      <span className={cn("row-span-2 grid size-[38px] place-items-center rounded-[13px] font-num text-[15px] font-bold", picked ? "bg-blue text-white" : "bg-white text-ink-2 shadow-sm")}>
                        {position + 1}
                      </span>
                      <span className="truncate text-[15px] font-semibold text-ink">
                        {chunk.title}
                        <em className="ml-2 text-xs font-normal text-ink-3 not-italic">{chunk.heading_path.join(" › ") || chunk.document}</em>
                      </span>
                      <span className="text-right font-num text-lg leading-snug font-bold text-ink">
                        {formatScore(current.scores.get(id) ?? 0)}
                        {current.key === "final" && <Move by={moveOf(id, views)} />}
                      </span>
                      <span className={cn("col-span-2 text-[13px] text-ink-2", expanded ? "whitespace-pre-wrap" : "truncate")}>{chunk.text}</span>
                      <span className="col-span-2 col-start-2 mt-1.5 flex flex-wrap gap-1.5">
                        {ranksOf(id, views).map((item) => (
                          <span key={item.label} className={cn("rounded-[9px] px-2 text-xs", item.label === current.label ? "bg-blue text-white" : "bg-chip text-ink-2")}>
                            {item.label} 第 {item.rank}
                          </span>
                        ))}
                        {picked && current.key !== "final" && <span className="rounded-[9px] bg-blue-soft px-2 text-xs font-semibold text-blue">交给模型</span>}
                      </span>
                    </Button>
                    {current.key === "final" && position + 1 === result.selected.length && position + 1 < current.order.length && (
                      <div className="mx-2 mt-0.5 mb-3 flex items-center gap-2.5 text-xs font-semibold whitespace-nowrap text-blue before:h-px before:flex-1 before:bg-blue/25 after:h-px after:flex-1 after:bg-blue/25">
                        以上 {result.selected.length} 块交给模型
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </aside>
  );
}
