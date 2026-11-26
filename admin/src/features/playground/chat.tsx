import { ArrowRightToLine, ChevronRight, PanelLeftClose, Send, Sparkles } from "lucide-react";
import { type KeyboardEvent, useEffect, useRef, useState } from "react";

import type { Recipe } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Toggle } from "@/components/ui/toggle";
import { cn } from "@/lib/utils";

import type { Turn } from "./model";

/** 把回答里的 [1][2] 变成能点的出处编号。 */
function AnswerText({ text, onCite }: { text: string; onCite: (n: number) => void }) {
  return (
    <>
      {text.split("\n").filter(Boolean).map((line, row) => (
        <p key={row} className="mb-2 leading-7 last:mb-0">
          {line.split(/(\[\d+\])/).map((part, col) => {
            const cite = /^\[(\d+)\]$/.exec(part);
            if (!cite) return part;
            return (
              <Button
                key={col}
                size="icon-xs"
                variant="secondary"
                className="mx-0.5 size-[18px] rounded-md bg-blue-soft align-[1px] text-[11px] font-bold text-blue hover:bg-blue hover:text-white"
                aria-label={`出处 ${cite[1]}`}
                onClick={(event) => {
                  event.stopPropagation();
                  onCite(Number(cite[1]));
                }}
              >
                {cite[1]}
              </Button>
            );
          })}
        </p>
      ))}
    </>
  );
}

function TurnView({ turn, selected, onSelect, onCite }: { turn: Turn; selected: boolean; onSelect: () => void; onCite: (n: number) => void }) {
  const { result, error } = turn;
  return (
    <div className="flex flex-col gap-3.5">
      <div className="bg-brand max-w-[82%] self-end rounded-[20px_20px_6px_20px] px-4 py-2.5 break-words whitespace-pre-wrap text-white shadow-blue">{turn.question}</div>
      <div className="grid grid-cols-[36px_minmax(0,1fr)] gap-2.5">
        <div className="grid size-9 place-items-center rounded-xl bg-white text-blue shadow-card">
          <Sparkles className="size-[19px]" />
        </div>
        <div
          className={cn("rounded-[6px_22px_22px_22px] border-[1.5px] border-transparent bg-white px-4 pt-3 pb-2.5 shadow-card transition-colors", selected && "border-blue/40")}
          onClick={result ? onSelect : undefined}
        >
          {!result && !error && (
            <span className="inline-flex items-center gap-2 py-1 text-ink-3">
              <span className="size-1.5 animate-pulse rounded-full bg-blue" />
              正在检索和回答
            </span>
          )}
          {error && <p className="text-down">{error}</p>}
          {result?.answer && <AnswerText text={result.answer.text} onCite={onCite} />}
          {result && !result.answer && <p className="text-ink-2">{result.answer_error ? `回答没有生成：${result.answer_error}` : "这次只做了检索，没有生成回答。"}</p>}
          {result && (
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 border-t border-hair pt-2 text-xs text-ink-3">
              <span>检索 {result.retrieval_ms} ms</span>
              {result.answer && <span>· 回答 {(result.answer.ms / 1000).toFixed(1)} s</span>}
              <span>· 用了 {result.selected.length} 块</span>
              <Button variant="ghost" size="xs" className="ml-auto text-blue" onClick={onSelect}>
                检索过程
                <ChevronRight />
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const SWITCHES: { key: "expand" | "dense" | "keyword"; label: string }[] = [
  { key: "expand", label: "改写" },
  { key: "dense", label: "语义" },
  { key: "keyword", label: "关键词" },
];
const RERANK_TOP = 10; // 重排前 10 块就拿到全部收益（docs/05 §12.1）

export function Chat({
  initialDraft,
  intro,
  examples,
  turns,
  selectedId,
  busy,
  canSend,
  recipe,
  onRecipe,
  onSend,
  onSelect,
  onCite,
  folded,
  onFold,
}: {
  initialDraft: string;
  intro: { name: string; detail: string } | null;
  examples: string[];
  turns: Turn[];
  selectedId: number | null;
  busy: boolean;
  canSend: boolean;
  recipe: Recipe;
  onRecipe: (recipe: Recipe) => void;
  onSend: (question: string) => void;
  onSelect: (id: number) => void;
  onCite: (turnId: number, n: number) => void;
  folded: boolean;
  onFold: () => void;
}) {
  const [draft, setDraft] = useState(initialDraft);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [turns.length]);

  const send = () => {
    const question = draft.trim();
    if (!question || busy || !canSend) return;
    setDraft("");
    onSend(question);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  };

  if (folded) {
    return (
      <section className="flex h-full flex-col items-center py-3.5">
        <Button variant="outline" size="icon" className="border-0 bg-white/70 text-ink-2" onClick={onFold} aria-label="展开对话">
          <ArrowRightToLine />
        </Button>
      </section>
    );
  }

  return (
    <section className="flex h-full min-w-0 flex-col px-4 py-3.5">
      <div className="mx-1 mb-2.5 flex items-center gap-2">
        <h1 className="mr-auto text-[22px] leading-tight font-bold tracking-tight whitespace-nowrap">检索测试台</h1>
        <Button variant="outline" size="icon" className="border-0 bg-white/70 text-ink-2" onClick={onFold} aria-label="收起对话">
          <PanelLeftClose />
        </Button>
      </div>

      <div ref={scroller} className="min-h-0 flex-1 overflow-auto px-1.5 pt-2 pb-3.5">
        {turns.length === 0 ? (
          <div className="flex flex-col gap-2.5">
            <div className="rounded-[20px] bg-white px-4 py-3.5 shadow-card">
              <span className="mb-1 flex items-center gap-2 text-[15px] font-bold">
                <span className="bg-brand grid size-7 shrink-0 place-items-center rounded-[9px] text-white">
                  <Sparkles className="size-4" />
                </span>
                {intro?.name ?? "检索测试台"}
              </span>
              <p className="text-[13px] leading-relaxed text-ink-2">{intro?.detail}</p>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-2">问一个买家可能问的问题，右边会显示每一步找到了什么。</p>
            </div>
            {examples.length > 0 && <h2 className="mx-1 mt-1 text-xs font-semibold text-ink-3">试试这些问题</h2>}
            {examples.map((example) => (
              <Button
                key={example}
                variant="ghost"
                className="flex h-auto w-full items-center justify-between gap-2 rounded-[14px] bg-white px-3.5 py-2.5 text-left text-[13.5px] font-normal whitespace-normal text-blue-deep shadow-sm hover:bg-blue-soft active:translate-y-0"
                onClick={() => {
                  setDraft(example);
                  input.current?.focus();
                }}
              >
                <span className="min-w-0">{example}</span>
                <ChevronRight className="shrink-0 text-ink-3" />
              </Button>
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-3.5">
            {turns.map((turn) => (
              <TurnView key={turn.id} turn={turn} selected={turn.id === selectedId} onSelect={() => onSelect(turn.id)} onCite={(n) => onCite(turn.id, n)} />
            ))}
          </div>
        )}
      </div>

      <div className="rounded-3xl bg-white py-2.5 pr-3 pl-4 shadow-[0_2px_4px_rgb(38_48_110/0.05),0_18px_40px_-16px_rgb(38_48_110/0.32)]">
        <Textarea
          ref={input}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          maxLength={500}
          aria-label="问题"
          placeholder={canSend ? "问一个买家可能问的问题" : "先在右边选一个索引版本"}
          className="h-12 min-h-0 resize-none rounded-lg border-0 bg-transparent px-1 py-0.5 text-[15px] shadow-none focus-visible:ring-0 dark:bg-transparent"
        />
        <div className="flex items-center gap-1.5">
          {SWITCHES.map(({ key, label }) => (
            <Toggle
              key={key}
              size="sm"
              pressed={recipe[key]}
              onPressedChange={(pressed) => onRecipe({ ...recipe, [key]: pressed })}
              className="rounded-[11px] bg-tile px-2.5 text-[13px] text-ink-3 data-pressed:bg-blue-soft data-pressed:font-semibold data-pressed:text-blue"
            >
              {label}
            </Toggle>
          ))}
          <Toggle
            size="sm"
            pressed={recipe.rerank > 0}
            onPressedChange={(pressed) => onRecipe({ ...recipe, rerank: pressed ? RERANK_TOP : 0 })}
            className="rounded-[11px] bg-tile px-2.5 text-[13px] text-ink-3 data-pressed:bg-blue-soft data-pressed:font-semibold data-pressed:text-blue"
          >
            重排
          </Toggle>
          <Button size="icon-lg" className="bg-brand ml-auto size-[42px] rounded-[15px] shadow-blue" onClick={send} disabled={busy || !canSend || !draft.trim()} aria-label="发送">
            <Send />
          </Button>
        </div>
      </div>
    </section>
  );
}
