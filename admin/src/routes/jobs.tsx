import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";

import { api, errorText, type TaskInfo } from "@/api/client";
import { Metric } from "@/components/shell/metric";
import { Picker } from "@/components/shell/picker";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TaskCard } from "@/features/jobs/task-card";

export const Route = createFileRoute("/jobs")({ component: Jobs });

const TABS = [
  { key: "all", label: "全部" },
  { key: "running", label: "进行中" },
  { key: "failed", label: "失败" },
  { key: "done", label: "完成" },
  { key: "cancelled", label: "已取消" },
];

function Jobs() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("all");
  const [kb, setKb] = useState("all");
  const overview = useQuery({
    queryKey: ["tasks"],
    queryFn: async () => (await api.GET("/api/tasks")).data ?? null,
    refetchInterval: (query) => (query.state.data?.tasks.some((task) => task.status === "running") ? 1000 : 4000),
  });
  const all = overview.data?.tasks ?? [];
  const kbs = [...new Set(all.map((task) => task.knowledge_base))];
  const tasks = all.filter((task) => kb === "all" || task.knowledge_base === kb);
  const count = (status: string) => tasks.filter((task) => task.status === status).length;
  const shown = tasks.filter((task) => tab === "all" || task.status === tab);
  const running = all.some((task) => task.status === "running");

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["dataset"] });
    queryClient.invalidateQueries({ queryKey: ["eval-runs"] });
  };
  const cancel = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/tasks/cancel");
      if (error) throw new Error(errorText(error));
    },
    onSuccess: refresh,
  });
  const retry = useMutation({
    mutationFn: async (task: TaskInfo) => {
      const { error } =
        task.type === "index"
          ? await api.POST("/api/tasks/index/{job_id}/retry", { params: { path: { job_id: task.id } } })
          : await api.POST("/api/tasks/eval/{run_id}/retry", { params: { path: { run_id: task.id } } });
      if (error) throw new Error(errorText(error));
    },
    onSuccess: refresh,
  });
  const failure = cancel.error ?? retry.error;

  return (
    <main className="flex h-full min-w-0 flex-col px-5 py-3.5 max-md:h-auto max-md:px-3">
      <div className="mx-0.5 mb-3 flex flex-none items-center gap-2 max-md:flex-wrap">
        <h1 className="text-[22px] leading-tight font-bold tracking-tight whitespace-nowrap">任务</h1>
        <span className="ml-1 text-[13px] text-ink-2">同步、建索引和评测，同一时间只跑一个</span>
        <Picker label="知识库" value={kb} placeholder="" options={[{ value: "all", label: "全部" }, ...kbs.map((name) => ({ value: name, label: name }))]} onChange={setKb} />
        <span className="flex-1" />
        {failure && <span className="text-[13px] text-down">{failure.message}</span>}
        <Button className="h-[34px] rounded-xl px-4 text-[13px]" nativeButton={false} render={<Link to="/imports" />}>
          导入文件
        </Button>
      </div>

      {overview.data && (
        <div className="mb-3 grid h-[72px] flex-none grid-cols-5 gap-2.5 max-md:grid-flow-col max-md:grid-cols-none max-md:auto-cols-[40%] max-md:overflow-x-auto max-md:[scrollbar-width:none]">
          <Metric label="进行中" value={String(count("running"))} unit="个" hero />
          <Metric label="失败" value={String(count("failed"))} unit="个" />
          <Metric label="完成" value={String(count("done"))} unit="个" />
          <Metric label="运行在" value={overview.data.device.replace("NVIDIA GeForce ", "")} />
          <Metric label="向量化速度" value={overview.data.embed_speed === null ? "—" : String(overview.data.embed_speed)} unit={overview.data.embed_speed === null ? undefined : "块/秒"} />
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
        <Tabs value={tab} onValueChange={(value) => setTab(String(value))} className="flex-none border-b border-hair px-5 pt-2.5 max-md:overflow-x-auto max-md:px-3 max-md:[scrollbar-width:none]">
          <TabsList variant="line" className="h-auto gap-6 p-0 max-md:gap-4">
            {TABS.map(({ key, label }) => (
              <TabsTrigger key={key} value={key} className="px-0.5 pb-2.5 text-[15px] text-ink-3 data-active:font-semibold data-active:text-blue">
                {label} {key === "all" ? tasks.length : count(key)}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="min-h-0 flex-1 overflow-auto px-3 pt-3 pb-1">
          {shown.length === 0 && <p className="px-2 py-3 text-ink-3">{overview.isPending ? "正在读取" : "这里没有任务"}</p>}
          {shown.map((task) => (
            <TaskCard
              key={`${task.type}-${task.id}`}
              task={task}
              busy={running || retry.isPending}
              onCancel={() => cancel.mutate()}
              onRetry={() => retry.mutate(task)}
            />
          ))}
        </div>
      </div>
    </main>
  );
}
