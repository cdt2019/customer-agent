import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";

import { api, type DatasetInfo, errorText } from "@/api/client";
import { indexDetail, Picker } from "@/components/shell/picker";
import { Metric } from "@/components/shell/metric";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { DocList } from "@/components/shell/doc-list";
import { DocView } from "@/features/datasets/doc-view";

// 从切块实验室存完新索引后跳过来，直接看它的进度
type Search = { index?: number };

export const Route = createFileRoute("/datasets")({
  component: Datasets,
  validateSearch: (raw: Record<string, unknown>): Search => ({ index: typeof raw.index === "number" ? raw.index : undefined }),
});

function jobText(data: DatasetInfo, busy: boolean): string {
  const job = data.last_job;
  if (busy) return job?.status === "running" ? `${job.progress.store ?? 0} / ${job.total} 篇` : "准备中";
  if (!job) return "还没有";
  if (job.status === "failed") return "失败";
  if (job.status === "cancelled") return "已取消";
  if (!job.finished_at) return "—";
  const minutes = Math.floor((Date.now() - new Date(job.finished_at).getTime()) / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  return minutes < 1440 ? `${Math.floor(minutes / 60)} 小时前` : `${Math.floor(minutes / 1440)} 天前`;
}

function Datasets() {
  const queryClient = useQueryClient();
  const knowledgeBases = useQuery({
    queryKey: ["knowledge-bases"],
    queryFn: async () => (await api.GET("/api/knowledge-bases")).data ?? [],
  });
  const all = knowledgeBases.data ?? [];
  const search = Route.useSearch();
  const [indexId, setIndexId] = useState<number | null>(search.index ?? null);
  const [documentId, setDocumentId] = useState<number | null>(null);
  const kb = all.find((item) => item.indexes.some((index) => index.id === indexId)) ?? all.find((item) => item.indexes.length > 0);
  const index = kb?.indexes.find((item) => item.id === indexId) ?? kb?.indexes[0];

  const dataset = useQuery({
    queryKey: ["dataset", index?.id],
    enabled: index !== undefined,
    queryFn: async () => (await api.GET("/api/indexes/{index_id}/dataset", { params: { path: { index_id: index!.id } } })).data ?? null,
    refetchInterval: (query) => (query.state.data?.busy ? 1200 : false),
    refetchOnMount: "always",
  });
  const data = dataset.data;
  const documents = data?.documents ?? [];
  const selected = documents.find((doc) => doc.id === documentId) ?? documents[0];

  // 任务一结束，块数、文档内容都可能变了
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && data && !data.busy) {
      queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
      queryClient.invalidateQueries({ queryKey: ["document"] });
    }
    wasBusy.current = data?.busy ?? false;
  }, [data, queryClient]);

  const action = useMutation({
    mutationFn: async (kind: "sync" | "rebuild") => {
      const { error } = await api.POST(kind === "sync" ? "/api/indexes/{index_id}/sync" : "/api/indexes/{index_id}/rebuild", { params: { path: { index_id: index!.id } } });
      if (error) throw new Error(errorText(error));
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["dataset", index?.id] }),
  });
  const busy = (data?.busy ?? false) || action.isPending;
  const stale = documents.filter((doc) => doc.stale).length;
  const failure = data?.last_job?.status === "failed" ? data.last_job.error : null;

  return (
    <main className="flex h-full min-w-0 flex-col px-5 py-3.5 max-md:h-auto max-md:px-3">
      <div className="mx-0.5 mb-3 flex flex-none flex-wrap items-center gap-2">
        <h1 className="mr-1.5 text-[22px] leading-tight font-bold tracking-tight whitespace-nowrap">数据集</h1>
        <Picker
          label="知识库"
          value={kb ? String(kb.id) : null}
          placeholder="没有知识库"
          options={all.map((item) => ({ value: String(item.id), label: `${item.name} · ${item.documents} 篇`, disabled: item.indexes.length === 0 }))}
          onChange={(value) => {
            setIndexId(all.find((item) => String(item.id) === value)?.indexes[0]?.id ?? null);
            setDocumentId(null);
          }}
        />
        <Picker
          label="索引"
          ariaLabel="索引版本"
          value={index ? String(index.id) : null}
          placeholder="没有索引"
          options={(kb?.indexes ?? []).map((item) => ({ value: String(item.id), label: item.name, detail: indexDetail(item) }))}
          onChange={(value) => setIndexId(Number(value))}
        />
        <span className="flex-1" />
        {action.error && <span className="text-[13px] text-down">{action.error.message}</span>}
        <Button variant="outline" className="h-[34px] rounded-xl border-0 bg-white/70 px-3 text-[13px] text-ink-2 shadow-none" nativeButton={false} render={<Link to="/imports" />}>
          导入文件
        </Button>
        <Dialog>
          <DialogTrigger render={<Button variant="outline" className="h-[34px] rounded-xl border-0 bg-white/70 px-3 text-[13px] text-ink-2 shadow-none" disabled={busy || !index} />}>
            全部重建
          </DialogTrigger>
          <DialogContent className="rounded-2xl sm:max-w-md">
            <DialogHeader>
              <DialogTitle>重建索引 {index?.name}？</DialogTitle>
              <DialogDescription>
                会清掉这个索引现有的 {data?.chunks ?? 0} 块，再把 {documents.length} 篇文档全部重切、重算向量。重建期间检索结果不完整。文档原文不受影响。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose render={<Button variant="outline" className="rounded-xl" />}>取消</DialogClose>
              <DialogClose render={<Button className="bg-brand rounded-xl px-4" onClick={() => action.mutate("rebuild")} />}>重建</DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        <Button className="bg-brand h-9 rounded-xl px-5 font-semibold shadow-blue" disabled={busy || !data?.can_sync} onClick={() => action.mutate("sync")}>
          {busy ? "处理中" : "现在同步"}
        </Button>
      </div>

      {data && (
        <div className="mb-3 grid h-[72px] flex-none grid-cols-[repeat(5,minmax(0,1fr))_minmax(150px,1.3fr)] gap-2.5 max-md:grid-flow-col max-md:grid-cols-none max-md:auto-cols-[40%] max-md:overflow-x-auto max-md:[scrollbar-width:none]">
          <Metric label="文档" value={String(documents.length)} unit="篇" />
          <Metric label="块" value={data.chunks.toLocaleString()} unit="块" />
          <Metric label="平均长度" value={String(data.average_chars)} unit="字" />
          <Metric label="待更新" value={String(stale)} unit="篇" />
          <Metric label="向量模型" value={data.embed_model} />
          <Metric label={busy ? "正在更新" : "上次更新"} value={jobText(data, busy)} hero />
        </div>
      )}
      {failure && !busy && <p className="mx-1 mb-2 flex-none truncate text-[13px] text-down" title={failure}>上次任务失败：{failure}</p>}

      <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)] grid-cols-[318px_minmax(0,1fr)] gap-3 max-[1240px]:grid-cols-[250px_minmax(0,1fr)] max-md:grid-cols-1 max-md:grid-rows-[50vh_80vh]">
        <DocList documents={documents} selectedId={selected?.id ?? null} onSelect={setDocumentId} />
        {index && selected ? (
          <DocView indexId={index.id} documentId={selected.id} chunkSize={index.chunk_size} version={`${data?.last_job?.finished_at}`} />
        ) : (
          <div className="grid place-items-center rounded-3xl bg-card text-ink-3 shadow-card">{dataset.isPending ? "正在读取" : "这个知识库还没有文档"}</div>
        )}
      </div>
    </main>
  );
}
