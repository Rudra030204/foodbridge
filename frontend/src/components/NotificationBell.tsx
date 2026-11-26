import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Notice } from "../api/types";
import { fmtDateTime } from "../lib/format";

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ unread: number; items: Notice[] }>("/notifications"),
    refetchInterval: 30000,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["notifications"] });
  const read = useMutation({ mutationFn: (id: number) => api(`/notifications/${id}/read`, { method: "POST" }), onSuccess: refresh });
  const readAll = useMutation({ mutationFn: () => api("/notifications/read-all", { method: "POST" }), onSuccess: refresh });
  const unread = data?.unread ?? 0;

  return (
    <div className="relative">
      <button className="btn-outline btn-sm relative" aria-label={`Notifications, ${unread} unread`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span aria-hidden>🔔</span>
        {unread > 0 && (
          <span data-testid="unread-count" className="absolute -right-1.5 -top-1.5 rounded-full bg-red-600 px-1.5 text-[10px] font-bold text-white">{unread}</span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-80 max-w-[90vw] rounded-xl border border-stone-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-stone-100 px-3 py-2">
            <p className="text-sm font-semibold">Notifications</p>
            <button className="text-xs text-brand-700 hover:underline disabled:opacity-40" disabled={unread === 0} onClick={() => readAll.mutate()}>Mark all read</button>
          </div>
          <ul className="max-h-80 divide-y divide-stone-100 overflow-y-auto">
            {(data?.items ?? []).length === 0 && <li className="px-3 py-6 text-center text-sm text-stone-500">Nothing yet.</li>}
            {(data?.items ?? []).map((n) => (
              <li key={n.id} className={`cursor-pointer px-3 py-2 text-sm hover:bg-stone-50 ${n.is_read ? "text-stone-500" : "bg-brand-50/50"}`} onClick={() => !n.is_read && read.mutate(n.id)}>
                <p className="font-medium text-stone-800">{n.title}</p>
                <p className="text-xs">{n.body}</p>
                <p className="mt-0.5 text-[11px] text-stone-400">{fmtDateTime(n.created_at)}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
