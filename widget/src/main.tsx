// 入口：CustomerAgent.mount({ base, mode, target, lang })。
// 也可以直接 <script src=".../widget.js" data-base="/api/chat" data-mode="float"> 自动挂一个悬浮窗。

import { useMemo, useState, type CSSProperties } from "react";
import { createRoot } from "react-dom/client";
import css from "./styles.css?inline";
import { client, type Theme } from "./api";
import { ChatPanel, Launcher } from "./ChatPanel";
import { texts, type Lang } from "./i18n";
import { useChat } from "./useChat";

type Options = { base?: string; mode?: "float" | "page"; target?: HTMLElement; lang?: Lang };

function App({ base, mode, lang }: { base: string; mode: "float" | "page"; lang: Lang }) {
  const api = useMemo(() => client(base), [base]);
  const chat = useChat(api, base);
  const [open, setOpen] = useState(false);
  const t = texts[lang];
  if (!chat.config && !chat.error) return null; // 等拿到接入方的主题色再画，免得先闪一下默认色
  const style = themeStyle(chat.config?.theme);
  if (mode === "page") {
    return (
      <div className="mx-auto h-full max-w-[820px]" style={style}>
        <ChatPanel chat={chat} t={t} lang={lang} mode="page" />
      </div>
    );
  }
  return (
    <div style={style}>
      {open && (
        <div className="fixed right-6 bottom-[94px] z-[2147483000] h-[min(640px,calc(100vh-170px))] w-[400px] max-[520px]:inset-0 max-[520px]:h-full max-[520px]:w-full">
          <ChatPanel chat={chat} t={t} lang={lang} mode="float" onClose={() => setOpen(false)} />
        </div>
      )}
      <Launcher open={open} onClick={() => setOpen(!open)} t={t} />
    </div>
  );
}

function themeStyle(theme?: Theme): CSSProperties | undefined {
  if (!theme) return undefined;
  return {
    "--color-brand": theme.brand,
    "--color-brand-deep": theme.brand_deep,
    "--color-brand-soft": theme.brand_soft,
    "--color-brand-ink": theme.brand_ink,
    "--color-on-brand": theme.on_brand,
  } as CSSProperties;
}

// Tailwind 4 用 @property 注册变量，这条规则在 Shadow DOM 里不生效，要放到页面上（只注册变量，不影响宿主样式）
let propertiesAdded = false;
function addProperties() {
  if (propertiesAdded) return;
  propertiesAdded = true;
  const rules = css.match(/@property[^{]+\{[^}]*\}/g);
  if (!rules) return;
  const style = document.createElement("style");
  style.textContent = rules.join("\n");
  document.head.append(style);
}

function pickLang(lang?: string): Lang {
  return (lang ?? document.documentElement.lang).toLowerCase().startsWith("en") ? "en" : "zh";
}

export function mount(options: Options = {}) {
  addProperties();
  const mode = options.mode ?? "float";
  const host = options.target ?? document.body.appendChild(document.createElement("div"));
  const shadow = host.shadowRoot ?? host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = css;
  const container = document.createElement("div");
  container.style.height = "100%";
  shadow.replaceChildren(style, container);
  const root = createRoot(container);
  root.render(<App base={options.base ?? "/api/chat"} mode={mode} lang={pickLang(options.lang)} />);
  return {
    unmount() {
      root.unmount();
      shadow.replaceChildren();
      if (!options.target) host.remove();
    },
  };
}

const script = document.currentScript as HTMLScriptElement | null;
if (script?.dataset.mode) {
  const auto = () => mount({ base: script.dataset.base, mode: script.dataset.mode as Options["mode"], lang: script.dataset.lang as Lang | undefined });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", auto);
  else auto();
}
