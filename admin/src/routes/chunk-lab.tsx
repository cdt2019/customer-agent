import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";

import { api, type ChunkPreview, type ChunkSettings, type ChunkStats, errorText, type IndexVersion } from "@/api/client";
import { DocList } from "@/components/shell/doc-list";
import { indexDetail, Picker } from "@/components/shell/picker";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Controls } from "@/features/chunk-lab/controls";
import { Preview } from "@/features/chunk-lab/preview";
import { SaveDialog } from "@/features/chunk-lab/save-dialog";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/chunk-lab")({ component: ChunkLab });

const settingsOf = (index: IndexVersion): ChunkSettings => ({ chunker: index.chunker as ChunkSettings["chunker"], size: index.chunk_size, overlap: index.overlap });

const METRICS: { key: keyof ChunkStats; label: string; unit: string; lowerIsBetter?: boolean }[] = [
  { key: "count", label: "块数", unit: "块" },
  { key: "average", label: "平均长度", unit: "字" },
  { key: "shortest", label: "最短", unit: "字" },
  { key: "longest", label: "最长", unit: "字" },
  { key: "short", label: "过短", unit: "块", lowerIsBetter: true },
  { key: "long", label: "过长", unit: "块", lowerIsBetter: true },
];

function Metric({ label, unit, value, before, lowerIsBetter, hero }: { label: string; unit: string; value: number; before: number; lowerIsBetter?: boolean; hero: boolean }) {
  const change = value - before;
  const tone = hero ? "text-white" : !lowerIsBetter || change === 0 ? "text-ink-3" : change < 0 ? "text-up" : "text-down";
  return (
    <div className={cn("flex min-w-0 flex-col justify-center overflow-hidden rounded-[18px] px-3.5", hero ? "bg-hero text-white shadow-blue" : "bg-card shadow-card")}>
      <span className={cn("text-[11.5px] leading-snug whitespace-nowrap", hero ? "text-white/85" : "text-ink-3")}>{label}</span>
      <b className="font-num text-[19px] leading-tight font-bold whitespace-nowrap">
        {value.toLocaleString()}
        <small className={cn("ml-0.5 text-[11px] font-medium", hero ? "text-white/85" : "text-ink-2")}>{unit}</small>
        <em className={cn("ml-1.5 text-[11.5px] font-semibold not-italic", tone)}>{change === 0 ? "持平" : `${change > 0 ? "+" : ""}${change.toLocaleString()}`}</em>
      </b>
    </div>
  );
}

function ChunkLab() {
  const knowledgeBases = useQuery({
    queryKey: ["knowledge-bases"],
    queryFn: async () => (await api.GET("/api/knowledge-bases")).data ?? [],
  });
  const all = (knowledgeBases.data ?? []).filter((item) => item.indexes.length > 0);
  const [indexId, setIndexId] = useState<number | null>(null);
  const [documentId, setDocumentId] = useState<number | null>(null);
  const [choosing, setChoosing] = useState(false);
  const [scope, setScope] = useState<"document" | "knowledge_base">("document");
  const [edited, setEdited] = useState<ChunkSettings | null>(null);
  const kb = all.find((item) => item.indexes.some((index) => index.id === indexId)) ?? all[0];
  const index = kb?.indexes.find((item) => item.id === indexId) ?? kb?.indexes[0];
  const settings = edited ?? (index ? settingsOf(index) : null);

  // 拖滑块时不用每一格都请求
  const [debounced, setDebounced] = useState(settings);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(settings), 150);
    return () => clearTimeout(timer);
  }, [JSON.stringify(settings)]);

  const dataset = useQuery({
    queryKey: ["dataset", index?.id],
    enabled: index !== undefined,
    queryFn: async () => (await api.GET("/api/indexes/{index_id}/dataset", { params: { path: { index_id: index!.id } } })).data ?? null,
  });
  const documents = dataset.data?.documents ?? [];
  const document = documents.find((doc) => doc.id === documentId) ?? documents[0];

  const preview = useQuery<ChunkPreview>({
    queryKey: ["chunk-preview", index?.id, document?.id, debounced],
    enabled: index !== undefined && document !== undefined && debounced !== null,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data, error } = await api.POST("/api/chunk-lab/preview", { body: { index_id: index!.id, document_id: document!.id, ...debounced! } });
      if (!data) throw new Error(errorText(error));
      return data;
    },
  });
  const result = preview.data;
  const comparison = result?.[scope];
  const unchanged = !index || !settings || (settings.chunker === index.chunker && settings.size === index.chunk_size && settings.overlap === index.overlap);

  return (
    <main className="flex h-full min-w-0 flex-col px-5 py-3.5 max-md:h-auto max-md:px-3">
      <div className="mx-0.5 mb-3 flex flex-none flex-wrap items-center gap-2">
        <h1 className="mr-1.5 text-[22px] leading-tight font-bold tracking-tight whitespace-nowrap">切块实验室</h1>
        <Picker
          label="知识库"
          value={kb ? String(kb.id) : null}
          placeholder="没有知识库"
          options={all.map((item) => ({ value: String(item.id), label: `${item.name} · ${item.documents} 篇` }))}
          onChange={(value) => {
            setIndexId(all.find((item) => String(item.id) === value)?.indexes[0]?.id ?? null);
            setDocumentId(null);
            setEdited(null);
          }}
        />
        <Picker
          label="对比"
          ariaLabel="对比的索引版本"
          value={index ? String(index.id) : null}
          placeholder="没有索引"
          options={(kb?.indexes ?? []).map((item) => ({ value: String(item.id), label: item.name, detail: indexDetail(item) }))}
          onChange={(value) => {
            setIndexId(Number(value));
            setEdited(null);
          }}
        />
        <span className="flex-1" />
        {preview.isFetching && <span className="text-xs text-ink-3">计算中</span>}
        <Button variant="outline" className="h-[34px] rounded-xl border-0 bg-white/70 px-3 text-[13px] text-ink-2 shadow-none" disabled={unchanged} onClick={() => setEdited(null)}>
          恢复对比版本的设置
        </Button>
        {index && settings && <SaveDialog indexId={index.id} settings={settings} chunks={result?.knowledge_base.candidate.count ?? 0} disabled={unchanged || preview.isFetching} />}
      </div>

      {comparison && (
        <div className="mb-3 grid h-[72px] flex-none grid-cols-6 gap-2.5 max-md:grid-flow-col max-md:grid-cols-none max-md:auto-cols-[40%] max-md:overflow-x-auto max-md:[scrollbar-width:none]">
          {METRICS.map((metric, n) => (
            <Metric key={metric.key} label={metric.label} unit={metric.unit} value={comparison.candidate[metric.key]} before={comparison.current[metric.key]} lowerIsBetter={metric.lowerIsBetter} hero={n === 0} />
          ))}
        </div>
      )}
      {preview.error && <p className="mx-1 mb-2 flex-none text-[13px] text-down">{preview.error.message}</p>}

      <div className="grid min-h-0 flex-1 grid-cols-[276px_minmax(0,1fr)_330px] grid-rows-[minmax(0,1fr)] gap-3 max-[1360px]:grid-cols-[250px_minmax(0,1fr)_260px] max-[1240px]:grid-cols-[230px_minmax(0,1fr)] max-md:grid-cols-1 max-md:grid-rows-[auto_70vh_auto]">
        <section className="min-h-0 overflow-auto rounded-3xl bg-card px-4 py-3.5 shadow-card">
          <h2 className="mb-2.5 text-[15px] font-bold">切块设置</h2>
          <Popover open={choosing} onOpenChange={setChoosing}>
            <PopoverTrigger
              render={<Button variant="outline" className="h-[34px] w-full justify-start gap-2 rounded-xl border-0 bg-tile px-3 text-[13px] font-normal shadow-none" aria-label="预览文档" />}
            >
              <span className="shrink-0 text-ink-2">文档</span>
              <span className="min-w-0 flex-1 truncate text-left">{document ? document.title : "没有文档"}</span>
              <ChevronDown className="text-ink-3" />
            </PopoverTrigger>
            <PopoverContent align="start" className="h-[min(560px,70vh)] w-[380px] max-w-[calc(100vw-24px)] rounded-3xl p-0">
              <DocList
                documents={documents}
                selectedId={document?.id ?? null}
                onSelect={(id) => {
                  setDocumentId(id);
                  setChoosing(false);
                }}
                className="h-full bg-white shadow-none"
              />
            </PopoverContent>
          </Popover>
          {settings && <Controls settings={settings} onChange={setEdited} />}
          <span className="mt-4 mb-1.5 block text-[13px] text-ink-2">指标看</span>
          <Tabs value={scope} onValueChange={(value) => setScope(value as typeof scope)}>
            <TabsList className="w-full rounded-[11px] bg-chip">
              <TabsTrigger value="document" className="rounded-lg text-[13px]">这一篇</TabsTrigger>
              <TabsTrigger value="knowledge_base" className="rounded-lg text-[13px]">整个知识库</TabsTrigger>
            </TabsList>
          </Tabs>
        </section>
        {result && settings ? (
          <Preview chunks={result.chunks} limit={(debounced ?? settings).size + (debounced ?? settings).overlap} />
        ) : (
          <div className="col-span-2 grid place-items-center rounded-3xl bg-card text-ink-3 shadow-card">{preview.error ? "预览失败" : "正在计算"}</div>
        )}
      </div>
    </main>
  );
}
