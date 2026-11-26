import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { api, errorText, type Recipe } from "@/api/client";
import { Chat } from "@/features/playground/chat";
import { Inspector } from "@/features/playground/inspector";
import type { Turn } from "@/features/playground/model";

// 从评测页跳过来时带上索引和题目
type Search = { index?: number; q?: string };

export const Route = createFileRoute("/playground")({
  component: Playground,
  validateSearch: (raw: Record<string, unknown>): Search => ({
    index: typeof raw.index === "number" ? raw.index : undefined,
    q: typeof raw.q === "string" ? raw.q : undefined,
  }),
});

// 默认配方：语义 + 关键词（docs/05 §12.5）
const DEFAULT_RECIPE: Recipe = { dense: true, keyword: true, expand: false, rerank: 0, candidates: 20, limit: 5 };

function Playground() {
  const search = Route.useSearch();
  const knowledgeBases = useQuery({
    queryKey: ["knowledge-bases"],
    queryFn: async () => (await api.GET("/api/knowledge-bases")).data ?? [],
  });
  const [indexId, setIndexId] = useState<number | null>(search.index ?? null);
  const [recipe, setRecipe] = useState(DEFAULT_RECIPE);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [focus, setFocus] = useState<{ chunkId: number; seq: number } | null>(null);
  const [chatFolded, setChatFolded] = useState(false);

  useEffect(() => {
    const first = knowledgeBases.data?.flatMap((kb) => kb.indexes)[0];
    if (indexId === null && first) setIndexId(first.id);
  }, [knowledgeBases.data, indexId]);

  const ask = useMutation({
    mutationFn: async (turn: Turn) => {
      const { data, error } = await api.POST("/api/playground", { body: { index_id: indexId!, question: turn.question, recipe: turn.recipe, answer: true } });
      if (!data) throw new Error(errorText(error));
      return data;
    },
    onSuccess: (result, turn) => setTurns((all) => all.map((item) => (item.id === turn.id ? { ...item, result } : item))),
    onError: (error, turn) => setTurns((all) => all.map((item) => (item.id === turn.id ? { ...item, error: error.message } : item))),
  });

  const send = (question: string) => {
    const turn: Turn = { id: Date.now(), question, recipe };
    setTurns((all) => [...all, turn]);
    setSelectedId(turn.id);
    ask.mutate(turn);
  };

  const selected = turns.find((turn) => turn.id === selectedId);
  const kb = knowledgeBases.data?.find((item) => item.indexes.some((index) => index.id === indexId));
  const index = kb?.indexes.find((item) => item.id === indexId);
  const examples = useQuery({
    queryKey: ["example-questions", kb?.id],
    enabled: kb !== undefined,
    queryFn: async () => (await api.GET("/api/knowledge-bases/{kb_id}/example-questions", { params: { path: { kb_id: kb!.id } } })).data ?? [],
  });
  const dense = recipe.dense || !recipe.keyword; // 两路至少留一路：都关时保留语义

  return (
    <div className="grid h-full min-w-0 grid-rows-[minmax(0,1fr)] max-md:h-auto max-md:grid-cols-1! max-md:grid-rows-[80vh_auto] max-md:[&>aside]:px-3" style={{ gridTemplateColumns: `${chatFolded ? 66 : 410}px minmax(0, 1fr)` }}>
      <Chat
        key={search.q}
        initialDraft={search.q ?? ""}
        intro={kb && index ? { name: kb.name, detail: `${kb.documents} 篇文档 · ${index.chunks.toLocaleString()} 块 · 索引 ${index.name}（${index.embed_model}）` } : null}
        examples={examples.data ?? []}
        turns={turns}
        selectedId={selectedId}
        busy={ask.isPending}
        canSend={indexId !== null}
        recipe={{ ...recipe, dense }}
        onRecipe={(next) => setRecipe({ ...next, dense: next.dense || !next.keyword })}
        onSend={send}
        onSelect={setSelectedId}
        onCite={(turnId, n) => {
          const chunkId = turns.find((turn) => turn.id === turnId)?.result?.selected[n - 1];
          setSelectedId(turnId);
          if (chunkId !== undefined) setFocus((before) => ({ chunkId, seq: (before?.seq ?? 0) + 1 }));
        }}
        folded={chatFolded}
        onFold={() => setChatFolded((value) => !value)}
      />
      <Inspector knowledgeBases={knowledgeBases.data ?? []} indexId={indexId} onIndex={setIndexId} question={selected?.question} result={selected?.result} recipe={{ ...recipe, dense }} waiting={ask.isPending} focus={focus} />
    </div>
  );
}
