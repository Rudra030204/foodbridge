import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { Listing, Pickup } from "../../api/types";
import MapView from "../../components/MapView";
import Rate from "../../components/Rate";
import { Countdown, EmptyState, ErrorState, Notice, ScoreBars, Spinner, StatusBadge, StatusTimeline } from "../../components/ui";
import { fmtDateTime, URGENCY_HEX } from "../../lib/format";
import { useAuth } from "../../store/auth";

function OfferCard({ l, onDone }: { l: Listing; onDone: (m: string, kind: "success" | "error") => void }) {
  const qc = useQueryClient();
  const [qty, setQty] = useState("");
  const [why, setWhy] = useState(false);
  const claim = useMutation({
    mutationFn: () => api("/listings/" + l.id + "/claim", { method: "POST", body: qty.trim() ? { quantity: Number(qty) } : {} }),
    onSuccess: () => { onDone(`Claimed "${l.title}". A volunteer is being assigned.`, "success"); void qc.invalidateQueries(); },
    onError: (e) => {
      const msg = e instanceof ApiError && e.status === 409 ? "Too late: another NGO claimed this first." : e instanceof ApiError ? e.message : "Could not claim.";
      onDone(msg, "error");
      void qc.invalidateQueries({ queryKey: ["listings"] });
    },
  });
  const open = l.status === "open" && l.remaining_meals > 0 && !l.my_claim_id;
  const qtyBad = qty.trim() !== "" && (!Number.isInteger(Number(qty)) || Number(qty) < 1 || Number(qty) > l.remaining_meals);

  return (
    <li className="card space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div><p className="font-semibold text-stone-900">{l.title}</p>
          <p className="text-xs text-stone-500">{l.donor_org ?? "Donor"} {l.donor_verified && <span title="Verified donor">✔</span>} · {l.is_veg ? "Veg" : "Non-veg"} · {l.remaining_meals} of {l.quantity_meals} meals left · {l.area_cell}</p></div>
        <StatusBadge status={l.my_claim_id ? "claimed" : l.status} />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Countdown safeUntil={l.safe_until} />
        {l.my_match && <span className="badge bg-brand-100 text-brand-800">Match {(l.my_match.score * 100).toFixed(0)} · {l.my_match.distance_km.toFixed(1)} km</span>}
        {l.escalation_level > 0 && <span className="badge bg-orange-100 text-orange-800">Escalation L{l.escalation_level}</span>}
      </div>
      {l.my_match && (<><button className="text-xs text-brand-700 hover:underline" onClick={() => setWhy(!why)}>{why ? "Hide" : "Why am I seeing this?"}</button>{why && <ScoreBars match={l.my_match} />}</>)}
      {open && (
        <div className="flex flex-wrap items-start gap-2">
          <div>
            <input aria-label="Quantity to claim" className="input w-32" inputMode="numeric" placeholder={`All (${l.remaining_meals})`} value={qty} onChange={(e) => setQty(e.target.value)} />
            {qtyBad && <p className="field-error">1 to {l.remaining_meals} meals.</p>}
          </div>
          <button className="btn-primary" disabled={claim.isPending || qtyBad} onClick={() => claim.mutate()}>{claim.isPending ? "Claiming..." : "Claim"}</button>
        </div>
      )}
    </li>
  );
}

function PickupCard({ p }: { p: Pickup }) {
  const qc = useQueryClient();
  const cancel = useMutation({ mutationFn: () => api(`/claims/${p.claim_id}/cancel`, { method: "POST" }), onSuccess: () => qc.invalidateQueries() });
  const active = !["delivered", "cancelled", "failed"].includes(p.status);
  return (
    <li className="card space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div><p className="font-semibold text-stone-900">{p.listing.title}</p><p className="text-xs text-stone-500">{p.quantity} meals from {p.listing.donor_org} · {p.listing.pickup_address}</p></div>
        <StatusBadge status={p.status} />
      </div>
      {p.is_diversion && <Notice kind="warn">Diversion pickup (compost / animal feed): not for human consumption.</Notice>}
      <StatusTimeline status={p.listing.status} />
      <p className="text-sm text-stone-600">{p.volunteer ? <>Volunteer: <b>{p.volunteer.name}</b>{p.volunteer.phone && ` · ${p.volunteer.phone}`}</> : "Waiting for a volunteer to accept..."}</p>
      {p.delivery_otp && active && (
        <div className="rounded-lg bg-sky-50 p-2 text-center">
          <p className="text-xs text-sky-800">Give this delivery code to the volunteer when the food arrives</p>
          <p data-testid="delivery-otp" className="font-mono text-2xl font-bold tracking-[0.3em] text-sky-900">{p.delivery_otp}</p>
        </div>
      )}
      {p.status === "delivered" && <p className="text-xs text-stone-500">Delivered {fmtDateTime(p.delivered_at)}</p>}
      {p.status === "delivered" && <div className="space-y-1"><Rate pickupId={p.id} toUser={p.listing.donor_id} name="the donor" />{p.volunteer && <Rate pickupId={p.id} toUser={p.volunteer.id} name={p.volunteer.name} />}</div>}
      {active && ["pending_assignment", "offered", "assigned"].includes(p.status) && (
        <button className="btn-outline btn-sm" disabled={cancel.isPending} onClick={() => window.confirm("Cancel this claim? The food goes back to other NGOs.") && cancel.mutate()}>Cancel claim</button>
      )}
    </li>
  );
}

export default function NgoDashboard() {
  const { user, profile } = useAuth();
  const [tab, setTab] = useState<"offers" | "pickups">("offers");
  const [flash, setFlash] = useState<{ text: string; kind: "success" | "error" } | null>(null);
  const offers = useQuery({ queryKey: ["listings", "ngo"], queryFn: () => api<{ items: Listing[] }>("/listings", { query: { status: "open,claimed,assigned,diverted" } }), refetchInterval: 15000 });
  const pickups = useQuery({ queryKey: ["pickups", "ngo"], queryFn: () => api<{ items: Pickup[] }>("/pickups/mine"), refetchInterval: 15000 });
  const items = offers.data?.items ?? [];
  const openOffers = items.filter((l) => l.status === "open" && !l.my_claim_id);
  const points = [
    ...(profile?.lat != null ? [{ lat: profile.lat as number, lng: profile.lng as number, label: "Your NGO", color: "#4f46e5" }] : []),
    ...openOffers.map((l) => ({ lat: l.lat, lng: l.lng, label: l.title, color: URGENCY_HEX[l.urgency] })),
  ];

  return (
    <div className="space-y-5">
      <div><h1>{profile?.org_name ?? user?.name}</h1><p className="text-sm text-stone-500">Food offered to you, best match first.</p></div>
      {flash && <Notice kind={flash.kind}>{flash.text}</Notice>}
      <div className="flex gap-1" role="tablist">
        <button role="tab" aria-selected={tab === "offers"} className={`tab ${tab === "offers" ? "tab-active" : ""}`} onClick={() => setTab("offers")}>Offers ({openOffers.length})</button>
        <button role="tab" aria-selected={tab === "pickups"} className={`tab ${tab === "pickups" ? "tab-active" : ""}`} onClick={() => setTab("pickups")}>My pickups ({pickups.data?.items.length ?? 0})</button>
      </div>
      {tab === "offers" && (
        <>
          {offers.isLoading && <Spinner />}
          {offers.isError && <ErrorState error={offers.error} retry={() => offers.refetch()} />}
          {points.length > 1 && <MapView points={points} height={260} />}
          {offers.data && openOffers.length === 0 && <EmptyState title="No open offers right now" hint="You will get a notification as soon as a nearby donor posts surplus food." />}
          <ul className="grid gap-3 md:grid-cols-2">{openOffers.map((l) => <OfferCard key={l.id} l={l} onDone={(text, kind) => setFlash({ text, kind })} />)}</ul>
        </>
      )}
      {tab === "pickups" && (
        <>
          {pickups.isLoading && <Spinner />}
          {pickups.isError && <ErrorState error={pickups.error} retry={() => pickups.refetch()} />}
          {pickups.data && pickups.data.items.length === 0 && <EmptyState title="No pickups yet" hint="Claim an offer to get started. Your claims appear here." />}
          <ul className="grid gap-3 md:grid-cols-2">{pickups.data?.items.map((p) => <PickupCard key={p.id} p={p} />)}</ul>
        </>
      )}
    </div>
  );
}
