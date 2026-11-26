// 聊天窗只认接入方提供的这组接口（docs/02 §5.4）。浏览器不直接连客服服务。

import type { ErrorCode } from "./i18n";

export type Config = {
  enabled: boolean; // 关着（或客服服务连不上）时只显示联系方式
  max_message_chars: number; // 一条消息最多几个字
  name: string;
  contacts: string;
  reply_hours: number;
  suggestions: Record<string, string[]>;
  page_url: string;
  source_url: string;
  theme?: Theme;
};

/** 接入方的主题色，聊天窗按它上色。 */
export type Theme = { brand: string; brand_deep: string; brand_soft: string; brand_ink: string; on_brand: string };

export type Source = { n: number; title: string; document: string };

export type Handoff = { kind: "ticket" | "record"; ticket_no: string | null; email: string | null; reply_hours: number; away_message: string | null };

export type Picture = { id: number; width: number; height: number };

export type StoredMessage = { id: number; role: string; text: string; sources: Source[]; feedback: number | null; image: Picture | null };

export type History = { id: string; status: string; messages: StoredMessage[]; handoff: Handoff | null };

export type StreamEvent =
  | { type: "user"; data: { text: string; message_id: number; image?: Picture } }
  | { type: "status"; data: { tool: string } }
  | { type: "text"; data: { text: string } }
  | { type: "clear"; data: Record<string, never> }
  | { type: "handoff"; data: Handoff }
  | { type: "done"; data: { message_id: number; sources: Source[]; staff?: boolean } } // staff：客服在接，这句只发给客服，没有 AI 回答
  | { type: "error"; data: { code: string } };

export class ChatError extends Error {
  constructor(readonly code: ErrorCode) {
    super(code);
  }
}

function errorFor(status: number): ChatError {
  if (status === 429) return new ChatError("limit");
  if (status >= 500) return new ChatError("unavailable");
  return new ChatError("failed");
}

export function client(base: string) {
  async function call<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(base + path, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...init });
    } catch {
      throw new ChatError("offline");
    }
    if (!response.ok) throw Object.assign(errorFor(response.status), { status: response.status });
    return response.status === 204 ? (undefined as T) : response.json();
  }

  /** 发一个请求，回答按 SSE 一段段回来。 */
  async function stream(path: string, init: RequestInit, onEvent: (event: StreamEvent) => void, errors: (status: number) => ChatError): Promise<void> {
    let response: Response;
    try {
      response = await fetch(base + path, { method: "POST", credentials: "same-origin", ...init });
    } catch {
      throw new ChatError("offline");
    }
    if (!response.ok || !response.body) throw Object.assign(errors(response.status), { status: response.status });
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += value;
        let end: number;
        while ((end = buffer.indexOf("\n\n")) >= 0) {
          const block = buffer.slice(0, end);
          buffer = buffer.slice(end + 2);
          const type = /^event: (.*)$/m.exec(block)?.[1];
          const data = /^data: (.*)$/m.exec(block)?.[1];
          if (type && data) onEvent({ type, data: JSON.parse(data) } as StreamEvent);
        }
      }
    } catch {
      throw new ChatError("offline");
    }
  }

  return {
    config: () => call<Config>("/config"),
    create: () => call<{ id: string }>("/conversations", { method: "POST" }),
    /** 取历史；after 是已有的最后一条消息编号，只取比它新的（转人工期间定时拉客服的回复）。 */
    history: (id: string, after = 0) => call<History>(`/conversations/${id}${after ? `?after=${after}` : ""}`),
    handoff: (id: string, email = "") =>
      call<{ status: "handoff" | "needs_email"; handoff: Handoff | null }>(`/conversations/${id}/handoff`, { method: "POST", body: JSON.stringify({ email }) }),
    feedback: (id: string, messageId: number, useful: boolean | null) =>
      call<void>(`/conversations/${id}/messages/${messageId}/feedback`, { method: "POST", body: JSON.stringify({ useful }) }),

    /** 发一条消息。 */
    send: (id: string, text: string, onEvent: (event: StreamEvent) => void) =>
      stream(`/conversations/${id}/messages`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) }, onEvent, errorFor),

    /** 发一张图片（docs/09），回答和发文字一样。 */
    sendImage: (id: string, file: File, onEvent: (event: StreamEvent) => void) => {
      const form = new FormData();
      form.append("file", file);
      const errors = (status: number) => (status === 422 ? new ChatError("badImage") : status === 429 ? new ChatError("tooManyImages") : errorFor(status));
      return stream(`/conversations/${id}/images`, { body: form }, onEvent, errors);
    },

    imageUrl: (id: string, imageId: number) => `${base}/conversations/${id}/images/${imageId}`,
  };
}

export type Client = ReturnType<typeof client>;
