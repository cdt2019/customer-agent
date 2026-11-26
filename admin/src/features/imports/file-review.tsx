import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, errorText, type ImportFile, toLogin } from "@/api/client";
import { Picker } from "@/components/shell/picker";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { formatSize, STATUS } from "./file-list";

async function must<T>(call: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T | undefined> {
  const { data, error, response } = await call;
  if (!response.ok) throw new Error(errorText(error));
  return data;
}

function Original({ file }: { file: ImportFile }) {
  const url = `/api/imports/${file.id}/original`;
  const isPdf = file.suffix === ".pdf";
  const source = useQuery({
    queryKey: ["import-original", file.id],
    enabled: file.previewable && !isPdf,
    queryFn: async () => {
      const response = await fetch(url);
      if (response.status === 401) toLogin();
      return response.text();
    },
  });
  if (isPdf) {
    return (
      <>
        <iframe title={`原文件 ${file.filename}`} src={url} className="min-h-0 w-full flex-1 border-0 bg-tile" />
        <a href={url} target="_blank" rel="noreferrer" className="flex-none px-4.5 py-1.5 text-xs font-semibold text-blue hover:underline">
          在新窗口打开
        </a>
      </>
    );
  }
  if (file.previewable) {
    // 当纯文本显示：HTML 里的标签和脚本都不会生效
    return <pre className="m-0 min-h-0 flex-1 overflow-auto px-4.5 py-2 font-mono text-[13px] leading-7 break-words whitespace-pre-wrap text-ink-2">{source.data}</pre>;
  }
  return (
    <div className="grid flex-1 place-items-center px-6 text-center text-[13px] text-ink-3">
      <p>
        Word 文件没法在浏览器里直接看。
        <a href={url} className="ml-1 font-semibold text-blue hover:underline">下载原文件</a>
      </p>
    </div>
  );
}

export function FileReview({ file, onConfirm, confirming, canConfirm }: { file: ImportFile; onConfirm: (saved: Promise<unknown>) => void; confirming: boolean; canConfirm: boolean }) {
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ["import", file.id, file.status, file.parser],
    queryFn: async () => (await api.GET("/api/imports/{file_id}", { params: { path: { file_id: file.id } } })).data ?? null,
  });
  const saved = detail.data?.markdown ?? "";
  const [draft, setDraft] = useState<string | null>(null);
  useEffect(() => setDraft(null), [file.id, file.status, file.parser]);
  const text = draft ?? saved;
  const dirty = draft !== null && draft !== saved;
  const editable = file.status === "pending";

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["imports"] });
    queryClient.invalidateQueries({ queryKey: ["import", file.id] });
  };
  const persist = () => must(api.PATCH("/api/imports/{file_id}", { params: { path: { file_id: file.id } }, body: { markdown: text } }));
  const save = useMutation({ mutationFn: persist, onSuccess: () => { refresh(); setDraft(null); } });
  const reparse = useMutation({
    mutationFn: (parser?: string) => must(api.POST("/api/imports/{file_id}/reparse", { params: { path: { file_id: file.id } }, body: { parser } })),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => must(api.DELETE("/api/imports/{file_id}", { params: { path: { file_id: file.id } } })),
    onSuccess: refresh,
  });
  const failure = save.error ?? reparse.error ?? remove.error;
  const status = STATUS[file.status];
  const working = file.status === "queued" || file.status === "parsing";

  return (
    <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
      <div className="flex flex-none items-center gap-2.5 border-b border-hair px-4.5 pt-3 pb-2.5">
        <h2 className="min-w-0 truncate text-[17px] leading-snug font-bold">{file.filename}</h2>
        <span className={cn("shrink-0 text-xs font-semibold", status.color)}>{status.label}</span>
        <span className="flex-1" />
        <span className="shrink-0 text-xs text-ink-3">{formatSize(file.size)}</span>
        {file.parsers.length > 1 ? (
          <Picker
            label="解析器"
            className="h-8 shrink-0 bg-tile text-xs"
            value={file.parser}
            placeholder=""
            options={file.parsers.map((parser) => ({ value: parser.name, label: parser.label, disabled: !(editable || file.status === "failed") }))}
            onChange={(parser) => parser !== file.parser && reparse.mutate(parser)}
          />
        ) : (
          <span className="shrink-0 text-xs text-ink-3">{file.parsers[0]?.label}</span>
        )}
        <Button variant="secondary" size="sm" className="shrink-0 rounded-[10px] px-3" disabled={!(editable || file.status === "failed") || reparse.isPending} onClick={() => reparse.mutate(undefined)}>
          重新解析
        </Button>
      </div>

      {(file.checks.length > 0 || file.warnings.length > 0) && (
        <div className="flex flex-none flex-wrap gap-1.5 border-b border-hair px-4.5 py-2">
          {file.checks.map((check) => <span key={check} className="rounded-lg bg-chip px-2 text-xs text-ink-2">{check}</span>)}
          {file.warnings.map((warning) => <span key={warning} className="rounded-lg bg-warn-soft px-2 text-xs text-warn">{warning}</span>)}
        </div>
      )}
      {file.error && <p className="mx-4.5 mt-2.5 flex-none rounded-[11px] bg-down/10 px-3 py-2 text-[13px] text-down">{file.error}</p>}

      {working ? (
        <div className="grid flex-1 place-items-center text-ink-3">{file.status === "queued" ? "排队等待解析" : "正在解析，Word 和 PDF 第一次要加载模型，可能要一两分钟"}</div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-2 grid-rows-[minmax(0,1fr)] max-md:grid-cols-1 max-md:grid-rows-2">
          <div className="flex min-h-0 min-w-0 flex-col">
            <h3 className="flex-none px-4.5 pt-2.5 pb-1.5 text-[12.5px] font-semibold text-ink-3">原文件</h3>
            <Original file={file} />
          </div>
          <div className="flex min-h-0 min-w-0 flex-col border-l border-hair">
            <h3 className="flex flex-none justify-between px-4.5 pt-2.5 pb-1.5 text-[12.5px] font-semibold text-ink-3">
              解析结果 · Markdown
              <span className="font-normal">{editable ? "可以直接修改" : "只读"}</span>
            </h3>
            <Textarea
              aria-label="解析结果"
              value={text}
              readOnly={!editable}
              onChange={(event) => setDraft(event.target.value)}
              className="min-h-0 flex-1 resize-none rounded-none border-0 bg-tile/60 px-4.5 py-2 font-mono text-[13px] leading-7 shadow-none focus-visible:ring-0 field-sizing-fixed"
            />
          </div>
        </div>
      )}

      <div className="flex flex-none items-center gap-2 border-t border-hair px-4.5 py-2.5">
        {failure ? <span className="min-w-0 truncate text-[12.5px] text-down">{failure.message}</span> : dirty && <span className="text-[12.5px] text-warn">有没保存的修改</span>}
        <span className="flex-1" />
        <Button variant="secondary" className="h-9 rounded-xl px-3.5" disabled={!(editable || file.status === "failed") || remove.isPending} onClick={() => remove.mutate()}>
          移除
        </Button>
        <Button variant="secondary" className="h-9 rounded-xl px-3.5" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
          保存修改
        </Button>
        <Button
          className="bg-brand h-9 rounded-xl px-5 font-semibold shadow-blue"
          disabled={!editable || !text.trim() || confirming || !canConfirm}
          onClick={() => onConfirm(dirty ? persist().then(() => setDraft(null)) : Promise.resolve())}
        >
          {file.status === "confirmed" ? "已确认" : confirming ? "处理中" : "确认，开始切块"}
        </Button>
      </div>
    </section>
  );
}
