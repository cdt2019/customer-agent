import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, errorText, type WidgetSettings } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const LANGS = [
  { key: "zh", label: "中文", placeholder: "付款后多久能收到？\n礼品卡怎么兑换？" },
  { key: "en", label: "English", placeholder: "How long does delivery take?\nHow do I redeem a gift card?" },
];
const MAX = 6;

const lines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

/** 聊天窗打开时给买家点的常见问题，一行一条，按语言分开。 */
export function SuggestionsForm({ state }: { state: WidgetSettings }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(() => Object.fromEntries(LANGS.map(({ key }) => [key, (state.suggestions[key] ?? []).join("\n")])));
  const parsed = Object.fromEntries(LANGS.map(({ key }) => [key, lines(draft[key])]));
  const save = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.PUT("/api/widget-settings", { body: { suggestions: parsed } });
      if (error) throw error;
      return data;
    },
    onSuccess: (data) => queryClient.setQueryData(["widget-settings"], data),
  });
  const tooMany = LANGS.some(({ key }) => parsed[key].length > MAX);
  const changed = LANGS.some(({ key }) => parsed[key].join("\n") !== (state.suggestions[key] ?? []).join("\n"));

  return (
    <section className="flex min-w-0 flex-col rounded-3xl bg-card px-5 py-4 shadow-card">
      <h2 className="text-[15px] font-bold">聊天窗的常见问题</h2>
      <p className="mb-3 text-xs text-ink-3">买家打开聊天窗时可以直接点的问题，一行一条，每种语言最多 {MAX} 条、每条 60 字以内。按买家的页面语言显示，保存后下次打开聊天窗就生效。</p>
      <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
        {LANGS.map(({ key, label, placeholder }) => (
          <label key={key} className="flex flex-col gap-1.5">
            <span className="flex items-center text-[13px] text-ink-2">
              {label}
              <span className="flex-1" />
              <small className={parsed[key].length > MAX ? "text-down" : "text-ink-3"}>
                {parsed[key].length} / {MAX} 条
              </small>
            </span>
            <Textarea
              value={draft[key]}
              onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
              placeholder={placeholder}
              className="min-h-[150px] resize-none rounded-xl border-0 bg-tile text-[13.5px] shadow-none"
            />
          </label>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2.5">
        <Button className="rounded-xl px-5" disabled={!changed || tooMany || save.isPending} onClick={() => save.mutate()}>
          保存
        </Button>
        {save.isError && <span className="text-xs text-down">{errorText(save.error)}</span>}
        {save.isSuccess && !changed && <span className="text-xs text-up">已保存</span>}
      </div>
    </section>
  );
}
