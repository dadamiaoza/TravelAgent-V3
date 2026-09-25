import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type DemoUser = { id: string; display_name: string };
type DemoSession = { demo_auth: boolean; user: DemoUser | null };

type Phase = "loading" | "hidden" | "out" | "in";

export default function DemoAccount({
  showLogin = true,
  align = "end",
}: {
  showLogin?: boolean;
  align?: "start" | "end";
}) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [name, setName] = useState("演示用户");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    api
      .get<DemoSession>("/auth/me")
      .then((session) => {
        if (!session.demo_auth) {
          setPhase("hidden");
          return;
        }
        if (session.user) {
          setName(session.user.display_name);
          setPhase("in");
        } else {
          setPhase("out");
        }
      })
      .catch(() => setPhase("hidden"));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function login() {
    setBusy(true);
    try {
      const session = await api.post<DemoSession>("/auth/demo/login", {});
      if (session.user) setName(session.user.display_name);
      setPhase("in");
      window.location.reload();
    } catch {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    try {
      await api.post<void>("/auth/logout", {});
      setPhase("out");
      window.location.reload();
    } catch {
      setBusy(false);
    }
  }

  if (phase === "loading" || phase === "hidden") return null;
  if (phase === "out" && !showLogin) return null;

  if (phase === "out") {
    return (
      <div className={`flex flex-col gap-1 ${align === "start" ? "items-start" : "items-end"}`}>
        <button
          type="button"
          onClick={login}
          disabled={busy}
          className="rounded-full bg-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
        >
          {busy ? "正在进入…" : "演示登录"}
        </button>
        <p className={`max-w-[14rem] text-[11px] text-ink-tertiary ${align === "start" ? "text-left" : "text-right"}`}>
          演示账号，不会发送邮件
        </p>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 rounded-full border border-line-tertiary bg-elevated py-1 pl-1 pr-1.5">
      <span
        aria-hidden
        className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-xs font-medium text-white"
      >
        演
      </span>
      <span className="text-sm font-medium text-ink">{name}</span>
      <button
        type="button"
        onClick={logout}
        disabled={busy}
        className="rounded-full px-2 py-1 text-xs text-ink-secondary hover:bg-chrome disabled:opacity-60"
      >
        退出
      </button>
    </div>
  );
}
