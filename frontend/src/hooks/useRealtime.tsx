import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getTokens, wsUrl } from "../api/client";
import { useAuth } from "../store/auth";

export interface Toast { id: number; title: string; body: string }
const ToastCtx = createContext<{ toasts: Toast[]; push: (t: Omit<Toast, "id">) => void; dismiss: (id: number) => void }>({
  toasts: [], push: () => undefined, dismiss: () => undefined,
});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((x) => [...x.slice(-3), { ...t, id }]);
    setTimeout(() => dismiss(id), 6000);
  }, [dismiss]);
  return <ToastCtx.Provider value={{ toasts, push, dismiss }}>{children}</ToastCtx.Provider>;
}

/** Keeps one WebSocket open for the signed-in user; every server event refreshes the relevant queries. */
export function useRealtime(): { connected: boolean } {
  const { user } = useAuth();
  const qc = useQueryClient();
  const { push } = useToast();
  const [connected, setConnected] = useState(false);
  const retry = useRef(0);

  useEffect(() => {
    if (!user) return;
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      const tok = getTokens();
      if (!tok || closed) return;
      ws = new WebSocket(wsUrl(tok.access_token));
      ws.onopen = () => { retry.current = 0; setConnected(true); };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.event === "connected" || msg.event === "pong") return;
          push({ title: msg.title ?? "Update", body: msg.body ?? "" });
          for (const key of ["notifications", "listings", "pickups", "route", "matches", "impact"]) void qc.invalidateQueries({ queryKey: [key] });
        } catch { /* ignore malformed frames */ }
      };
      ws.onclose = () => {
        setConnected(false);
        if (closed) return;
        retry.current += 1;
        timer = setTimeout(connect, Math.min(15000, 1000 * 2 ** retry.current));
      };
    };
    connect();
    const ping = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), 25000);
    return () => { closed = true; clearInterval(ping); if (timer) clearTimeout(timer); ws?.close(); };
  }, [user, qc, push]);

  return { connected };
}
