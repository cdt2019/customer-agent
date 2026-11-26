import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export const api = createClient<paths>();

/** 没登录或登录过期：去登录页，登录后回到原来的页面。 */
export function toLogin() {
  if (location.pathname !== "/login") location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
}

api.use({
  onResponse({ response }) {
    if (response.status === 401) toLogin();
  },
});

export type KnowledgeBase = components["schemas"]["KnowledgeBaseOut"];
export type IndexVersion = components["schemas"]["IndexOut"];
export type Recipe = components["schemas"]["RecipeIn"];
export type PlaygroundResult = components["schemas"]["PlaygroundOut"];
export type Stage = components["schemas"]["StageOut"];
export type ChunkInfo = components["schemas"]["ChunkOut"];

/** 接口报错时返回的说明文字。 */
export function errorText(error: unknown): string {
  const detail = (error as { detail?: unknown })?.detail;
  return typeof detail === "string" ? detail : "请求没有成功，稍后再试";
}

export type EvalRun = components["schemas"]["RunOut"];
export type KindScores = components["schemas"]["KindScores"];
export type CompareRow = components["schemas"]["CompareRow"];

export type DatasetInfo = components["schemas"]["DatasetOut"];
export type DocumentRow = components["schemas"]["DocumentRow"];
export type DocumentDetail = components["schemas"]["DocumentDetail"];

export type ChunkPreview = components["schemas"]["PreviewOut"];
export type ChunkStats = components["schemas"]["ChunkStats"];
export type ChunkSettings = Pick<components["schemas"]["PreviewIn"], "chunker" | "size" | "overlap">;

export type TaskInfo = components["schemas"]["TaskOut"];

export type ImportFile = components["schemas"]["FileRow"];
export type ImportDetail = components["schemas"]["FileDetail"];

export type ChatList = components["schemas"]["ChatList"];
export type ChatRow = components["schemas"]["ChatRow"];
export type ChatDetail = components["schemas"]["ChatDetail"];
export type ChatMessage = components["schemas"]["ChatMessageOut"];
export type HandoffRow = components["schemas"]["HandoffRecord"];
export type Usage = components["schemas"]["UsageOut"];
export type ServiceState = components["schemas"]["ServiceStateOut"];
export type WidgetSettings = components["schemas"]["WidgetSettings"];
