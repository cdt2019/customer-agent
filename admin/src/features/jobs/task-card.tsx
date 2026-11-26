import { Link } from "@tanstack/react-router";

import type { TaskInfo } from "@/api/client";
import { Button } from "@/components/ui/button";
import { when } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS: Record<string, { label: string; color: string }> = {
  running: { label: "进行中", color: "text-blue" },
  done: { label: "完成", color: "text-up" },
  failed: { label: "失败", color: "text-down" },
  cancelled: { label: "已取消", color: "text-ink-3" },
};

function duration(task: TaskInfo): string {
  if (!task.finished_at && task.status !== "running") return "";  // 早期的评测没记结束时间
  const end = task.finished_at ? new Date(task.finished_at).getTime() : Date.now();
  const seconds = Math.max(0, Math.round((end - new Date(task.started_at).getTime()) / 1000));
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

function Stage({ stage, status, current }: { stage: TaskInfo["stages"][number]; status: string; current: boolean }) {
  const percent = stage.total ? Math.round((stage.done / stage.total) * 100) : status === "done" ? 100 : 0;
  const complete = percent === 100;
  const tone = complete ? "up" : current && status === "failed" ? "down" : current && status === "running" ? "blue" : "muted";
  return (
    <div className="min-w-0">
      <span className={cn("flex justify-between gap-1 text-xs whitespace-nowrap", { up: "text-up", down: "font-semibold text-down", blue: "font-semibold text-blue", muted: "text-ink-3" }[tone])}>
        {stage.name}
        <em className="font-num not-italic">{stage.total ? `${stage.done} / ${stage.total}` : complete ? "无变化" : "—"}</em>
      </span>
      <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-chip">
        <i className={cn("block h-full rounded-full transition-[width] duration-300", { up: "bg-up", down: "bg-down", blue: "bg-brand", muted: "bg-ink-3" }[tone])} style={{ width: `${percent}%` }} />
      </span>
    </div>
  );
}

export function TaskCard({ task, busy, onCancel, onRetry }: { task: TaskInfo; busy: boolean; onCancel: () => void; onRetry: () => void }) {
  const status = STATUS[task.status] ?? { label: task.status, color: "text-ink-3" };
  const currentStage = task.stages.findIndex((stage) => stage.done < stage.total);
  return (
    <article className="mb-2.5 rounded-[18px] bg-tile px-4 py-3">
      <div className="flex min-w-0 items-center gap-2.5 max-md:flex-wrap max-md:gap-y-1">
        <b className="shrink-0 text-[15px] font-semibold">{task.title}</b>
        <span className="min-w-0 truncate text-xs text-ink-3">
          {task.knowledge_base} · 索引 {task.index_name}
        </span>
        <span className="flex-1" />
        <span className="shrink-0 text-xs whitespace-nowrap text-ink-3">
          {[when(task.started_at), duration(task)].filter(Boolean).join(" · ")}
        </span>
        <span className={cn("w-11 shrink-0 text-right text-xs font-semibold", status.color)}>{status.label}</span>
        {task.status === "running" && (
          <Button variant="secondary" size="sm" className="rounded-[10px] px-3" onClick={onCancel}>
            取消
          </Button>
        )}
        {task.retryable && (
          <Button variant="secondary" size="sm" className="rounded-[10px] px-3" disabled={busy} onClick={onRetry}>
            {task.type === "index" ? "接着做" : "重跑"}
          </Button>
        )}
        {task.type === "eval" && task.status === "done" && (
          <Button variant="ghost" size="sm" className="rounded-[10px] px-2 text-blue" nativeButton={false} render={<Link to="/evals" />}>
            看结果
          </Button>
        )}
        {task.type === "index" && task.status === "done" && (
          <Button variant="ghost" size="sm" className="rounded-[10px] px-2 text-blue" nativeButton={false} render={<Link to="/datasets" search={{ index: task.index_id }} />}>
            看数据
          </Button>
        )}
      </div>
      <div className="mt-2.5 grid gap-2" style={{ gridTemplateColumns: `repeat(${task.stages.length}, minmax(0, 1fr))` }}>
        {task.stages.map((stage, n) => (
          <Stage key={stage.name} stage={stage} status={task.status} current={n === currentStage} />
        ))}
      </div>
      {task.error && <p className="mt-2 rounded-[11px] bg-down/10 px-3 py-1.5 text-[12.5px] break-all text-down">{task.error}</p>}
    </article>
  );
}
