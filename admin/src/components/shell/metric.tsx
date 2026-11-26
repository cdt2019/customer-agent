import { cn } from "@/lib/utils";

/** 指标卡：上面小字说明，下面大号数字加单位。hero 是这一排里最重要的那张。 */
export function Metric({ label, value, unit, hero }: { label: string; value: string; unit?: string; hero?: boolean }) {
  return (
    <div className={cn("flex min-w-0 flex-col justify-center overflow-hidden rounded-[18px] px-3.5", hero ? "bg-hero text-white shadow-blue" : "bg-card shadow-card")}>
      <span className={cn("text-[11.5px] leading-snug whitespace-nowrap", hero ? "text-white/85" : "text-ink-3")}>{label}</span>
      <b className="truncate font-num text-[19px] leading-tight font-bold">
        {value}
        {unit && <small className={cn("ml-0.5 text-[11px] font-medium", hero ? "text-white/85" : "text-ink-2")}>{unit}</small>}
      </b>
    </div>
  );
}
