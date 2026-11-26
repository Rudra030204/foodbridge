import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { Pickup, RouteInfo } from "../../api/types";
import MapView from "../../components/MapView";
import Rate from "../../components/Rate";
import { Countdown, EmptyState, ErrorState, Notice, Spinner, StatusBadge } from "../../components/ui";
import { fmtTime } from "../../lib/format";
import { useAuth } from "../../store/auth";

function OtpForm({ p, kind }: { p: Pickup; kind: "pickup" | "delivery" }) {
  const qc = useQueryClient();
  const [otp, setOtp] = useState("");
  const [check, setCheck] = useState({ food_covered: false, container_clean: false, temperature_ok: false });
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api(`/pickups/${p.id}/verify-${kind}-otp`, { method: "POST", body: kind === "pickup" ? { otp, ...check } : { otp } }),
    onSuccess: () => { setOtp(""); setErr(null); void qc.invalidateQueries(); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : "Verification failed."),
  });
  const valid = /^\d{4}$/.test(otp) && (kind === "delivery" || Object.values(check).every(Boolean));
  return (
    <form className="space-y-2 rounded-lg border border-stone-200 bg-stone-50 p-3" onSubmit={(e) => { e.preventDefault(); if (valid) m.mutate(); }} aria-label={`Verify ${kind}`}>
      <p className="text-sm font-medium">{kind === "pickup" ? "Ask the donor for the 4-digit pickup code" : "Ask the NGO for the 4-digit delivery code"}</p>
      {kind === "pickup" && (
        <div className="space-y-1 text-sm">
          <p className="text-xs text-stone-500">Safety checklist (all required):</p>
          {([["food_covered", "Food is covered"], ["container_clean", "Container is clean"], ["temperature_ok", "Temperature looks right (hot food hot, cold food cold)"]] as const).map(([k, t]) => (
            <label key={k} className="flex items-center gap-2"><input type="checkbox" checked={check[k]} onChange={(e) => setCheck({ ...check, [k]: e.target.checked })} />{t}</label>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <input aria-label="OTP code" inputMode="numeric" maxLength={4} className="input w-28 text-center font-mono tracking-widest" value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} />
        <button className="btn-primary" disabled={!valid || m.isPending}>{m.isPending ? "Checking..." : kind === "pickup" ? "Confirm pickup" : "Confirm delivery"}</button>
      </div>
      {err && <Notice kind="error">{err}</Notice>}
      {p.otp_locked_until && <Notice kind="warn">Locked after too many wrong codes. Try again in a few minutes.</Notice>}
    </form>
  );
}

function JobCard({ p }: { p: Pickup }) {
  const qc = useQueryClient();
  const [err, setErr] = useState<string | null>(null);
  const act = useMutation({
    mutationFn: (a: "accept" | "decline" | "start") => api(`/pickups/${p.id}/${a}`, { method: "POST" }),
    onSuccess: () => { setErr(null); void qc.invalidateQueries(); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : "Action failed."),
  });
  return (
    <li className="card space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div><p className="font-semibold text-stone-900">{p.listing.title}</p>
          <p className="text-xs text-stone-500">{p.quantity} meals · {p.listing.is_veg ? "Veg" : "Non-veg"}</p></div>
        <div className="flex items-center gap-2"><StatusBadge status={p.status} />{!["delivered", "failed", "cancelled"].includes(p.status) && <Countdown safeUntil={p.listing.safe_until} />}</div>
      </div>
      <div className="grid gap-2 text-sm sm:grid-cols-2">
        <div className="rounded-lg bg-amber-50 p-2"><p className="text-xs font-medium text-amber-800">PICK UP</p><p>{p.listing.donor_org}</p><p className="text-xs text-stone-600">{p.listing.pickup_address ?? "Exact address is shown after you accept"}</p></div>
        <div className="rounded-lg bg-sky-50 p-2"><p className="text-xs font-medium text-sky-800">DELIVER TO</p><p>{p.ngo.org_name}</p><p className="text-xs text-stone-600">{p.ngo.address}</p></div>
      </div>
      {err && <Notice kind="error">{err}</Notice>}
      {p.status === "offered" && (
        <div className="flex gap-2">
          <button className="btn-primary" disabled={act.isPending} onClick={() => act.mutate("accept")}>Accept job</button>
          <button className="btn-outline" disabled={act.isPending} onClick={() => act.mutate("decline")}>Decline</button>
        </div>
      )}
      {p.status === "assigned" && <button className="btn-primary" disabled={act.isPending} onClick={() => act.mutate("start")}>Start trip to donor</button>}
      {p.status === "en_route" && <OtpForm p={p} kind="pickup" />}
      {p.status === "picked_up" && <OtpForm p={p} kind="delivery" />}
      {p.status === "delivered" && p.can_rate !== false && <Rate pickupId={p.id} toUser={p.ngo.id} name={p.ngo.org_name ?? "the NGO"} />}
    </li>
  );
}

export default function VolunteerDashboard() {
  const { profile, reload } = useAuth();
  const qc = useQueryClient();
  const pickups = useQuery({ queryKey: ["pickups", "vol"], queryFn: () => api<{ items: Pickup[] }>("/pickups/mine"), refetchInterval: 15000 });
  const route = useQuery({ queryKey: ["route"], queryFn: () => api<RouteInfo>("/volunteers/me/route"), refetchInterval: 30000 });
  const avail = useMutation({
    mutationFn: (v: boolean) => api("/volunteers/me/availability", { method: "PUT", body: { is_available: v } }),
    onSuccess: async () => { await reload(); void qc.invalidateQueries(); },
  });
  const share = useMutation({
    mutationFn: (pos: { lat: number; lng: number }) => api("/volunteers/me/location", { method: "PUT", body: pos }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["route"] }),
  });
  const [geoErr, setGeoErr] = useState<string | null>(null);
  const shareLocation = () =>
    navigator.geolocation ? navigator.geolocation.getCurrentPosition((p) => { setGeoErr(null); share.mutate({ lat: p.coords.latitude, lng: p.coords.longitude }); }, () => setGeoErr("Location permission denied or unavailable."))
      : setGeoErr("This browser has no geolocation.");

  const all = pickups.data?.items ?? [];
  const current = all.filter((p) => !["delivered", "failed", "cancelled"].includes(p.status));
  const done = all.filter((p) => p.status === "delivered");
  const stops = route.data?.stops ?? [];
  const available = Boolean(profile?.is_available);
  const pts = stops.map((s) => ({ lat: s.lat, lng: s.lng, label: `${s.seq}. ${s.label}`, color: s.kind === "pickup" ? "#d97706" : "#0284c7" }));
  const cur = profile?.current_lat != null ? [{ lat: profile.current_lat as number, lng: profile.current_lng as number, label: "You", color: "#111827", radius: 6 }] : [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1>My pickups</h1>
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-outline btn-sm" onClick={shareLocation} disabled={share.isPending}>Update my location</button>
          <label className="flex cursor-pointer items-center gap-2 text-sm"><input type="checkbox" checked={available} disabled={avail.isPending} onChange={(e) => avail.mutate(e.target.checked)} /> Available for jobs</label>
        </div>
      </div>
      {geoErr && <Notice kind="warn">{geoErr}</Notice>}
      {!available && <Notice kind="info">You are marked unavailable, so new pickups will not be offered to you.</Notice>}

      {stops.length > 0 && (
        <section className="card space-y-3" aria-label="Planned route">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2>Planned route</h2>
            <p className="text-xs text-stone-500">{route.data!.total_distance_km.toFixed(1)} km · about {Math.round(route.data!.estimated_minutes)} min</p>
          </div>
          {!route.data!.feasible && <Notice kind="warn">This route may not finish before some food stops being safe. Prioritise the earliest-expiring pickup.</Notice>}
          <MapView points={[...pts, ...cur]} route={[...cur.map((c) => [c.lat, c.lng] as [number, number]), ...stops.map((s) => [s.lat, s.lng] as [number, number])]} height={280} />
          <ol className="space-y-1 text-sm">
            {stops.map((s) => (
              <li key={`${s.seq}-${s.kind}`} className="flex items-center justify-between gap-2 rounded-lg bg-stone-50 px-3 py-1.5">
                <span><b>{s.seq}.</b> {s.label}</span>
                <span className="text-xs text-stone-500">ETA {fmtTime(s.eta)} · {s.leg_km.toFixed(1)} km</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {pickups.isLoading && <Spinner />}
      {pickups.isError && <ErrorState error={pickups.error} retry={() => pickups.refetch()} />}
      {pickups.data && current.length === 0 && <EmptyState title="No active jobs" hint="Stay available and share your location: you will be notified when a nearby pickup needs a volunteer." />}
      <ul className="grid gap-3 lg:grid-cols-2">{current.map((p) => <JobCard key={p.id} p={p} />)}</ul>
      {done.length > 0 && (<><h2>Completed</h2><ul className="grid gap-3 lg:grid-cols-2">{done.slice(0, 6).map((p) => <JobCard key={p.id} p={p} />)}</ul></>)}
    </div>
  );
}
