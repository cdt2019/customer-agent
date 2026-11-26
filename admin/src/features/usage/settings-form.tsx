import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";

import { api, errorText, type ServiceState } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";

type Draft = Omit<ServiceState, "used_today" | "open_now">;
type NumberField = Exclude<keyof Draft, "enabled">;

function Row({ label, note, children }: { label: string; note?: string; children: ReactNode }) {
  return (
    <label className="flex items-center gap-2.5 border-b border-hair py-2">
      <span className="flex-1 text-[13.5px]">
        {label}
        {note && <small className="block text-[11.5px] text-ink-3">{note}</small>}
      </span>
      {children}
    </label>
  );
}

function NumberBox({ value, unit, step, onChange }: { value: number; unit: string; step?: number; onChange: (value: number) => void }) {
  return (
    <span className="inline-flex h-8 items-center gap-1 rounded-[10px] bg-tile px-2.5 focus-within:ring-2 focus-within:ring-ring">
      <input
        type="number"
        min={0}
        step={step ?? 1}
        value={Number.isNaN(value) ? "" : value}
        onChange={(event) => onChange(event.target.valueAsNumber)}
        className="w-[104px] bg-transparent text-right font-num outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
      />
      <em className="text-xs text-ink-3 not-italic">{unit}</em>
    </span>
  );
}

function pick({ used_today: _, open_now: __, ...draft }: ServiceState): Draft {
  return draft;
}

/** 总开关、限额和单价。改完点保存，立刻生效。 */
export function SettingsForm({ state }: { state: ServiceState }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>(() => pick(state));
  const save = useMutation({
    mutationFn: async (body: Draft) => {
      const { data, error } = await api.PUT("/api/service-settings", { body });
      if (error) throw error;
      return data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["service-settings"], data);
      queryClient.invalidateQueries({ queryKey: ["usage"] });
    },
  });
  const set = (field: NumberField) => (value: number) => setDraft({ ...draft, [field]: value });
  const invalid = Object.entries(draft).some(([key, value]) => key !== "enabled" && (typeof value !== "number" || Number.isNaN(value) || value < 0));
  const changed = (Object.keys(draft) as (keyof Draft)[]).some((key) => draft[key] !== state[key]);

  return (
    <section aria-label="开关和限额" className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl bg-card shadow-card">
      <div className="flex-none px-4.5 pt-3.5 pb-1">
        <b className="block text-[15px]">开关和限额</b>
        <small className="text-xs text-ink-3">保存后立刻生效</small>
      </div>
      <form
        className="min-h-0 flex-1 overflow-auto px-4.5 pb-4"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate(draft);
        }}
      >
        <Row label="总开关" note="关掉后聊天窗只显示联系方式">
          <Switch checked={draft.enabled} onCheckedChange={(enabled) => setDraft({ ...draft, enabled })} aria-label="总开关" />
        </Row>
        <Row label="每个访客每天">
          <NumberBox value={draft.per_visitor_day} unit="轮" onChange={set("per_visitor_day")} />
        </Row>
        <Row label="每个会话">
          <NumberBox value={draft.per_conversation} unit="轮" onChange={set("per_conversation")} />
        </Row>
        <Row label="买家一条消息最多" note="聊天窗按它提示，超过的不收">
          <NumberBox value={draft.max_message_chars} unit="字" onChange={set("max_message_chars")} />
        </Row>
        <Row label="全店每天上限" note="到了自动暂停，并提醒店主一次">
          <NumberBox value={draft.daily_token_limit} unit="token" step={100_000} onChange={set("daily_token_limit")} />
        </Row>
        <h3 className="mt-3.5 mb-0.5 text-[13px] font-semibold">
          单价（每百万 token，元）
          <small className="block text-[11.5px] font-normal text-ink-3">只用来估算花费，按模型供应商官网填</small>
        </h3>
        <Row label="输入">
          <NumberBox value={draft.price_input} unit="元" step={0.01} onChange={set("price_input")} />
        </Row>
        <Row label="输入（命中缓存）">
          <NumberBox value={draft.price_cached_input} unit="元" step={0.01} onChange={set("price_cached_input")} />
        </Row>
        <Row label="输出">
          <NumberBox value={draft.price_output} unit="元" step={0.01} onChange={set("price_output")} />
        </Row>
        <p className="my-2.5 text-[11.5px] text-ink-3">有的供应商分高峰和空闲时段，这里不分；按高峰价填，估出来偏高一些。</p>
        <div className="flex items-center gap-2.5">
          <Button type="submit" disabled={!changed || invalid || save.isPending}>
            保存
          </Button>
          {invalid && <span className="text-xs text-down">数字不能为空或小于 0</span>}
          {save.isError && <span className="text-xs text-down">{errorText(save.error)}</span>}
          {save.isSuccess && !changed && <span className="text-xs text-up">已保存</span>}
        </div>
      </form>
    </section>
  );
}
