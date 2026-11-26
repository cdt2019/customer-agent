/** 原文的一段：chunkId 为空是没进任何块的文字（比如标题行）。 */
export type Segment = { text: string; chunkId: number | null };

/**
 * 按块在原文里的位置把原文切成段，用来左右对照。
 * 块按顺序往后找；相邻块重叠的部分算在前一块。找不到的块（定长切块去掉了首尾空白以外不会发生）跳过。
 */
export function segmentsOf(markdown: string, chunks: { id: number; text: string }[]): Segment[] {
  const out: Segment[] = [];
  let shown = 0; // 原文已经输出到哪
  let from = 0; // 下一块从哪开始找
  for (const chunk of chunks) {
    const start = markdown.indexOf(chunk.text, from);
    if (start < 0) continue;
    const end = start + chunk.text.length;
    if (start > shown) out.push({ text: markdown.slice(shown, start), chunkId: null });
    if (end > shown) {
      out.push({ text: markdown.slice(Math.max(start, shown), end), chunkId: chunk.id });
      shown = end;
    }
    from = start + 1;
  }
  if (shown < markdown.length) out.push({ text: markdown.slice(shown), chunkId: null });
  return out;
}
