// 聊天窗的状态：会话、消息、转人工、错误。界面只读这里，不直接调接口。
// 转了人工或客服在接时，页面在前台就每 POLL_MS 拉一次新消息（docs/07 §3）。

import { useCallback, useEffect, useRef, useState } from "react";
import { ChatError, type Client, type Config, type Handoff, type Picture, type Source, type StoredMessage, type StreamEvent } from "./api";
import type { ErrorCode } from "./i18n";

export type Message = {
  key: string;
  role: "user" | "assistant" | "staff" | "system"; // staff 客服的话；system 给买家看的说明，比如客服交还给 AI
  text: string;
  id?: number;
  sources?: Source[];
  feedback?: number | null;
  tool?: string | null; // 正在调的工具
  pending?: boolean;
  image?: Picture | null; // 买家发的图（docs/09）
  preview?: string; // 图片还没传完时先显示本地的
};

const storageKey = (base: string) => `customer-agent:conversation:${base}`;
const POLL_MS = 5000;
const SHOWN = new Set(["user", "assistant", "staff", "system"]);

function fromStored(m: StoredMessage): Message {
  return { key: nextKey(), role: m.role as Message["role"], text: m.text, id: m.id, sources: m.sources, feedback: m.feedback, image: m.image };
}
let counter = 0;
const nextKey = () => `m${++counter}`;

export function useChat(api: Client, base: string) {
  const [config, setConfig] = useState<Config | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [handoff, setHandoff] = useState<Handoff | null>(null);
  const [needsEmail, setNeedsEmail] = useState(false);
  const [error, setError] = useState<ErrorCode | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("open"); // open / handoff / staff
  const conversation = useRef<string | null>(localStorage.getItem(storageKey(base)));
  const lastId = useRef(0); // 已经有的最后一条消息编号，拉新消息从它往后

  const forget = useCallback(() => {
    conversation.current = null;
    localStorage.removeItem(storageKey(base));
  }, [base]);

  useEffect(() => {
    api.config().then(setConfig, () => setError("unavailable"));
    const id = conversation.current;
    if (!id) return;
    api.history(id).then(
      (history) => {
        setMessages(history.messages.filter((m) => SHOWN.has(m.role)).map(fromStored));
        lastId.current = Math.max(0, ...history.messages.map((m) => m.id));
        setHandoff(history.handoff);
        setStatus(history.status);
      },
      (failure: ChatError & { status?: number }) => {
        if (failure.status === 404 || failure.status === 403) forget(); // 换了身份或会话已清理：开新的
      },
    );
  }, [api, forget]);

  // 转了人工或客服在接：定时拉客服的新回复。买家自己发的话已经在界面上，只补客服的话和说明。
  useEffect(() => {
    if (status === "open") return;
    let stopped = false;
    async function pull() {
      const id = conversation.current;
      if (!id || document.hidden || stopped) return;
      try {
        const history = await api.history(id, lastId.current);
        if (stopped || !history.messages.length) return setStatus(history.status);
        lastId.current = Math.max(lastId.current, ...history.messages.map((m) => m.id));
        const fresh = history.messages.filter((m) => m.role === "staff" || m.role === "system").map(fromStored);
        if (fresh.length) setMessages((list) => [...list, ...fresh]);
        setStatus(history.status);
      } catch {
        // 一次没拉到不要紧，下一轮再拉
      }
    }
    const timer = setInterval(pull, POLL_MS);
    document.addEventListener("visibilitychange", pull);
    return () => {
      stopped = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", pull);
    };
  }, [api, status]);

  async function ensureConversation(): Promise<string> {
    if (conversation.current) return conversation.current;
    const { id } = await api.create();
    conversation.current = id;
    localStorage.setItem(storageKey(base), id);
    return id;
  }

  function patchLast(change: (message: Message) => Message) {
    setMessages((list) => list.map((m, i) => (i === list.length - 1 ? change(m) : m)));
  }

  function onEvent(event: StreamEvent) {
    switch (event.type) {
      case "user": {
        // 服务端打码后的原话（发图片时还有存好的图），替换掉刚才显示的那条
        const mine = event.data;
        setMessages((list) => {
          const at = list.map((m) => m.role).lastIndexOf("user");
          return list.map((m, i) => (i === at ? { ...m, text: mine.text, id: mine.message_id, image: mine.image ?? m.image } : m));
        });
        break;
      }
      case "status":
        patchLast((m) => ({ ...m, tool: event.data.tool }));
        break;
      case "text":
        patchLast((m) => ({ ...m, text: m.text + event.data.text, tool: null }));
        break;
      case "clear":
        patchLast((m) => ({ ...m, text: "" }));
        break;
      case "handoff":
        setHandoff(event.data);
        setNeedsEmail(false);
        setStatus((now) => (now === "staff" ? now : "handoff"));
        break;
      case "done":
        lastId.current = Math.max(lastId.current, event.data.message_id);
        if (event.data.staff) {
          // 客服在接：这句只发给客服，撤掉等 AI 回答的空泡
          setMessages((list) => list.filter((m) => !m.pending));
          setStatus("staff");
          break;
        }
        patchLast((m) => ({ ...m, id: event.data.message_id, sources: event.data.sources, pending: false, tool: null, feedback: null }));
        break;
      case "error":
        setError("failed");
        break;
    }
  }

  /** 买家的一条（文字或图片）先显示出来，再发出去收回答。 */
  async function deliver(mine: Message, go: (id: string) => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    // 客服在接时不会有 AI 回答，不放「正在想」的空泡
    setMessages((list) => [...list, mine, ...(status === "staff" ? [] : [{ key: nextKey(), role: "assistant" as const, text: "", pending: true }])]);
    try {
      await go(await ensureConversation());
    } catch (failure) {
      setError(failure instanceof ChatError ? failure.code : "failed");
      if (mine.preview) setMessages((list) => list.filter((m) => m.key !== mine.key)); // 没收下的图片不留
    } finally {
      // 没收到 done 的半截回答去掉，免得留一个空泡
      setMessages((list) => list.filter((m) => !(m.pending && !m.text)).map((m) => ({ ...m, pending: false, tool: null })));
      setBusy(false);
    }
  }

  async function send(text: string) {
    const clean = text.trim();
    if (clean) await deliver({ key: nextKey(), role: "user", text: clean }, (id) => api.send(id, clean, onEvent));
  }

  async function sendImage(file: File) {
    await deliver({ key: nextKey(), role: "user", text: "", preview: URL.createObjectURL(file) }, (id) => api.sendImage(id, file, onEvent));
  }

  /** 图片地址：已存好的从接入方取，没传完的用本地预览。 */
  function imageSrc(message: Message): string | null {
    if (message.image && conversation.current) return api.imageUrl(conversation.current, message.image.id);
    return message.preview ?? null;
  }

  async function requestHuman(email = "") {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const id = await ensureConversation();
      const result = await api.handoff(id, email);
      setNeedsEmail(result.status === "needs_email");
      if (result.handoff) {
        setHandoff(result.handoff);
        setStatus((now) => (now === "staff" ? now : "handoff"));
      }
    } catch (failure) {
      setError(failure instanceof ChatError ? failure.code : "failed");
    } finally {
      setBusy(false);
    }
  }

  async function rate(message: Message, useful: boolean) {
    if (!message.id || !conversation.current) return;
    const value = message.feedback === Number(useful) ? null : useful;
    setMessages((list) => list.map((m) => (m.key === message.key ? { ...m, feedback: value === null ? null : Number(value) } : m)));
    await api.feedback(conversation.current, message.id, value).catch(() => undefined);
  }

  function reset() {
    if (busy) return;
    forget();
    setMessages([]);
    setHandoff(null);
    setNeedsEmail(false);
    setError(null);
    setStatus("open");
    lastId.current = 0;
  }

  return { config, messages, handoff, needsEmail, error, busy, status, send, sendImage, imageSrc, requestHuman, rate, reset };
}

export type Chat = ReturnType<typeof useChat>;
