import { memo, useRef } from "react";

import type { ChunkPreview } from "@/api/client";
import { Button } from "@/components/ui/button";
import { markLinked, scrollWithin } from "@/lib/linked";
import { cn } from "@/lib/utils";

const SHORT = 60;

const Blocks = memo(function Blocks({ chunks }: { chunks: ChunkPreview["chunks"] }) {
  return (
    <div className="px-4 pt-3 pb-4 text-[13.5px] leading-7">
      {chunks.map((chunk, n) => (
        <div
          key={n}
          data-c={n}
          className="mb-1.5 rounded-[10px] border-l-[3px] border-blue/50 bg-blue-soft/50 px-2.5 py-1.5 break-words whitespace-pre-wrap text-ink-2 transition-colors even:border-ink-3/50 even:bg-tile data-[on]:border-blue data-[on]:!bg-blue-soft"
        >
          {chunk.heading_path.length > 0 && <span className="mb-0.5 block text-xs font-semibold text-blue">{chunk.heading_path.join(" › ")}</span>}
          {chunk.overlap > 0 && <mark className="rounded-sm bg-warn-soft text-inherit">{chunk.text.slice(0, chunk.overlap)}</mark>}
          {chunk.text.slice(chunk.overlap)}
        </div>
      ))}
      {chunks.length === 0 && <p className="text-ink-3">这篇文档切不出内容。</p>}
    </div>
  );
});

const List = memo(function List({ chunks, limit, onJump }: { chunks: ChunkPreview["chunks"]; limit: number; onJump: (n: number) => void }) {
  const top = Math.max(limit, ...chunks.map((chunk) => chunk.text.length));
  return (
    <div className="px-2.5 pt-2.5 pb-3">
      {chunks.map((chunk, n) => {
        const bad = chunk.text.length < SHORT || chunk.text.length > limit;
        return (
          <Button
            key={n}
            variant="ghost"
            data-c={n}
            onClick={() => onJump(n)}
            className="mb-1.5 block h-auto w-full rounded-[13px] bg-tile px-3 py-2 text-left font-normal whitespace-normal hover:bg-blue-soft active:translate-y-0 data-[on]:bg-blue-soft"
          >
            <span className="flex items-center gap-2">
              <span className="grid size-[22px] shrink-0 place-items-center rounded-[7px] bg-white font-num text-[11.5px] font-bold text-ink-2">{n + 1}</span>
              <span className="min-w-0 flex-1 truncate text-[12.5px] font-semibold text-ink">{chunk.heading_path.at(-1) ?? `第 ${n + 1} 段`}</span>
              <span className={cn("font-num text-[12.5px] font-bold whitespace-nowrap", bad ? "text-down" : "text-ink")}>{chunk.text.length} 字</span>
            </span>
            <span className="mt-1.5 block h-1 overflow-hidden rounded-full bg-chip">
              <i className={cn("block h-full rounded-full", bad ? "bg-down" : "bg-brand")} style={{ width: `${(chunk.text.length / top) * 100}%` }} />
            </span>
          </Button>
        );
      })}
    </div>
  );
});

export function Preview({ chunks, limit }: { chunks: ChunkPreview["chunks"]; limit: number }) {
  const root = useRef<HTMLDivElement>(null);
  const jump = useRef((n: number) => {
    const target = root.current?.querySelector(`[data-preview] [data-c="${n}"]`);
    if (target) scrollWithin(target);
    markLinked(root.current, String(n));
  });
  return (
    <div
      ref={root}
      className="contents"
      onMouseOver={(event) => markLinked(root.current, (event.target as HTMLElement).closest<HTMLElement>("[data-c]")?.dataset.c ?? null)}
      onMouseLeave={() => markLinked(root.current, null)}
    >
      <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
        <div className="flex flex-none items-baseline gap-2 border-b border-hair px-4.5 pt-3 pb-2.5">
          <h2 className="text-[15px] font-bold whitespace-nowrap">切块预览</h2>
          <span className="truncate text-xs text-ink-3">颜色交替表示不同的块，鼠标移上去和右边对应</span>
        </div>
        <div data-preview data-scroll className="min-h-0 flex-1 overflow-auto">
          <Blocks chunks={chunks} />
        </div>
      </section>
      <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl bg-card shadow-card max-[1240px]:hidden">
        <div className="flex flex-none items-baseline gap-2 border-b border-hair px-4.5 pt-3 pb-2.5">
          <h2 className="text-[15px] font-bold">块列表</h2>
          <span className="text-xs text-ink-3">共 {chunks.length} 块，红色是过短或过长</span>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          <List chunks={chunks} limit={limit} onJump={jump.current} />
        </div>
      </section>
    </div>
  );
}
