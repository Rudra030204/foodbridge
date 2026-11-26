import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Stat } from "../components/ui";
import { homeFor, useAuth } from "../store/auth";

interface PublicImpact { meals_rescued: number; kg_saved: number; co2e_avoided_kg: number; active_listings: number; deliveries: number }

export default function Landing() {
  const { user } = useAuth();
  const { data } = useQuery({ queryKey: ["impact", "public"], queryFn: () => api<PublicImpact>("/analytics/public", { auth: false }), refetchInterval: 30000 });
  return (
    <div className="space-y-10">
      <section className="rounded-2xl bg-gradient-to-br from-brand-800 to-brand-600 px-6 py-12 text-white sm:px-12">
        <h1 className="max-w-2xl text-3xl text-white sm:text-4xl">Rescue surplus food before it spoils.</h1>
        <p className="mt-3 max-w-xl text-brand-100">
          FoodBridge Plus matches hostels, caterers and event hosts with nearby NGOs and volunteers. A safe-time countdown on every listing and
          automatic escalation make sure good food reaches people, not bins.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          {user ? (
            <Link to={homeFor(user.role)} className="btn bg-white text-brand-800 hover:bg-brand-50">Open my dashboard</Link>
          ) : (
            <>
              <Link to="/register" className="btn bg-white text-brand-800 hover:bg-brand-50">Join the network</Link>
              <Link to="/login" className="btn border border-white/60 text-white hover:bg-white/10">Log in</Link>
            </>
          )}
        </div>
      </section>

      <section aria-label="Platform impact" className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat title="Meals rescued" value={data ? data.meals_rescued.toLocaleString() : "-"} />
        <Stat title="Food saved" value={data ? `${data.kg_saved.toLocaleString()} kg` : "-"} />
        <Stat title="CO₂e avoided" value={data ? `${data.co2e_avoided_kg.toLocaleString()} kg` : "-"} hint="Estimate, see assumptions in Impact" />
        <Stat title="Live listings now" value={data ? data.active_listings : "-"} />
      </section>

      <section className="grid gap-4 md:grid-cols-4">
        {[
          ["1. Donor posts", "Food type, quantity and storage. The system computes a safe-until time and shows a live countdown."],
          ["2. Smart match", "Nearby verified NGOs are ranked by distance, time left, capacity, food preference and track record."],
          ["3. Volunteer pickup", "A volunteer accepts the job, follows an optimised route and verifies pickup and delivery with OTP codes."],
          ["4. Auto-escalate", "No claim? The search radius widens, then fallback partners (compost, animal feed) are notified."],
        ].map(([t, d]) => (
          <div key={t} className="card"><h2 className="text-base">{t}</h2><p className="mt-1 text-sm text-stone-600">{d}</p></div>
        ))}
      </section>
    </div>
  );
}
