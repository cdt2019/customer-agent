import { Search } from "lucide-react";
import { useState } from "react";

import type { DocumentRow } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Toggle } from "@/components/ui/toggle";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<string, string> = { faq: "常见问题", guide: "教程", notice: "公告", page: "法务", product: "商品", upload: "导入" };
export const kindLabel = (kind: string) => KIND_LABEL[kind] ?? kind;

/** 文档列表：搜索、按类型筛、点一篇选中。数据集页常驻左栏，切块实验室放在弹出面板里。 */
export function DocList({
  documents,
  selectedId,
  onSelect,
  className,
}: {
  documents: DocumentRow[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  className?: string;
}) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<string | null>(null);
  const kinds = [...new Set(documents.map((doc) => doc.kind))];
  const needle = query.trim().toLowerCase();
  const shown = documents.filter(
    (doc) => (!kind || doc.kind === kind) && (!needle || doc.title.toLowerCase().includes(needle) || doc.source_id.toLowerCase().includes(needle)),
  );

  return (
    <section className={cn("flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl bg-card shadow-card", className)}>
      <label className="m-3 mb-2 flex h-[38px] flex-none items-center gap-2 rounded-[13px] bg-tile px-3 text-ink-3">
        <Search className="size-4 shrink-0" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="搜索文档"
          placeholder="搜索文档"
          className="h-auto min-w-0 border-0 bg-transparent p-0 text-sm text-ink shadow-none focus-visible:ring-0 dark:bg-transparent"
        />
      </label>
      {kinds.length > 1 && (
        <div className="flex flex-none flex-wrap gap-1.5 px-3 pb-2.5">
          {kinds.map((name) => (
            <Toggle
              key={name}
              size="sm"
              pressed={kind === name}
              onPressedChange={(pressed) => setKind(pressed ? name : null)}
              className="h-[26px] min-w-0 rounded-[9px] bg-tile px-2.5 text-[12.5px] text-ink-2 data-pressed:bg-blue data-pressed:font-semibold data-pressed:text-white"
            >
              {kindLabel(name)}
            </Toggle>
          ))}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-auto px-2 pb-2">
        {shown.length === 0 && <p className="px-2.5 py-3 text-ink-3">没有匹配的文档</p>}
        {shown.map((doc) => (
          <Button
            key={doc.id}
            variant="ghost"
            aria-current={doc.id === selectedId}
            onClick={() => onSelect(doc.id)}
            className={cn(
              "mb-0.5 grid h-auto w-full grid-cols-[minmax(0,1fr)_auto] gap-x-2 rounded-[14px] px-3 py-2 text-left font-normal whitespace-normal hover:bg-tile active:translate-y-0",
              doc.id === selectedId && "bg-blue-soft hover:bg-blue-soft",
            )}
          >
            <b className={cn("truncate font-semibold", doc.id === selectedId ? "text-blue-deep" : "text-ink")}>{doc.title}</b>
            <span className="text-right text-xs whitespace-nowrap text-ink-3">{doc.chunks} 块</span>
            <span className="col-span-2 truncate text-xs text-ink-3">
              {doc.stale && <span className="font-semibold text-warn">待更新 · </span>}
              {kindLabel(doc.kind)}
              {doc.lang !== "zh" && ` · ${doc.lang}`} · {doc.chars.toLocaleString()} 字
            </span>
          </Button>
        ))}
      </div>
    </section>
  );
}
