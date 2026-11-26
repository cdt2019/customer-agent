// 聊天窗本体：头部、消息、输入框。悬浮版和整页版共用，外壳不同。

import { ChevronRight, Expand, Headset, ImagePlus, MessageCircle, Plus, Send, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from "react";
import { Answer } from "./Answer";
import type { Source } from "./api";
import type { Lang, Texts } from "./i18n";
import type { Chat, Message } from "./useChat";

type Props = { chat: Chat; t: Texts; lang: Lang; mode: "float" | "page"; onClose?: () => void };


export function ChatPanel({ chat, t, lang, mode, onClose }: Props) {
  const body = useRef<HTMLDivElement>(null);
  const { config, messages, handoff, needsEmail, error, busy } = chat;
  const name = config?.name ?? "";
  const paused = config?.enabled === false;

  useEffect(() => {
    body.current?.scrollTo({ top: body.current.scrollHeight });
  }, [messages, handoff, needsEmail, error]);

  return (
    <div className={`flex h-full flex-col overflow-hidden bg-shell ${mode === "float" ? "rounded-3xl shadow-panel max-[520px]:rounded-none" : "rounded-3xl shadow-card"}`}>
      <header className="head-bg flex flex-none items-center gap-2.5 py-3 pr-3 pl-3.5 text-on-brand">
        <div className="grid size-9 flex-none place-items-center rounded-lg bg-white text-brand-ink">
          <Sparkles size={19} />
        </div>
        <div className="min-w-0 flex-1 leading-tight">
          <b className="flex min-w-0 gap-1 text-md">
            <span className="truncate max-[420px]:hidden">{name}</span>
            <span className="flex-none">{t.assistant}</span>
          </b>
          <span className="block truncate text-xs opacity-90">{t.subtitle}</span>
        </div>
        {!paused && (
          <>
            <HeadButton onClick={() => chat.requestHuman()} label={t.human} disabled={busy}>
              <Headset size={15} />
              {t.human}
            </HeadButton>
            <HeadButton onClick={chat.reset} label={t.newChat} icon disabled={busy}>
              <Plus size={16} />
            </HeadButton>
          </>
        )}
        {mode === "float" && config?.page_url && (
          <a href={config.page_url} aria-label={t.expand} title={t.expand} className="grid size-8 place-items-center rounded-md bg-on-brand/12 hover:bg-on-brand/20">
            <Expand size={15} />
          </a>
        )}
        {onClose && (
          <HeadButton onClick={onClose} label={t.close} icon>
            <X size={16} />
          </HeadButton>
        )}
      </header>

      <div ref={body} className={`flex min-h-0 flex-1 flex-col gap-2.5 overflow-auto pt-3.5 pb-2 ${mode === "page" ? "px-5.5" : "px-3.5"}`}>
        {paused && (
          <div className="rounded-2xl bg-white px-4 py-3.5 shadow-bubble" role="status">
            <b className="mb-0.5 block text-lg">{t.pausedTitle}</b>
            <p className="m-0 text-sm text-ink-2">
              {t.paused}
              <br />
              {config?.contacts}
            </p>
          </div>
        )}
        {!paused && messages.length === 0 && <Welcome chat={chat} t={t} lang={lang} grid={mode === "page"} />}
        {messages.map((m) =>
          m.role === "user" ? (
            <Mine key={m.key} message={m} src={chat.imageSrc(m)} t={t} />
          ) : m.role === "staff" ? (
            <StaffSays key={m.key} text={m.text} t={t} />
          ) : m.role === "system" ? (
            <p key={m.key} className="m-0 self-center text-center text-xs text-ink-3">
              {m.text}
            </p>
          ) : (
            <Reply key={m.key} message={m} chat={chat} t={t} />
          ),
        )}
        {handoff && chat.status !== "staff" && <HandoffCard chat={chat} t={t} />}
        {needsEmail && !handoff && <EmailForm chat={chat} t={t} />}
        {error && (
          <div className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn-ink" role="alert">
            {t.errors[error]}
            {config && <div className="mt-0.5">{t.contacts(config.contacts)}</div>}
          </div>
        )}
      </div>

      {chat.status === "staff" && (
        <div className="mx-2.5 flex-none rounded-lg bg-brand-soft px-3 py-1.5 text-center text-xs text-brand-ink" role="status">
          {t.staffHere}
        </div>
      )}
      {!paused && config && <Composer chat={chat} t={t} wide={mode === "page"} max={config.max_message_chars} />}
      <div className="flex-none px-3 pb-2 text-center text-[11px] text-ink-3">{t.footer}</div>
    </div>
  );
}

function HeadButton({ children, onClick, label, icon, disabled }: { children: React.ReactNode; onClick: () => void; label: string; icon?: boolean; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={`inline-flex h-8 flex-none cursor-pointer items-center justify-center gap-1 rounded-md bg-on-brand/12 text-[12.5px] font-semibold whitespace-nowrap text-on-brand hover:bg-on-brand/20 disabled:cursor-default disabled:opacity-60 ${icon ? "w-8" : "px-2.5"}`}
    >
      {children}
    </button>
  );
}

function Welcome({ chat, t, lang, grid }: { chat: Chat; t: Texts; lang: Lang; grid: boolean }) {
  const suggestions = chat.config?.suggestions[lang] ?? [];
  return (
    <>
      <div className="rounded-2xl bg-white px-4 py-3.5 shadow-bubble">
        <b className="mb-0.5 block text-lg">{t.helloTitle}</b>
        <p className="m-0 text-sm text-ink-2">{t.hello}</p>
      </div>
      <div className={grid ? "grid grid-cols-2 gap-1.5 max-[640px]:grid-cols-1" : "flex flex-col gap-1.5"}>
        {suggestions.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => chat.send(s)}
            className="flex cursor-pointer items-center justify-between gap-2 rounded-lg bg-white px-3.5 py-2 text-left text-[13.5px] text-brand-ink shadow-bubble hover:bg-brand-soft"
          >
            <span>{s}</span>
            <ChevronRight size={14} className="flex-none text-ink-3" />
          </button>
        ))}
      </div>
    </>
  );
}

/** 同一篇文章的几段合成一个出处：[1][4] 标题。 */
function byDocument(sources: Source[]): { document: string; title: string; numbers: number[] }[] {
  const merged = new Map<string, { document: string; title: string; numbers: number[] }>();
  for (const s of sources) {
    const entry = merged.get(s.document) ?? { document: s.document, title: s.title, numbers: [] };
    entry.numbers.push(s.n);
    merged.set(s.document, entry);
  }
  return [...merged.values()];
}

function StaffSays({ text, t }: { text: string; t: Texts }) {
  return (
    <div className="max-w-[94%] self-start rounded-[5px_16px_16px_16px] bg-brand-soft px-3.5 pt-1.5 pb-2 break-words whitespace-pre-wrap shadow-bubble">
      <small className="block text-[11px] font-semibold text-brand-ink">{t.staff}</small>
      {text}
    </div>
  );
}

function Mine({ message, src, t }: { message: Message; src: string | null; t: Texts }) {
  if (src) {
    // 买家发的图：点开看大图
    return (
      <a href={src} target="_blank" rel="noreferrer" className="max-w-[70%] self-end overflow-hidden rounded-[16px_16px_5px_16px] shadow-bubble">
        <img src={src} alt={t.picture} className={`block max-h-60 w-auto ${message.image ? "" : "opacity-60"}`} />
      </a>
    );
  }
  return <div className="brand-bg max-w-[84%] self-end rounded-[16px_16px_5px_16px] px-3.5 py-2 break-words whitespace-pre-wrap text-on-brand">{message.text}</div>;
}

function Reply({ message, chat, t }: { message: Message; chat: Chat; t: Texts }) {
  const waiting = message.pending && !message.text;
  const link = chat.config?.source_url;
  return (
    <div className="w-full max-w-[94%] self-start rounded-[5px_16px_16px_16px] bg-white px-3.5 pt-2.5 pb-2 break-words shadow-bubble">
      {waiting || message.tool ? (
        <div className="flex items-center gap-2 py-0.5 text-sm text-ink-3">
          <span className="inline-flex gap-[3px]" aria-hidden>
            {[0, 1, 2].map((i) => (
              <i key={i} className="size-[5px] animate-hop rounded-full bg-brand/60" style={{ animationDelay: `${i * 0.15}s` }} />
            ))}
          </span>
          {(message.tool && t.tools[message.tool]) || t.thinking}
        </div>
      ) : null}
      {message.text && <Answer text={message.text} />}
      {!!message.sources?.length && (
        <div className="mt-1 mb-0.5 flex flex-wrap gap-1.5" aria-label={t.sources}>
          {byDocument(message.sources).map(({ document, title, numbers }) => (
            <a
              key={document}
              href={link ? link.replace("{document}", document) : undefined}
              className="rounded-sm bg-brand-soft px-2 text-xs leading-[1.8] text-brand-ink no-underline hover:underline"
            >
              {numbers.map((n) => `[${n}]`).join("")} {title}
            </a>
          ))}
        </div>
      )}
      {message.id && !message.pending && (
        <div className="mt-1 flex gap-1">
          <Vote on={message.feedback === 1} onClick={() => chat.rate(message, true)} label={t.useful} />
          <Vote on={message.feedback === 0} onClick={() => chat.rate(message, false)} label={t.useless} />
        </div>
      )}
    </div>
  );
}

function Vote({ on, onClick, label }: { on: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className={`h-6 cursor-pointer rounded-sm px-2 text-xs ${on ? "bg-brand-soft font-semibold text-brand-ink" : "text-ink-3 hover:bg-tile hover:text-ink-2"}`}
    >
      {label}
    </button>
  );
}

function HandoffCard({ chat, t }: { chat: Chat; t: Texts }) {
  const h = chat.handoff!;
  const hours = h.reply_hours || chat.config?.reply_hours || 0;
  return (
    <div className="rounded-lg bg-up-soft px-3 py-2 text-sm text-up-ink" role="status">
      <b className="block">{h.ticket_no ? t.handedTicket(h.ticket_no) : t.handedRecord}</b>
      {h.ticket_no ? t.replyTicket(hours) : h.email ? t.replyEmail(hours, h.email) : t.replyHere(hours)}
      {h.away_message && <div className="mt-1 rounded-md bg-warn-soft px-2 py-1 text-warn-ink">{h.away_message}</div>}
      {chat.config && <div className="mt-0.5 text-xs opacity-90">{t.contacts(chat.config.contacts)}</div>}
    </div>
  );
}

function EmailForm({ chat, t }: { chat: Chat; t: Texts }) {
  const [email, setEmail] = useState("");
  const [bad, setBad] = useState(false);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return setBad(true);
    setBad(false);
    chat.requestHuman(email.trim());
  }
  return (
    <form onSubmit={submit} className="rounded-2xl bg-white px-3.5 py-2.5 text-sm shadow-bubble">
      <p className="m-0">{t.emailAsk}</p>
      <div className="mt-1.5 flex gap-1.5">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-label="Email"
          placeholder="you@example.com"
          className="h-[34px] min-w-0 flex-1 rounded-md border border-line bg-white px-2.5 outline-none focus:border-brand"
        />
        <button type="submit" disabled={chat.busy} className="h-[34px] cursor-pointer rounded-md bg-brand px-3 font-semibold whitespace-nowrap text-on-brand disabled:opacity-60">
          {t.emailSubmit}
        </button>
      </div>
      {bad && <div className="mt-1 text-xs text-down">{t.emailBad}</div>}
    </form>
  );
}

function Composer({ chat, t, wide, max }: { chat: Chat; t: Texts; wide: boolean; max: number }) {
  const [text, setText] = useState("");
  const over = text.length > max;
  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (over || chat.busy || !text.trim()) return;
    chat.send(text);
    setText("");
  }
  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }
  // 直接粘贴截图就发出去
  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const file = [...event.clipboardData.files].find((f) => f.type.startsWith("image/"));
    if (file && !chat.busy) {
      event.preventDefault();
      chat.sendImage(file);
    }
  }
  const picker = useRef<HTMLInputElement>(null);
  return (
    <form onSubmit={submit} className={`flex flex-none items-end gap-1.5 rounded-xl bg-white py-1.5 pr-1.5 pl-1.5 shadow-input ${wide ? "mx-4.5 mt-1 mb-1.5" : "mx-2.5 mt-1 mb-1.5"}`}>
      <button type="button" aria-label={t.sendImage} title={t.sendImage} disabled={chat.busy} onClick={() => picker.current?.click()} className="grid size-9 flex-none cursor-pointer place-items-center rounded-lg text-ink-3 hover:bg-brand-soft hover:text-brand-ink disabled:opacity-60">
        <ImagePlus size={18} />
      </button>
      <input
        ref={picker}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) chat.sendImage(file);
          e.target.value = "";
        }}
      />
      <div className="min-w-0 flex-1">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          onPaste={onPaste}
          rows={1}
          aria-label={t.input}
          placeholder={chat.status === "staff" ? t.toStaff : t.placeholder}
          className="block max-h-28 min-h-9 w-full resize-none border-0 bg-transparent py-[7px] leading-[22px] outline-none [field-sizing:content] placeholder:text-ink-3"
        />
        {text.length > max * 0.8 && <div className={`pb-0.5 text-[11px] ${over ? "text-down" : "text-ink-3"}`}>{t.tooLong(text.length, max)}</div>}
      </div>
      <button type="submit" aria-label={t.send} disabled={chat.busy || over} className="brand-bg grid size-9 flex-none cursor-pointer place-items-center rounded-lg text-on-brand disabled:opacity-60">
        <Send size={17} />
      </button>
    </form>
  );
}

export function Launcher({ open, onClick, t }: { open: boolean; onClick: () => void; t: Texts }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={t.open}
      aria-expanded={open}
      className={`brand-bg fixed right-6 bottom-6 z-[2147483000] grid size-[58px] cursor-pointer place-items-center rounded-2xl text-on-brand shadow-brand hover:-translate-y-0.5 ${open ? "max-[520px]:hidden" : ""}`}
    >
      {open ? <X size={25} /> : <MessageCircle size={25} />}
    </button>
  );
}
