import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api, errorText } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const Route = createFileRoute("/login")({
  validateSearch: (search: Record<string, unknown>) => ({ next: typeof search.next === "string" ? search.next : undefined }),
  component: Login,
});

function Login() {
  const { next } = Route.useSearch();
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const { error: failure } = await api.POST("/api/login", { body: { username, password } });
    setBusy(false);
    if (failure) return setError(errorText(failure));
    // 只回到站内地址，不跟着参数跳到别的网站
    navigate({ to: next?.startsWith("/") && !next.startsWith("//") ? next : "/playground" });
  }

  return (
    <main className="grid h-full place-items-center p-6">
      <form onSubmit={submit} className="w-full max-w-[360px] rounded-3xl bg-white p-7 shadow-card">
        <div className="mb-5 flex items-center gap-2.5">
          <div className="bg-brand grid size-[34px] place-items-center rounded-[11px] text-white shadow-blue">
            <Sparkles className="size-[18px]" />
          </div>
          <div>
            <b className="block text-[17px] leading-tight">Customer Agent</b>
            <small className="text-ink-3">管理后台</small>
          </div>
        </div>
        <label className="mb-3 block text-[13px] text-ink-2">
          账号
          <Input className="mt-1 h-10" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label className="mb-4 block text-[13px] text-ink-2">
          密码
          <Input className="mt-1 h-10" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" autoFocus />
        </label>
        {error && (
          <p className="mb-3 text-[13px] text-down" role="alert">
            {error}
          </p>
        )}
        <Button type="submit" className="h-10 w-full" disabled={busy || !password}>
          {busy ? "登录中" : "登录"}
        </Button>
      </form>
    </main>
  );
}
