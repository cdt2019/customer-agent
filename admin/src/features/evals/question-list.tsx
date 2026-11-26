import { Link } from "@tanstack/react-router";
import { useState } from "react";

import type { CompareRow, EvalRun } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Toggle } from "@/components/ui/toggle";
import { cn } from "@/lib/utils";

import { KIND_LABEL, TREND_LABEL } from "./model";

const TREND_COLOR: Record<string, string> = { better: "text-up", worse: "text-down", same: "text-ink-3" };

const rankText = (rank: number | null | undefined) => (rank ? `第 ${rank}` : "没找到");
const verdict = (correct: boolean | null | undefined) => (correct === null || correct === undefined ? null : correct ? "合格" : "不合格");

/** 按题型的前 5 命中，点一下只看这一类。 */
function KindFilter({ base, target, kind, onKind }: { base?: EvalRun; target: EvalRun; kind: string | null; onKind: (kind: string | null) => void }) {
  const kinds = Object.entries(target.scores.by_kind);
  if (kinds.length === 0) return null;
  return (
    <div className="flex flex-none flex-wrap gap-1.5 border-b border-hair px-4 py-2">
      {kinds.map(([name, score]) => {
        const before = base?.scores.by_kind[name]?.hit5;
        return (
          <Toggle
            key={name}
            size="sm"
            pressed={kind === name}
            onPressedChange={(pressed) => onKind(pressed ? name : null)}
            className="h-7 rounded-[9px] bg-tile px-2.5 text-xs text-ink-2 data-pressed:bg-blue data-pressed:text-white"
          >
            {KIND_LABEL[name] ?? name} {before !== undefined && `${Math.round(before * 100)}% → `}
            {Math.round(score.hit5 * 100)}%
          </Toggle>
        );
      })}
    </div>
  );
}

function Detail({ row, indexId }: { row: CompareRow; indexId: number }) {
  return (
    <div className="mb-2 space-y-1 rounded-b-2xl bg-tile px-3.5 pt-1 pb-3 text-[13px] leading-relaxed text-ink-2">
      <p><b className="font-semibold text-ink">应找到：</b>{row.expect_docs.join("、") || "资料里没有"}</p>
      {row.evidence.length > 0 && <p><b className="font-semibold text-ink">原文片段：</b>{row.evidence.join(" ／ ")}</p>}
      <p><b className="font-semibold text-ink">参考答案：</b>{row.reference}</p>
      {row.base?.answer && <p><b className="font-semibold text-ink">基准的回答（{verdict(row.base.correct) ?? "未判分"}）：</b>{row.base.answer}</p>}
      {row.target?.answer && <p><b className="font-semibold text-ink">对比的回答（{verdict(row.target.correct) ?? "未判分"}）：</b>{row.target.answer}</p>}
      <Link to="/playground" search={{ index: indexId, q: row.question }} className="inline-block font-semibold text-blue hover:underline">
        在测试台打开
      </Link>
    </div>
  );
}

export function QuestionList({ rows, base, target }: { rows: CompareRow[]; base?: EvalRun; target: EvalRun }) {
  const [tab, setTab] = useState("worse");
  const [kind, setKind] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const inKind = rows.filter((row) => !kind || row.kind === kind);
  const groups: Record<string, CompareRow[]> = {
    worse: inKind.filter((row) => row.trend === "worse"),
    better: inKind.filter((row) => row.trend === "better"),
    all: inKind,
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
      <Tabs value={tab} onValueChange={(value) => setTab(String(value))} className="flex-none border-b border-hair px-5 pt-2.5">
        <TabsList variant="line" className="h-auto gap-6 p-0">
          {Object.keys(groups).map((key) => (
            <TabsTrigger key={key} value={key} className="px-0.5 pb-2.5 text-[15px] text-ink-3 data-active:font-semibold data-active:text-blue">
              {TREND_LABEL[key]} {groups[key].length}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <KindFilter base={base} target={target} kind={kind} onKind={setKind} />

      <div className="min-h-0 flex-1 overflow-auto px-3 pt-2.5 pb-3">
        {groups[tab].length === 0 && <p className="px-2 py-3 text-ink-3">这里没有题目。</p>}
        {groups[tab].map((row) => {
          const expanded = open === row.id;
          return (
            <div key={row.id}>
              <Button
                variant="ghost"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : row.id)}
                className={cn(
                  "grid h-auto w-full grid-cols-[minmax(0,1fr)_88px_150px] items-center gap-3 rounded-2xl bg-tile px-3.5 py-2.5 text-left font-normal whitespace-normal hover:bg-blue-soft active:translate-y-0 max-[1240px]:grid-cols-[minmax(0,1fr)_130px]",
                  expanded ? "rounded-b-none" : "mb-2",
                )}
              >
                <span className="truncate font-semibold text-ink">{row.question}</span>
                <span className="w-fit rounded-lg bg-chip px-2 text-xs whitespace-nowrap text-ink-2 max-[1240px]:hidden">{KIND_LABEL[row.kind] ?? row.kind}</span>
                <span className="text-right font-num font-bold whitespace-nowrap text-ink">
                  {base && (
                    <>
                      {rankText(row.base?.rank)}
                      <i className="mx-1 font-medium text-ink-3 not-italic">→</i>
                    </>
                  )}
                  <span className={TREND_COLOR[row.trend]}>{rankText(row.target?.rank)}</span>
                </span>
              </Button>
              {expanded && <Detail row={row} indexId={target.index_id} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
