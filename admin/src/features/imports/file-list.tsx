import { Upload } from "lucide-react";
import { type DragEvent, useRef, useState } from "react";

import type { ImportFile } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export const STATUS: Record<string, { label: string; color: string }> = {
  queued: { label: "排队", color: "text-ink-3" },
  parsing: { label: "解析中", color: "text-blue" },
  pending: { label: "待确认", color: "text-warn" },
  confirmed: { label: "已确认", color: "text-up" },
  failed: { label: "失败", color: "text-down" },
};

const ACCEPT = ".md,.txt,.html,.docx,.pdf";

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function FileList({
  files,
  selectedId,
  uploading,
  onSelect,
  onFiles,
}: {
  files: ImportFile[];
  selectedId: number | null;
  uploading: boolean;
  onSelect: (id: number) => void;
  onFiles: (files: File[]) => void;
}) {
  const picker = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    onFiles([...event.dataTransfer.files]);
  };

  return (
    <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
      <Button
        variant="ghost"
        disabled={uploading}
        onClick={() => picker.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={cn(
          "m-3 block h-auto flex-none rounded-[18px] border-[1.5px] border-dashed border-blue/35 bg-blue-soft/40 px-3 py-4 text-center font-normal whitespace-normal hover:border-blue hover:bg-blue-soft active:translate-y-0",
          over && "border-blue bg-blue-soft",
        )}
      >
        <span className="bg-brand mx-auto mb-1.5 grid size-[38px] place-items-center rounded-[13px] text-white">
          <Upload className="size-[18px]" />
        </span>
        <b className="block font-semibold text-ink">{uploading ? "正在上传" : "拖入文件，或点击选择"}</b>
        <small className="text-xs text-ink-3">Markdown、TXT、HTML、Word、文字型 PDF，单个最大 50MB</small>
      </Button>
      <Input
        ref={picker}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        aria-label="选择文件"
        onChange={(event) => {
          onFiles([...(event.target.files ?? [])]);
          event.target.value = "";
        }}
      />
      <div className="min-h-0 flex-1 overflow-auto px-2 pb-2">
        {files.length === 0 && <p className="px-2.5 py-2 text-ink-3">这个知识库还没有导入过文件。</p>}
        {files.map((file) => {
          const status = STATUS[file.status];
          return (
            <Button
              key={file.id}
              variant="ghost"
              aria-current={file.id === selectedId}
              onClick={() => onSelect(file.id)}
              className={cn(
                "mb-0.5 grid h-auto w-full grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-x-2.5 rounded-[14px] px-2.5 py-2 text-left font-normal whitespace-normal hover:bg-tile active:translate-y-0",
                file.id === selectedId && "bg-blue-soft hover:bg-blue-soft",
              )}
            >
              <span className="row-span-2 grid size-[34px] place-items-center rounded-[10px] bg-white text-[10px] font-bold text-blue uppercase shadow-sm">{file.suffix.slice(1)}</span>
              <b className="truncate font-semibold text-ink">{file.filename}</b>
              <span className={cn("row-span-2 text-xs font-semibold whitespace-nowrap", status.color)}>{status.label}</span>
              <small className="col-start-2 truncate text-xs text-ink-3">{formatSize(file.size)}</small>
            </Button>
          );
        })}
      </div>
    </section>
  );
}
