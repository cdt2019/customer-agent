import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";

import { api, errorText } from "@/api/client";
import { indexDetail, Picker } from "@/components/shell/picker";
import { Metric } from "@/components/shell/metric";
import { Button } from "@/components/ui/button";
import { FileList } from "@/features/imports/file-list";
import { FileReview } from "@/features/imports/file-review";

export const Route = createFileRoute("/imports")({ component: Imports });

function Imports() {
  const queryClient = useQueryClient();
  const knowledgeBases = useQuery({
    queryKey: ["knowledge-bases"],
    queryFn: async () => (await api.GET("/api/knowledge-bases")).data ?? [],
  });
  const all = (knowledgeBases.data ?? []).filter((item) => item.indexes.length > 0);
  const [kbId, setKbId] = useState<number | null>(null);
  const [indexId, setIndexId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // 默认放到 samples：导入是试验性质的，别一上来就往正式知识库里加
  const kb = all.find((item) => item.id === kbId) ?? all.find((item) => item.name === "samples") ?? all[0];
  const index = kb?.indexes.find((item) => item.id === indexId) ?? kb?.indexes[0];

  const listed = useQuery({
    queryKey: ["imports", kb?.id],
    enabled: kb !== undefined,
    queryFn: async () => (await api.GET("/api/knowledge-bases/{kb_id}/imports", { params: { path: { kb_id: kb!.id } } })).data ?? [],
    refetchInterval: (query) => (query.state.data?.some((file) => file.status === "queued" || file.status === "parsing") ? 1200 : false),
  });
  const files = listed.data ?? [];
  const selected = files.find((file) => file.id === selectedId) ?? files[0];
  const count = (...statuses: string[]) => files.filter((file) => statuses.includes(file.status)).length;
  const pending = files.filter((file) => file.status === "pending");

  const upload = useMutation({
    mutationFn: async (chosen: File[]) => {
      const problems: string[] = [];
      let last: number | null = null;
      for (const file of chosen) {
        const { data, error } = await api.POST("/api/knowledge-bases/{kb_id}/imports", {
          params: { path: { kb_id: kb!.id } },
          body: { file: file as unknown as string },
          bodySerializer: (body) => {
            const form = new FormData();
            form.append("file", body.file as unknown as File);
            return form;
          },
        });
        if (data) last = data.id;
        else problems.push(`${file.name}：${errorText(error)}`);
      }
      return { problems, last };
    },
    onSuccess: ({ problems, last }) => {
      setNotice(problems.length ? problems.join("；") : null);
      if (last !== null) setSelectedId(last);
      queryClient.invalidateQueries({ queryKey: ["imports", kb?.id] });
    },
  });

  const confirm = useMutation({
    mutationFn: async ({ ids, saved }: { ids: number[]; saved: Promise<unknown> }) => {
      await saved;
      const { error, response } = await api.POST("/api/knowledge-bases/{kb_id}/imports/confirm", {
        params: { path: { kb_id: kb!.id } },
        body: { file_ids: ids, index_id: index!.id },
      });
      if (!response.ok) throw new Error(errorText(error));
      return ids;
    },
    onMutate: () => setNotice(null),
    onSuccess: (ids) => {
      setNotice(`已确认 ${ids.length} 份，正在切块和算向量，可以到任务页看进度`);
      const next = pending.find((file) => !ids.includes(file.id));
      if (next) setSelectedId(next.id);
      for (const key of ["imports", "knowledge-bases", "dataset", "tasks"]) queryClient.invalidateQueries({ queryKey: [key] });
    },
    onError: (error) => setNotice(error.message),
  });

  return (
    <main className="flex h-full min-w-0 flex-col px-5 py-3.5 max-md:h-auto max-md:px-3">
      <div className="mx-0.5 mb-3 flex flex-none flex-wrap items-center gap-2">
        <h1 className="mr-1.5 text-[22px] leading-tight font-bold tracking-tight whitespace-nowrap">导入和解析</h1>
        <Picker
          label="导入到"
          ariaLabel="导入到知识库"
          value={kb ? String(kb.id) : null}
          placeholder="没有知识库"
          options={all.map((item) => ({ value: String(item.id), label: `${item.name} · ${item.documents} 篇` }))}
          onChange={(value) => {
            setKbId(Number(value));
            setIndexId(null);
            setSelectedId(null);
            setNotice(null);
          }}
        />
        <Picker
          label="更新索引"
          value={index ? String(index.id) : null}
          placeholder="没有索引"
          options={(kb?.indexes ?? []).map((item) => ({ value: String(item.id), label: item.name, detail: indexDetail(item) }))}
          onChange={(value) => setIndexId(Number(value))}
        />
        <span className="flex-1" />
        <Button variant="outline" className="h-[34px] rounded-xl border-0 bg-white/70 px-3 text-[13px] text-ink-2 shadow-none" nativeButton={false} render={<Link to="/jobs" />}>
          查看任务
        </Button>
        <Button
          className="bg-brand h-9 rounded-xl px-5 font-semibold shadow-blue"
          disabled={pending.length === 0 || confirm.isPending || !index}
          onClick={() => confirm.mutate({ ids: pending.map((file) => file.id), saved: Promise.resolve() })}
        >
          确认全部{pending.length > 0 && ` ${pending.length}`}
        </Button>
      </div>

      <div className="mb-3 grid h-[72px] flex-none grid-cols-5 gap-2.5 max-md:grid-flow-col max-md:grid-cols-none max-md:auto-cols-[40%] max-md:overflow-x-auto max-md:[scrollbar-width:none]">
        <Metric label="导入的文件" value={String(files.length)} unit="份" />
        <Metric label="待确认" value={String(count("pending"))} unit="份" />
        <Metric label="解析中" value={String(count("queued", "parsing"))} unit="份" />
        <Metric label="失败" value={String(count("failed"))} unit="份" />
        <Metric label="已进知识库" value={String(count("confirmed"))} unit="份" hero />
      </div>
      {notice && <p className="mx-1 mb-2 flex-none truncate text-[13px] text-ink-2" title={notice}>{notice}</p>}

      <div className="grid min-h-0 flex-1 grid-cols-[318px_minmax(0,1fr)] grid-rows-[minmax(0,1fr)] gap-3 max-[1240px]:grid-cols-[250px_minmax(0,1fr)] max-md:grid-cols-1 max-md:grid-rows-[50vh_80vh]">
        <FileList files={files} selectedId={selected?.id ?? null} uploading={upload.isPending} onSelect={setSelectedId} onFiles={(chosen) => chosen.length && kb && upload.mutate(chosen)} />
        {selected ? (
          <FileReview
            key={selected.id}
            file={selected}
            confirming={confirm.isPending}
            canConfirm={index !== undefined}
            onConfirm={(saved) => confirm.mutate({ ids: [selected.id], saved })}
          />
        ) : (
          <div className="grid place-items-center rounded-3xl bg-card text-ink-3 shadow-card">拖入文件后，这里左右对照看解析结果。</div>
        )}
      </div>
    </main>
  );
}
