import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { api } from "@/api/client";
import { Picker } from "@/components/shell/picker";
import { defaultPair, indexLabel, recipeLabel } from "@/features/evals/model";
import { NewRunDialog } from "@/features/evals/new-run-dialog";
import { QuestionList } from "@/features/evals/question-list";
import { RunList } from "@/features/evals/run-list";
import { ScoreCards } from "@/features/evals/score-cards";

export const Route = createFileRoute("/evals")({ component: Evals });

function Evals() {
  const queryClient = useQueryClient();
  const knowledgeBases = useQuery({
    queryKey: ["knowledge-bases"],
    queryFn: async () => (await api.GET("/api/knowledge-bases")).data ?? [],
  });
  const withQuestions = (knowledgeBases.data ?? []).filter((kb) => kb.questions > 0);
  const [kbId, setKbId] = useState<number | null>(null);
  // 默认看练习文档：检索调优是在它上面做的
  const kb = withQuestions.find((item) => item.id === kbId) ?? withQuestions[0];

  const runs = useQuery({
    queryKey: ["eval-runs", kb?.id],
    enabled: kb !== undefined,
    queryFn: async () => (await api.GET("/api/evals/runs", { params: { query: { kb_id: kb!.id } } })).data ?? [],
    refetchInterval: (query) => (query.state.data?.some((run) => run.status === "running") ? 1500 : false),
  });
  const list = runs.data ?? [];
  const running = list.some((run) => run.status === "running");

  // 手动选的基准和对比；没选时用默认的最新两次
  const [picked, setPicked] = useState<{ base: number | null; target: number | null } | null>(null);
  const fallback = defaultPair(list);
  const targetId = picked?.target ?? fallback.target;
  const baseId = picked ? picked.base : fallback.base;
  const target = list.find((run) => run.id === targetId);
  const base = list.find((run) => run.id === baseId);

  // 评测一结束，让新的那次成为对比对象，之前的成为基准
  useEffect(() => {
    if (!running) setPicked(null);
  }, [running]);

  const compare = useQuery({
    queryKey: ["eval-compare", baseId, targetId],
    enabled: targetId !== null && target?.status === "done",
    queryFn: async () => (await api.GET("/api/evals/compare", { params: { query: { base: baseId ?? targetId!, target: targetId! } } })).data ?? [],
  });

  return (
    <main className="flex h-full min-w-0 flex-col px-5 py-3.5 max-md:h-auto max-md:px-3">
      <div className="mx-0.5 mb-3 flex flex-none items-center gap-2 max-md:flex-wrap">
        <h1 className="mr-1.5 text-[22px] leading-tight font-bold tracking-tight whitespace-nowrap">评测</h1>
        <Picker
          label="知识库"
          value={kb ? String(kb.id) : null}
          placeholder="没有题集"
          options={withQuestions.map((item) => ({ value: String(item.id), label: `${item.name} · ${item.questions} 题` }))}
          onChange={(value) => {
            setKbId(Number(value));
            setPicked(null);
          }}
        />
        <span className="flex-1" />
        {kb && (
          <NewRunDialog
            kb={kb}
            disabled={running}
            onStarted={() => queryClient.invalidateQueries({ queryKey: ["eval-compare"] })}
          />
        )}
      </div>

      <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)] grid-cols-[340px_minmax(0,1fr)] gap-3 max-[1240px]:grid-cols-[260px_minmax(0,1fr)] max-md:grid-cols-1 max-md:grid-rows-[50vh_80vh]">
        <RunList
          runs={list}
          base={baseId}
          target={targetId}
          onPick={(id) => setPicked({ base: id === baseId ? null : id, target: targetId })}
        />
        <section className="flex min-h-0 min-w-0 flex-col gap-3">
          {!target ? (
            <div className="grid flex-1 place-items-center rounded-3xl bg-card text-ink-3 shadow-card">还没有完成的评测。</div>
          ) : (
            <>
              <p className="mx-1 flex min-w-0 flex-none items-center gap-2 text-[13px] text-ink-2">
                <span className="shrink-0">基准</span>
                <b className="min-w-0 truncate font-semibold text-ink" title={base && indexLabel(base)}>
                  {base ? `#${base.id} ${recipeLabel(base)}` : "未选"}
                </b>
                <span className="shrink-0">→ 对比</span>
                <b className="min-w-0 truncate font-semibold text-blue" title={indexLabel(target)}>
                  #{target.id} {recipeLabel(target)}
                </b>
              </p>
              <ScoreCards base={base} target={target} />
              <QuestionList key={`${baseId}-${targetId}`} rows={compare.data ?? []} base={base} target={target} />
            </>
          )}
        </section>
      </div>
      <p className="mt-2 flex-none text-[11.5px] text-ink-3">分数是真实评测结果。题目少，一道题就是一两个百分点，个位数的差距不要当真。</p>
    </main>
  );
}
