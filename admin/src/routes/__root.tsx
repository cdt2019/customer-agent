import { createRootRoute, Outlet, useRouterState } from "@tanstack/react-router";
import { Menu } from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Sidebar } from "@/components/shell/sidebar";
import { Button } from "@/components/ui/button";

export const Route = createRootRoute({ component: Shell });

// 和 Tailwind 的 md 断点一致：窄于它算手机，页面里用 max-md: 改成竖排
const PHONE = matchMedia("(width < 48rem)");

function usePhone() {
  return useSyncExternalStore(
    (onChange) => {
      PHONE.addEventListener("change", onChange);
      return () => PHONE.removeEventListener("change", onChange);
    },
    () => PHONE.matches,
  );
}

function Shell() {
  const phone = usePhone();
  // 窗口窄的时候菜单默认收起（docs/03 §3.1）
  const [folded, setFolded] = useState(() => window.innerWidth < 1240);
  const [drawer, setDrawer] = useState(false);
  const path = useRouterState({ select: (state) => state.location.pathname });
  useEffect(() => setDrawer(false), [path]);
  if (path === "/login") return <Outlet />;
  if (phone) {
    // 手机：顶上一条，菜单从左边拉出来，页面整页滚动
    return (
      <div className="h-full overflow-y-auto">
        <header className="sticky top-0 z-20 flex h-12 items-center gap-1.5 border-b border-hair bg-white/80 px-2 backdrop-blur-xl">
          <Button variant="ghost" size="icon" onClick={() => setDrawer(true)} aria-label="打开菜单" aria-expanded={drawer}>
            <Menu />
          </Button>
          <b className="text-[15px] font-bold tracking-tight">Customer Agent</b>
        </header>
        <Outlet />
        {drawer && (
          <div className="fixed inset-0 z-30 bg-ink/30" onClick={() => setDrawer(false)}>
            <div className="h-full w-[264px] bg-white" onClick={(event) => event.stopPropagation()}>
              <Sidebar folded={false} onToggle={() => setDrawer(false)} />
            </div>
          </div>
        )}
      </div>
    );
  }
  return (
    <div className="grid h-full grid-rows-[minmax(0,1fr)]" style={{ gridTemplateColumns: `${folded ? 58 : 232}px minmax(0, 1fr)` }}>
      <Sidebar folded={folded} onToggle={() => setFolded((value) => !value)} />
      <Outlet />
    </div>
  );
}
