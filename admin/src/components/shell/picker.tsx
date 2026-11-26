import type { IndexVersion } from "@/api/client";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

type Option = { value: string; label: string; detail?: string; disabled?: boolean };

/** 页面顶部的选择器：「说明 + 当前值 + 下箭头」。选中后显示 label，展开时可以看 detail。 */
export function Picker({
  label,
  ariaLabel,
  value,
  placeholder,
  options,
  onChange,
  className,
}: {
  label: string;
  ariaLabel?: string;
  value: string | null;
  placeholder: string;
  options: Option[];
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={(next) => next !== null && onChange(next)} items={options.map(({ value: v, label: l }) => ({ value: v, label: l }))}>
      <SelectTrigger className={cn("h-[34px] rounded-xl border-0 bg-white/70 text-[13px] shadow-none", className)} aria-label={ariaLabel ?? label}>
        <span className="shrink-0 text-ink-2">{label}</span>
        <SelectValue placeholder={placeholder} className="min-w-0 truncate" />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
            {option.detail ? `${option.label} · ${option.detail}` : option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function indexDetail(index: IndexVersion): string {
  return `${index.chunker === "heading" ? "按标题" : "定长"} ${index.chunk_size} 字 · ${index.embed_model} · ${index.chunks} 块`;
}
