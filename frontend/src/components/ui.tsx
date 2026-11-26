import { ReactNode } from "react";
import { ApiError } from "../api/client";
import { useCountdown } from "../hooks/useCountdown";
import { formatDuration, label, URGENCY_CLASS, urgencyOf } from "../lib/format";
import type { MatchInfo } from "../api/types";

export function Spinner({ text = "Loading..." }: { text?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-10 text-sm text-stone-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-stone-300 border-t-brand-600" />
      {text}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof ApiError ? error.message : error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-medium">Could not load this.</p>
      <p className="mt-0.5">{msg}</p>
      {retry && <button className="btn-outline btn-sm mt-3" onClick={retry}>Try again</button>}
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-stone-300 bg-white px-6 py-10 text-center">
      <p className="font-medium text-stone-700">{title}</p>
      {hint && <p className="mt-1 text-sm text-stone-500">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "error" | "success" | "warn"; children: ReactNode }) {
  const c = { info: "bg-sky-50 text-sky-800 border-sky-200", error: "bg-red-50 text-red-800 border-red-200",
    success: "bg-emerald-50 text-emerald-800 border-emerald-200", warn: "bg-amber-50 text-amber-900 border-amber-200" }[kind];
  return <div role={kind === "error" ? "alert" : "status"} className={`rounded-lg border px-3 py-2 text-sm ${c}`}>{children}</div>;
}

/** Live countdown to a safe-until time, colour-coded green / amber / red. */
export function Countdown({ safeUntil, className = "" }: { safeUntil: string; className?: string }) {
  const { ms, expired } = useCountdown(safeUntil);
  const u = urgencyOf(ms);
  return (
    <span data-testid="countdown" data-urgency={expired ? "red" : u}
      className={`inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-sm font-semibold tabular-nums ${URGENCY_CLASS[expired ? "red" : u]} ${className}`}>
      {expired ? "Expired" : formatDuration(ms)}
    </span>
  );
}

const STATUS_STYLE: Record<string, string> = {
  open: "bg-sky-100 text-sky-800", claimed: "bg-indigo-100 text-indigo-800", assigned: "bg-violet-100 text-violet-800",
  picked_up: "bg-amber-100 text-amber-800", delivered: "bg-emerald-100 text-emerald-800", diverted: "bg-orange-100 text-orange-800",
  expired: "bg-stone-200 text-stone-700", cancelled: "bg-stone-200 text-stone-700", failed: "bg-red-100 text-red-800",
  offered: "bg-sky-100 text-sky-800", pending_assignment: "bg-stone-200 text-stone-700", en_route: "bg-violet-100 text-violet-800",
};
export const StatusBadge = ({ status }: { status: string }) => (
  <span className={`badge ${STATUS_STYLE[status] ?? "bg-stone-100 text-stone-700"}`}>{label(status)}</span>
);

const STEPS = ["open", "claimed", "assigned", "picked_up", "delivered"] as const;
export function StatusTimeline({ status }: { status: string }) {
  if (["expired", "cancelled"].includes(status))
    return <p className="text-sm text-stone-500">This listing is <b>{status}</b>.</p>;
  const at = status === "diverted" ? 1 : STEPS.indexOf(status as (typeof STEPS)[number]);
  return (
    <ol className="flex items-center gap-1 text-xs" aria-label="Status timeline">
      {STEPS.map((s, i) => (
        <li key={s} className="flex flex-1 items-center gap-1">
          <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${i <= at ? "bg-brand-600 text-white" : "bg-stone-200 text-stone-500"}`}>{i < at ? "✓" : i + 1}</span>
          <span className={`hidden truncate sm:inline ${i <= at ? "font-medium text-stone-800" : "text-stone-400"}`}>{label(s)}</span>
          {i < STEPS.length - 1 && <span className={`h-px flex-1 ${i < at ? "bg-brand-600" : "bg-stone-200"}`} />}
        </li>
      ))}
    </ol>
  );
}

const WEIGHTS = { distance: 0.3, time: 0.3, capacity: 0.2, preference: 0.05, history: 0.15 };
/** "Why this NGO was ranked": each component bar with its weight. */
export function ScoreBars({ match }: { match: MatchInfo }) {
  return (
    <div className="space-y-1.5 text-xs">
      <p className="font-medium text-stone-700">Match score {(match.score * 100).toFixed(0)} / 100 · rank #{match.rank} · {match.distance_km.toFixed(1)} km</p>
      {(Object.keys(WEIGHTS) as (keyof typeof WEIGHTS)[]).map((k) => (
        <div key={k} className="flex items-center gap-2">
          <span className="w-16 capitalize text-stone-500">{k}</span>
          <div className="h-1.5 flex-1 rounded-full bg-stone-200"><div className="h-1.5 rounded-full bg-brand-600" style={{ width: `${Math.round(match.components[k] * 100)}%` }} /></div>
          <span className="w-20 text-right tabular-nums text-stone-500">{(match.components[k] * 100).toFixed(0)}% × {WEIGHTS[k]}</span>
        </div>
      ))}
    </div>
  );
}

export function Stat({ title, value, hint }: { title: string; value: ReactNode; hint?: string }) {
  return (
    <div className="card">
      <p className="text-xs font-medium uppercase tracking-wide text-stone-500">{title}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-stone-900">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-stone-500">{hint}</p>}
    </div>
  );
}
