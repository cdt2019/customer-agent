import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, errorText, type KnowledgeBase, type Recipe } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

// 默认配方：语义 + 关键词（docs/05 §12.5）
const DEFAULT_RECIPE: Recipe = { dense: true, keyword: true, expand: false, rerank: 0, candidates: 20, limit: 5 };
const RERANK_TOP = 10;

function Row({ label, note, checked, onChange }: { label: string; note?: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="flex items-center gap-3 border-b border-hair py-2 last:border-0">
      <span className="min-w-0 flex-1">
        {label}
        {note && <small className="block text-xs text-ink-3">{note}</small>}
      </span>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
    </label>
  );
}

export function NewRunDialog({ kb, disabled, onStarted }: { kb: KnowledgeBase; disabled: boolean; onStarted: () => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<number | null>(null);
  const [recipe, setRecipe] = useState(DEFAULT_RECIPE);
  const [answers, setAnswers] = useState(false);
  const indexId = kb.indexes.some((index) => index.id === chosen) ? chosen! : (kb.indexes[0]?.id ?? null);

  const start = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/evals/runs", { body: { index_id: indexId!, recipe, answers } });
      if (!data) throw new Error(errorText(error));
      return data;
    },
    onSuccess: () => {
      setOpen(false);
      onStarted();
      queryClient.invalidateQueries({ queryKey: ["eval-runs", kb.id] });
    },
  });

  return (
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); start.reset(); }}>
      <DialogTrigger render={<Button className="bg-brand h-9 rounded-xl px-5 font-semibold shadow-blue" disabled={disabled || kb.questions === 0} />}>
        {disabled ? "评测进行中" : "运行评测"}
      </DialogTrigger>
      <DialogContent className="rounded-2xl sm:max-w-md">
        <DialogHeader>
          <DialogTitle>运行评测</DialogTitle>
          <DialogDescription>
            {kb.name} 的 {kb.questions} 道题，在后台跑，可以离开这一页。
          </DialogDescription>
        </DialogHeader>
        <Select value={indexId === null ? null : String(indexId)} onValueChange={(value) => setChosen(Number(value))} items={kb.indexes.map((index) => ({ value: String(index.id), label: `索引 ${index.name} · ${index.embed_model}` }))}>
          <SelectTrigger className="w-full rounded-xl" aria-label="索引版本">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {kb.indexes.map((index) => (
              <SelectItem key={index.id} value={String(index.id)}>
                索引 {index.name} · {index.embed_model}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div>
          <Row label="语义检索" checked={recipe.dense} onChange={(dense) => setRecipe({ ...recipe, dense })} />
          <Row label="关键词检索" checked={recipe.keyword} onChange={(keyword) => setRecipe({ ...recipe, keyword })} />
          <Row label="改写问题" note="每题多调用一次模型" checked={recipe.expand} onChange={(expand) => setRecipe({ ...recipe, expand })} />
          <Row label={`重排前 ${RERANK_TOP} 块`} checked={recipe.rerank > 0} onChange={(on) => setRecipe({ ...recipe, rerank: on ? RERANK_TOP : 0 })} />
          <Row label="生成回答并判分" note="每题调用两次模型，会产生花费" checked={answers} onChange={setAnswers} />
        </div>
        {start.error && <p className="text-[13px] text-down">{start.error.message}</p>}
        <DialogFooter>
          <Button className="bg-brand rounded-xl px-5" disabled={start.isPending || indexId === null || !(recipe.dense || recipe.keyword)} onClick={() => start.mutate()}>
            {start.isPending ? "发起中" : "开始"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
