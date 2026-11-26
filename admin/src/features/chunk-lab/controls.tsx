import type { ChunkSettings } from "@/api/client";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const HINT: Record<ChunkSettings["chunker"], string> = {
  heading: "按小标题分段，太长再按句子切，表格尽量不切开。适合帮助文章。",
  fixed: "不管结构，按字数切。作为对照，实测比按标题差很多。",
};

function Field({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (value: number) => void }) {
  return (
    <div className="mb-4">
      <div className="mb-2 flex justify-between text-[13px] text-ink-2">
        {label}
        <b className="font-num text-ink">{value} 字</b>
      </div>
      <Slider aria-label={label} value={[value]} min={min} max={max} step={step} onValueChange={(next) => onChange(Array.isArray(next) ? next[0] : next)} />
    </div>
  );
}

export function Controls({ settings, onChange }: { settings: ChunkSettings; onChange: (settings: ChunkSettings) => void }) {
  const maxOverlap = Math.min(300, Math.floor(settings.size / 20) * 10);
  return (
    <div className="mt-4">
      <span className="mb-1.5 block text-[13px] text-ink-2">策略</span>
      <Tabs value={settings.chunker} onValueChange={(value) => onChange({ ...settings, chunker: value as ChunkSettings["chunker"] })}>
        <TabsList className="w-full rounded-[11px] bg-chip">
          <TabsTrigger value="heading" className="rounded-lg text-[13px]">按标题</TabsTrigger>
          <TabsTrigger value="fixed" className="rounded-lg text-[13px]">定长</TabsTrigger>
        </TabsList>
      </Tabs>
      <p className="mt-1.5 mb-4 text-xs leading-relaxed text-ink-3">{HINT[settings.chunker]}</p>
      <Field
        label="块大小"
        value={settings.size}
        min={100}
        max={1200}
        step={20}
        onChange={(size) => onChange({ ...settings, size, overlap: Math.min(settings.overlap, Math.floor(size / 20) * 10) })}
      />
      <Field label="重叠" value={settings.overlap} min={0} max={maxOverlap} step={10} onChange={(overlap) => onChange({ ...settings, overlap })} />
      <p className="text-xs leading-relaxed text-ink-3">重叠是相邻块共用的字，预览里标黄。块大小不含重叠，所以一块最长是两者之和。长度按字符数算。</p>
    </div>
  );
}
