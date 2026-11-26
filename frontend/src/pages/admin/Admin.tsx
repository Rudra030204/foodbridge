import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { EmptyState, ErrorState, Notice, Spinner, Stat } from "../../components/ui";
import { fmtDateTime, label, pct } from "../../lib/format";

interface Row { id: number; name: string; email: string; role: string; is_verified: boolean; is_active: boolean; org_name: string | null; created_at: string; is_fallback_partner: boolean | null }
type Tab = "verify" | "users" | "rules" | "weights" | "reports" | "ops";
const TABS: [Tab, string][] = [["verify", "Verification"], ["users", "Users"], ["rules", "Safety rules"], ["weights", "Match weights"], ["reports", "Reports"], ["ops", "System & KPIs"]];

function useAction(invalidate: string[]) {
  const qc = useQueryClient();
  const [err, setErr] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => { setErr(null); invalidate.forEach((k) => void qc.invalidateQueries({ queryKey: [k] })); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : "Action failed."),
  });
  return { run: (fn: () => Promise<unknown>) => run.mutate(fn), err, pending: run.isPending };
}

function Verification() {
  const q = useQuery({ queryKey: ["admin", "verifications"], queryFn: () => api<{ items: Row[] }>("/admin/verifications") });
  const { run, err } = useAction(["admin"]);
  if (q.isLoading) return <Spinner />;
  if (q.isError) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const items = q.data!.items;
  return (
    <div className="space-y-3">
      {err && <Notice kind="error">{err}</Notice>}
      {items.length === 0 && <EmptyState title="Nobody is waiting for verification" />}
      {items.map((u) => (
        <div key={u.id} className="card flex flex-wrap items-center justify-between gap-3">
          <div><p className="font-medium">{u.org_name ?? u.name} <span className="badge bg-stone-100 text-stone-600">{u.role}</span></p><p className="text-xs text-stone-500">{u.email} · registered {fmtDateTime(u.created_at)}</p></div>
          <div className="flex gap-2">
            <button className="btn-primary btn-sm" onClick={() => run(() => api(`/admin/verifications/${u.id}`, { method: "POST", body: { approve: true } }))}>Approve</button>
            <button className="btn-danger btn-sm" onClick={() => window.confirm(`Reject ${u.email}? Their account will be deactivated.`) && run(() => api(`/admin/verifications/${u.id}`, { method: "POST", body: { approve: false } }))}>Reject</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function Users() {
  const [role, setRole] = useState("");
  const [search, setSearch] = useState("");
  const q = useQuery({ queryKey: ["admin", "users", role, search], queryFn: () => api<{ items: Row[] }>("/admin/users", { query: { role, q: search } }) });
  const { run, err } = useAction(["admin"]);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <select aria-label="Role filter" className="input w-40" value={role} onChange={(e) => setRole(e.target.value)}><option value="">All roles</option>{["donor", "ngo", "volunteer", "admin"].map((r) => <option key={r} value={r}>{r}</option>)}</select>
        <input aria-label="Search users" className="input w-64" placeholder="Search name or email" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      {err && <Notice kind="error">{err}</Notice>}
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} retry={() => q.refetch()} />}
      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-stone-50 text-xs uppercase text-stone-500"><tr><th className="px-3 py-2">User</th><th>Role</th><th>Status</th><th>Fallback</th><th /></tr></thead>
          <tbody>
            {q.data?.items.map((u) => (
              <tr key={u.id} className="border-t border-stone-100">
                <td className="px-3 py-2"><p className="font-medium">{u.org_name ?? u.name}</p><p className="text-xs text-stone-500">{u.email}</p></td>
                <td>{u.role}</td>
                <td>{!u.is_active ? <span className="badge bg-red-100 text-red-800">Suspended</span> : u.is_verified ? <span className="badge bg-emerald-100 text-emerald-800">Active</span> : <span className="badge bg-amber-100 text-amber-800">Unverified</span>}</td>
                <td>{u.role === "ngo" ? <input type="checkbox" aria-label={`Fallback partner ${u.email}`} checked={!!u.is_fallback_partner} onChange={(e) => run(() => api(`/admin/ngos/${u.id}/fallback`, { method: "PUT", body: { is_fallback_partner: e.target.checked } }))} /> : "-"}</td>
                <td className="pr-3 text-right">{u.role !== "admin" && (u.is_active
                  ? <button className="btn-outline btn-sm" onClick={() => window.confirm(`Suspend ${u.email}?`) && run(() => api(`/admin/users/${u.id}/suspend`, { method: "POST" }))}>Suspend</button>
                  : <button className="btn-outline btn-sm" onClick={() => run(() => api(`/admin/users/${u.id}/activate`, { method: "POST" }))}>Activate</button>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Rules() {
  const q = useQuery({ queryKey: ["admin", "rules"], queryFn: () => api<{ disclaimer: string; items: { id: number; food_category: string; storage_condition: string; safe_hours: number; notes: string | null }[] }>("/admin/safety-rules") });
  const { run, err } = useAction(["admin"]);
  const [edit, setEdit] = useState<Record<number, string>>({});
  if (q.isLoading) return <Spinner />;
  if (q.isError) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  return (
    <div className="space-y-3">
      <Notice kind="info">{q.data!.disclaimer}</Notice>
      {err && <Notice kind="error">{err}</Notice>}
      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-stone-50 text-xs uppercase text-stone-500"><tr><th className="px-3 py-2">Food</th><th>Storage</th><th>Safe hours</th><th /></tr></thead>
          <tbody>{q.data!.items.map((r) => {
            const v = edit[r.id] ?? String(r.safe_hours);
            const bad = !(Number(v) > 0 && Number(v) <= 720);
            return (
              <tr key={r.id} className="border-t border-stone-100">
                <td className="px-3 py-2">{label(r.food_category)}</td><td>{label(r.storage_condition)}</td>
                <td><input aria-label={`Safe hours ${r.food_category} ${r.storage_condition}`} className="input w-24 py-1" value={v} onChange={(e) => setEdit({ ...edit, [r.id]: e.target.value })} /></td>
                <td className="pr-3 text-right"><button className="btn-outline btn-sm" disabled={bad || String(r.safe_hours) === v} onClick={() => run(() => api("/admin/safety-rules", { method: "POST", body: { food_category: r.food_category, storage_condition: r.storage_condition, safe_hours: Number(v) } }))}>Save</button></td>
              </tr>);
          })}</tbody>
        </table>
      </div>
      <button className="btn-outline btn-sm" onClick={() => window.confirm("Reset every rule to the defaults?") && run(() => api("/admin/safety-rules/reset", { method: "POST" }))}>Reset to defaults</button>
    </div>
  );
}

const WKEYS = ["distance", "time", "capacity", "preference", "history"] as const;
function Weights() {
  const q = useQuery({ queryKey: ["admin", "weights"], queryFn: () => api<{ weights: Record<string, number>; defaults: Record<string, number> }>("/admin/match-weights") });
  const { run, err } = useAction(["admin"]);
  const [w, setW] = useState<Record<string, number> | null>(null);
  useEffect(() => { if (q.data) setW(q.data.weights); }, [q.data]);
  if (q.isLoading || !w) return <Spinner />;
  if (q.isError) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const sum = WKEYS.reduce((s, k) => s + (w[k] ?? 0), 0);
  const ok = Math.abs(sum - 1) <= 0.01;
  return (
    <div className="card max-w-xl space-y-3">
      <p className="text-sm text-stone-600">Weights decide how NGOs are ranked. They must add up to 1.00.</p>
      {err && <Notice kind="error">{err}</Notice>}
      {WKEYS.map((k) => (
        <div key={k} className="flex items-center gap-3 text-sm">
          <label className="w-24 capitalize" htmlFor={`w-${k}`}>{k}</label>
          <input id={`w-${k}`} type="range" min={0} max={1} step={0.05} className="flex-1" value={w[k]} onChange={(e) => setW({ ...w, [k]: Number(e.target.value) })} />
          <span className="w-12 text-right tabular-nums">{w[k].toFixed(2)}</span>
        </div>
      ))}
      <p className={`text-sm font-medium ${ok ? "text-emerald-700" : "text-red-600"}`}>Total: {sum.toFixed(2)} {ok ? "" : "(must be 1.00)"}</p>
      <div className="flex gap-2">
        <button className="btn-primary" disabled={!ok} onClick={() => run(() => api("/admin/match-weights", { method: "PUT", body: w }))}>Save weights</button>
        <button className="btn-outline" onClick={() => setW(q.data!.defaults)}>Load defaults</button>
      </div>
    </div>
  );
}

function Reports() {
  const q = useQuery({ queryKey: ["admin", "reports"], queryFn: () => api<{ items: { id: number; listing_id: number; reason: string; details: string | null; status: string; created_at: string }[] }>("/admin/reports") });
  const { run, err } = useAction(["admin"]);
  if (q.isLoading) return <Spinner />;
  if (q.isError) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  return (
    <div className="space-y-3">
      {err && <Notice kind="error">{err}</Notice>}
      {q.data!.items.length === 0 && <EmptyState title="No problem reports" />}
      {q.data!.items.map((r) => (
        <div key={r.id} className="card flex flex-wrap items-center justify-between gap-3">
          <div><p className="font-medium">{r.reason} <span className="text-xs text-stone-500">· listing #{r.listing_id}</span></p>{r.details && <p className="text-sm text-stone-600">{r.details}</p>}<p className="text-xs text-stone-400">{fmtDateTime(r.created_at)}</p></div>
          {r.status === "open" ? <button className="btn-outline btn-sm" onClick={() => run(() => api(`/admin/reports/${r.id}/resolve`, { method: "POST" }))}>Mark resolved</button> : <span className="badge bg-emerald-100 text-emerald-800">Resolved</span>}
        </div>
      ))}
    </div>
  );
}

function Ops() {
  const health = useQuery({ queryKey: ["admin", "health"], queryFn: () => api<any>("/admin/health"), refetchInterval: 10000 });
  const perf = useQuery({ queryKey: ["admin", "perf"], queryFn: () => api<any>("/analytics/performance") });
  const audit = useQuery({ queryKey: ["admin", "audit"], queryFn: () => api<{ items: { id: number; actor_id: number | null; action: string; entity: string; entity_id: number | null; created_at: string }[] }>("/admin/audit-log", { query: { limit: 25 } }) });
  const { run, err } = useAction(["forecast"]);
  const h = health.data, p = perf.data;
  return (
    <div className="space-y-5">
      {health.isError && <ErrorState error={health.error} />}
      {h && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat title="System" value={h.status === "ok" ? "Healthy" : h.status} hint={`DB ${h.db} · time scale ×${h.time_scale}`} />
          <Stat title="Scheduler" value={h.scheduler.enabled ? "Running" : "Off"} hint={h.scheduler.last_run ? `last run ${fmtDateTime(h.scheduler.last_run)}` : "no run yet"} />
          <Stat title="Open listings" value={h.open_listings} hint={`${h.pickups_waiting_for_volunteer} pickups need a volunteer`} />
          <Stat title="Users online" value={h.websocket_users_online} />
        </div>
      )}
      {p && (
        <section className="card" aria-label="Escalation performance">
          <h2>Claim performance by escalation level</h2>
          <table className="mt-2 w-full text-left text-sm"><thead className="text-xs uppercase text-stone-500"><tr><th>Level</th><th>Listings</th><th>Claim rate</th><th>Avg time to claim</th></tr></thead>
            <tbody>{Object.entries(p.by_escalation_level as Record<string, any>).map(([lvl, v]) => (
              <tr key={lvl} className="border-t border-stone-100"><td className="py-1.5">L{lvl}</td><td>{v.listings}</td><td>{pct(v.claim_rate)}</td><td>{v.avg_time_to_claim_min != null ? `${v.avg_time_to_claim_min} min` : "-"}</td></tr>))}</tbody></table>
          <p className="mt-2 text-xs text-stone-500">Avg claim to delivery: {p.avg_claim_to_delivery_min != null ? `${p.avg_claim_to_delivery_min} min` : "-"} · {p.deliveries} deliveries · users: {Object.entries(p.users).map(([r, n]) => `${n} ${r}`).join(", ")}</p>
        </section>
      )}
      <section className="card space-y-2">
        <h2>Surplus forecast model</h2>
        {err && <Notice kind="error">{err}</Notice>}
        <button className="btn-outline btn-sm" onClick={() => window.confirm("Retrain on current data? This can take a few seconds.") && run(() => api("/predictions/retrain", { method: "POST" }))}>Retrain model</button>
      </section>
      <section className="card" aria-label="Audit log">
        <h2>Recent audit log</h2>
        <ul className="mt-2 divide-y divide-stone-100 text-sm">
          {audit.data?.items.map((a) => <li key={a.id} className="flex justify-between gap-2 py-1.5"><span><b>{a.action}</b> <span className="text-stone-500">{a.entity}{a.entity_id != null ? ` #${a.entity_id}` : ""} by user {a.actor_id ?? "system"}</span></span><span className="text-xs text-stone-400">{fmtDateTime(a.created_at)}</span></li>)}
        </ul>
      </section>
    </div>
  );
}

export default function AdminDashboard() {
  const [tab, setTab] = useState<Tab>("verify");
  return (
    <div className="space-y-5">
      <h1>Admin console</h1>
      <div className="flex flex-wrap gap-1" role="tablist">{TABS.map(([k, t]) => <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? "tab-active" : ""}`} onClick={() => setTab(k)}>{t}</button>)}</div>
      {tab === "verify" && <Verification />}{tab === "users" && <Users />}{tab === "rules" && <Rules />}
      {tab === "weights" && <Weights />}{tab === "reports" && <Reports />}{tab === "ops" && <Ops />}
    </div>
  );
}
