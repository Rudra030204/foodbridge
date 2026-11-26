import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { Impact, Listing } from "../../api/types";
import { Countdown, EmptyState, ErrorState, Spinner, Stat, StatusBadge } from "../../components/ui";
import { fmtDateTime } from "../../lib/format";
import { useAuth } from "../../store/auth";

const FILTERS: [string, string][] = [["", "All"], ["open", "Open"], ["claimed,assigned,picked_up,diverted", "In progress"], ["delivered", "Delivered"], ["expired,cancelled", "Closed"]];

export default function DonorDashboard() {
  const { user } = useAuth();
  const [filter, setFilter] = useState("");
  const listings = useQuery({ queryKey: ["listings", "donor", filter], queryFn: () => api<{ items: Listing[] }>("/listings", { query: { status: filter } }), refetchInterval: 20000 });
  const impact = useQuery({ queryKey: ["impact", "me"], queryFn: () => api<Impact>("/analytics/impact") });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1>My surplus listings</h1>
        <Link to="/donor/new" className="btn-primary">+ Post surplus food</Link>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat title="Meals rescued" value={impact.data?.meals_rescued ?? "-"} />
        <Stat title="Delivered pickups" value={impact.data?.deliveries ?? "-"} />
        <Stat title="CO₂e avoided" value={impact.data ? `${impact.data.co2e_avoided_kg} kg` : "-"} />
        <Stat title="Reliability" value={user?.reliability != null ? `${user.reliability.toFixed(1)} / 5` : "New"} hint={`${user?.rating_count ?? 0} ratings`} />
      </div>
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Filter listings">
        {FILTERS.map(([v, t]) => <button key={t} role="tab" aria-selected={filter === v} className={`tab ${filter === v ? "tab-active" : ""}`} onClick={() => setFilter(v)}>{t}</button>)}
      </div>
      {listings.isLoading && <Spinner />}
      {listings.isError && <ErrorState error={listings.error} retry={() => listings.refetch()} />}
      {listings.data && listings.data.items.length === 0 && (
        <EmptyState title="No listings here yet" hint="Post surplus food and nearby NGOs are notified within seconds." action={<Link to="/donor/new" className="btn-primary">Post surplus food</Link>} />
      )}
      <ul className="grid gap-3 md:grid-cols-2">
        {listings.data?.items.map((l) => (
          <li key={l.id}>
            <Link to={`/donor/listings/${l.id}`} className="card block transition hover:border-brand-500">
              <div className="flex items-start justify-between gap-2">
                <div><p className="font-semibold text-stone-900">{l.title}</p>
                  <p className="text-xs text-stone-500">{l.is_veg ? "Veg" : "Non-veg"} · {l.quantity_meals} meals · posted {fmtDateTime(l.created_at)}</p></div>
                <StatusBadge status={l.status} />
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                {["open", "claimed", "assigned", "diverted"].includes(l.status) && <Countdown safeUntil={l.safe_until} />}
                {l.escalation_level > 0 && <span className="badge bg-orange-100 text-orange-800" data-testid="esc-badge">Escalation L{l.escalation_level}</span>}
                {l.claimed_meals > 0 && <span className="text-stone-500">{l.claimed_meals}/{l.quantity_meals} claimed</span>}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
