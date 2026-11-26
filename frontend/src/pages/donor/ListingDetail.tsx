import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type { Listing, Match, MatchInfo, Pickup } from "../../api/types";
import MapView from "../../components/MapView";
import { Countdown, ErrorState, Notice, ScoreBars, Spinner, StatusBadge, StatusTimeline } from "../../components/ui";
import { fmtDateTime, label, URGENCY_HEX } from "../../lib/format";
import { useAuth } from "../../store/auth";

const LEVELS = ["Level 0: nearby NGOs notified", "Level 1: radius widened to 6 km", "Level 2: 12 km, every eligible NGO", "Level 3: fallback partners (compost / animal feed)"];

export default function DonorListingDetail() {
  const id = Number(useParams().id);
  const { user } = useAuth();
  const qc = useQueryClient();
  const [report, setReport] = useState({ open: false, reason: "", sent: false });
  const [actionErr, setActionErr] = useState<string | null>(null);

  const listing = useQuery({ queryKey: ["listings", id], queryFn: () => api<Listing>(`/listings/${id}`), refetchInterval: 15000 });
  const matches = useQuery({ queryKey: ["matches", id], queryFn: () => api<{ matches: Match[] }>(`/listings/${id}/matches`) });
  const pickups = useQuery({ queryKey: ["pickups", "listing", id], queryFn: () => api<{ items: Pickup[] }>("/pickups/mine"), enabled: user?.role === "donor" });

  const cancel = useMutation({
    mutationFn: () => api(`/listings/${id}/cancel`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["listings"] }),
    onError: (e) => setActionErr(e instanceof ApiError ? e.message : "Failed."),
  });
  const sendReport = useMutation({
    mutationFn: () => api(`/listings/${id}/report`, { method: "POST", body: { reason: report.reason } }),
    onSuccess: () => setReport({ open: false, reason: "", sent: true }),
    onError: (e) => setActionErr(e instanceof ApiError ? e.message : "Failed."),
  });

  if (listing.isLoading) return <Spinner />;
  if (listing.isError) return <ErrorState error={listing.error} retry={() => listing.refetch()} />;
  const l = listing.data!;
  const mine = (pickups.data?.items ?? []).filter((p) => p.listing.id === id);
  const live = ["open", "claimed", "assigned", "diverted"].includes(l.status);
  const cancellable = ["open", "claimed", "assigned", "diverted"].includes(l.status);

  return (
    <div className="space-y-5">
      <Link to="/donor" className="text-sm text-brand-700 hover:underline">← All listings</Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h1>{l.title}</h1><p className="text-sm text-stone-500">{l.is_veg ? "Veg" : "Non-veg"} · {label(l.food_category)} · {label(l.storage_condition)} · {l.quantity_meals} meals ({l.claimed_meals} claimed)</p></div>
        <div className="flex items-center gap-2"><StatusBadge status={l.status} />{live && <Countdown safeUntil={l.safe_until} />}</div>
      </div>
      <div className="card"><StatusTimeline status={l.status} /></div>
      {actionErr && <Notice kind="error">{actionErr}</Notice>}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card space-y-2" aria-label="Escalation">
          <h2>Escalation</h2>
          <ol className="space-y-1 text-sm">
            {LEVELS.map((t, i) => (
              <li key={t} className={`flex items-center gap-2 ${i <= l.escalation_level ? "font-medium text-stone-900" : "text-stone-400"}`}>
                <span className={`h-2.5 w-2.5 rounded-full ${i <= l.escalation_level ? "bg-orange-500" : "bg-stone-300"}`} />{t}
              </li>
            ))}
          </ol>
          <p className="text-xs text-stone-500">Safe until {fmtDateTime(l.safe_until)} · pickup window ends {fmtDateTime(l.pickup_window_end)}</p>
        </section>

        <section className="card space-y-3" aria-label="Pickup">
          <h2>Pickup</h2>
          {mine.length === 0 && <p className="text-sm text-stone-500">No NGO has claimed this yet. NGOs notified: {l.notified_count ?? matches.data?.matches.filter((m) => m.notified).length ?? 0}.</p>}
          {mine.map((p) => (
            <div key={p.id} className="space-y-1 rounded-lg border border-stone-200 p-3 text-sm">
              <p className="flex items-center justify-between"><b>{p.ngo.org_name}</b><StatusBadge status={p.status} /></p>
              <p className="text-stone-600">{p.quantity} meals · {p.volunteer ? `Volunteer: ${p.volunteer.name}` : "Waiting for a volunteer"}</p>
              {p.pickup_otp && p.status !== "picked_up" && p.status !== "delivered" && (
                <div className="mt-2 rounded-lg bg-amber-50 p-2 text-center">
                  <p className="text-xs text-amber-800">Give this pickup code to the volunteer only when they arrive</p>
                  <p data-testid="pickup-otp" className="font-mono text-2xl font-bold tracking-[0.3em] text-amber-900">{p.pickup_otp}</p>
                </div>
              )}
              {p.otp_locked_until && <Notice kind="warn">Too many wrong codes: pickup locked for a few minutes.</Notice>}
            </div>
          ))}
        </section>
      </div>

      {matches.data && matches.data.matches.length > 0 && (
        <section className="card" aria-label="Why these NGOs">
          <h2>Why these NGOs? <span className="text-xs font-normal text-stone-500">(ranked by the weighted match score)</span></h2>
          <ul className="mt-3 grid gap-4 md:grid-cols-2">
            {matches.data.matches.slice(0, 6).map((m) => (
              <li key={m.ngo_id} className="rounded-lg border border-stone-200 p-3">
                <p className="mb-2 flex items-center justify-between text-sm font-semibold">{m.org_name}
                  <span className={`badge ${m.notified ? "bg-sky-100 text-sky-800" : "bg-stone-100 text-stone-600"}`}>{m.notified ? `Notified · ${m.response}` : "Not notified"}</span></p>
                <ScoreBars match={m as unknown as MatchInfo} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <MapView height={240} points={[
        { lat: l.lat, lng: l.lng, label: "Pickup", color: URGENCY_HEX[l.urgency] },
        ...mine.filter((p) => p.ngo.lat != null).map((p) => ({ lat: p.ngo.lat!, lng: p.ngo.lng!, label: p.ngo.org_name ?? "NGO", color: "#4f46e5" })),
      ]} />

      <div className="flex flex-wrap gap-2">
        {user?.role === "donor" && cancellable && (
          <button className="btn-danger" disabled={cancel.isPending} onClick={() => window.confirm("Cancel this listing?") && cancel.mutate()}>Cancel listing</button>
        )}
        <button className="btn-outline" onClick={() => setReport((r) => ({ ...r, open: !r.open }))}>Report a problem</button>
      </div>
      {report.sent && <Notice kind="success">Thanks, an admin will review your report.</Notice>}
      {report.open && (
        <form className="card flex gap-2" onSubmit={(e) => { e.preventDefault(); if (report.reason.trim().length >= 3) sendReport.mutate(); }}>
          <input className="input" aria-label="Problem reason" placeholder="What went wrong?" value={report.reason} onChange={(e) => setReport({ ...report, reason: e.target.value })} />
          <button className="btn-primary" disabled={report.reason.trim().length < 3 || sendReport.isPending}>Send</button>
        </form>
      )}
    </div>
  );
}
