import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { memo, useMemo, useRef } from "react";

import { api, type DocumentDetail } from "@/api/client";
import { Button } from "@/components/ui/button";
import { markLinked, scrollWithin } from "@/lib/linked";

import { kindLabel } from "@/components/shell/doc-list";
import { segmentsOf } from "./segments";

const Source = memo(function Source({ detail }: { detail: DocumentDetail }) {
  const segments = useMemo(() => segmentsOf(detail.markdown, detail.chunks), [detail]);
  return (
    <pre className="m-0 px-5 pt-1 pb-4 font-sans text-[13.5px] leading-7 break-words whitespace-pre-wrap text-ink-2">
      {segments.map((segment, n) =>
        segment.chunkId === null ? (
          <span key={n} className="text-ink-3">{segment.text}</span>
        ) : (
          <span key={n} data-c={segment.chunkId} className="rounded-sm border-b-2 border-blue/25 transition-colors data-[on]:bg-blue-soft">{segment.text}</span>
        ),
      )}
    </pre>
  );
});

const Chunks = memo(function Chunks({ detail, size, onJump }: { detail: DocumentDetail; size: number; onJump: (id: number) => void }) {
  return (
    <div className="px-3.5 pt-1 pb-4">
      {detail.chunks.map((chunk) => (
        <Button
          key={chunk.id}
          variant="ghost"
          data-c={chunk.id}
          onClick={() => onJump(chunk.id)}
          className="mb-2 block h-auto w-full rounded-[15px] bg-white px-3 py-2.5 text-left font-normal whitespace-normal shadow-sm hover:bg-blue-soft active:translate-y-0 data-[on]:bg-blue-soft"
        >
          <span className="flex items-center gap-2">
            <span className="grid size-6 shrink-0 place-items-center rounded-lg bg-blue-soft font-num text-xs font-bold text-blue">{chunk.seq + 1}</span>
            <span className="min-w-0 flex-1 truncate text-xs text-ink-3">{chunk.heading_path.join(" › ") || "无小节"}</span>
            <span className="font-num text-[12.5px] font-bold whitespace-nowrap text-ink">{chunk.text.length} 字</span>
          </span>
          <span className="my-1.5 block h-1 overflow-hidden rounded-full bg-chip">
            <i className="bg-brand block h-full rounded-full" style={{ width: `${Math.min(100, (chunk.text.length / size) * 100)}%` }} />
          </span>
          <span className="line-clamp-2 text-[12.5px] leading-relaxed text-ink-2">{chunk.text}</span>
        </Button>
      ))}
      {detail.chunks.length === 0 && <p className="px-2 text-ink-3">这篇文档在当前索引里还没有块。</p>}
    </div>
  );
});

export function DocView({ indexId, documentId, chunkSize, version }: { indexId: number; documentId: number; chunkSize: number; version: string }) {
  const root = useRef<HTMLDivElement>(null);
  const detail = useQuery({
    queryKey: ["document", indexId, documentId, version],
    queryFn: async () => (await api.GET("/api/indexes/{index_id}/documents/{document_id}", { params: { path: { index_id: indexId, document_id: documentId } } })).data ?? null,
  });
  const onJump = useMemo(
    () => (id: number) => {
      const target = root.current?.querySelector(`pre [data-c="${id}"]`);
      if (target) scrollWithin(target);
      markLinked(root.current, String(id));
    },
    [],
  );

  return (
    <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
      {!detail.data ? (
        <div className="grid flex-1 place-items-center text-ink-3">{detail.isPending ? "正在读取" : "读取失败"}</div>
      ) : (
        <>
          <div className="flex flex-none items-center gap-2.5 border-b border-hair px-5 pt-3.5 pb-2.5">
            <h2 className="min-w-0 truncate text-[17px] leading-snug font-bold">{detail.data.title}</h2>
            <span className="shrink-0 rounded-lg bg-chip px-2 text-xs text-ink-2">{kindLabel(detail.data.kind)}</span>
            <span className="shrink-0 rounded-lg bg-chip px-2 text-xs text-ink-2">{detail.data.chunks.length} 块</span>
            <span className="flex-1" />
            <Link to="/playground" search={{ index: indexId, q: detail.data.title }} className="shrink-0 text-[13px] font-semibold text-blue hover:underline">
              去测试台提问
            </Link>
          </div>
          <div
            ref={root}
            className="grid min-h-0 flex-1 grid-cols-2 grid-rows-[minmax(0,1fr)] max-md:grid-cols-1 max-md:grid-rows-2"
            onMouseOver={(event) => markLinked(root.current, (event.target as HTMLElement).closest<HTMLElement>("[data-c]")?.dataset.c ?? null)}
            onMouseLeave={() => markLinked(root.current, null)}
          >
            <div className="flex min-h-0 min-w-0 flex-col">
              <h3 className="flex-none px-5 pt-2.5 pb-1.5 text-[12.5px] font-semibold text-ink-3">原文</h3>
              <div data-scroll className="min-h-0 flex-1 overflow-auto">
                <Source detail={detail.data} />
              </div>
            </div>
            <div className="flex min-h-0 min-w-0 flex-col border-l border-hair bg-tile/60">
              <h3 className="flex-none px-5 pt-2.5 pb-1.5 text-[12.5px] font-semibold text-ink-3">切出来的块</h3>
              <div className="min-h-0 flex-1 overflow-auto">
                <Chunks detail={detail.data} size={chunkSize} onJump={onJump} />
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
