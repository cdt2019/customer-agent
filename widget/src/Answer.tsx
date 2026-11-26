// 把模型的回答排成段落、列表、加粗和引用编号。只认这几样，不用 innerHTML。

import type { ReactNode } from "react";

function inline(text: string, key: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[\d+\])/g).map((part, i) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong>;
    if (/^`[^`]+`$/.test(part)) return <code key={`${key}-${i}`} className="rounded-sm bg-tile px-1 text-[12.5px]">{part.slice(1, -1)}</code>;
    if (/^\[\d+\]$/.test(part)) return <sup key={`${key}-${i}`} className="mx-px text-[10px] font-semibold text-brand-ink">{part}</sup>;
    return part;
  });
}

export function Answer({ text }: { text: string }) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, b) => {
        const lines = block.split("\n");
        const isList = lines.every((line) => /^\s*([-*]|\d+\.)\s+/.test(line));
        if (isList) {
          const ordered = /^\s*\d+\./.test(lines[0]);
          const items = lines.map((line, i) => <li key={i}>{inline(line.replace(/^\s*([-*]|\d+\.)\s+/, ""), `${b}-${i}`)}</li>);
          return ordered ? (
            <ol key={b} className="mb-1 list-decimal pl-5">{items}</ol>
          ) : (
            <ul key={b} className="mb-1 list-disc pl-5">{items}</ul>
          );
        }
        return (
          <p key={b} className="mb-1 leading-[1.7] whitespace-pre-wrap">
            {inline(block, String(b))}
          </p>
        );
      })}
    </>
  );
}
