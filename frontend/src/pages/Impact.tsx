import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { Forecast, Impact } from "../api/types";
import MapView from "../components/MapView";
import { ErrorState, Notice, Spinner, Stat } from "../components/ui";
import { label, pct } from "../lib/format";

async function downloadCsv() {
  const text = await api<string>("/analytics/export.csv", { text: true });
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url; a.download = "foodbridge_impact.csv"; a.click();
  URL.revokeObjectURL(url);
}

export default function ImpactPage() {
  const impact = useQuery({ queryKey: ["impact", "full"], queryFn: () => api<Impact & { assumptions?: Record<string, number> }>("/analytics/impact"), refetchInterval: 30000 });
  const forecast = useQuery({ queryKey: ["forecast"], queryFn: () => api<Forecast>("/predictions/forecast", { query: { days: 7 } }), retry: 0 });
  if (impact.isLoading) return <Spinner />;
  if (impact.isError) return <ErrorState error={impact.error} retry={() => impact.refetch()} />;
  const d = impact.data!;
  const statuses = Object.entries(d.listings_by_status).map(([k, v]) => ({ status: label(k), count: v }));
  const topCells = [...(forecast.data?.cells ?? [])].sort((a, b) => b.week_total - a.week_total).slice(0, 5);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1>Impact dashboard</h1>
        <button className="btn-outline" onClick={() => void downloadCsv()}>Export CSV</button>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat title="Meals rescued" value={d.meals_rescued.toLocaleString()} hint={`${d.meals_diverted} diverted to compost / feed`} />
        <Stat title="Food saved" value={`${d.kg_saved} kg`} />
        <Stat title="CO₂e avoided" value={`${d.co2e_avoided_kg} kg`} hint={d.assumptions ? `Assumes ${d.assumptions.kg_per_meal} kg/meal, ${d.assumptions.co2e_per_kg_food} kg CO₂e/kg` : "Estimate"} />
        <Stat title="Delivery success" value={pct(d.delivery_success_rate)} hint={`${d.deliveries} deliveries`} />
        <Stat title="Avg time to claim" value={d.avg_time_to_claim_min != null ? `${d.avg_time_to_claim_min} min` : "-"} />
        <Stat title="Escalation rate" value={pct(d.escalation_rate)} hint="Share of listings that needed escalation" />
        <Stat title="Listings" value={d.listings_total} />
      </div>

      <section className="card" aria-label="Meals per day">
        <h2>Meals rescued per day</h2>
        {d.by_day.length === 0 ? <p className="mt-3 text-sm text-stone-500">No deliveries in this period yet.</p> : (
          <div className="mt-3 h-64"><ResponsiveContainer width="100%" height="100%">
            <BarChart data={d.by_day}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Bar isAnimationActive={false} dataKey="meals" fill="#059669" radius={[4, 4, 0, 0]} /></BarChart>
          </ResponsiveContainer></div>
        )}
      </section>

      <section className="card" aria-label="Listings by status">
        <h2>Listings by status</h2>
        <div className="mt-3 h-56"><ResponsiveContainer width="100%" height="100%">
          <BarChart data={statuses} layout="vertical" margin={{ left: 30 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} /><YAxis type="category" dataKey="status" tick={{ fontSize: 11 }} width={90} /><Tooltip /><Bar isAnimationActive={false} dataKey="count" fill="#4f46e5" radius={[0, 4, 4, 0]} /></BarChart>
        </ResponsiveContainer></div>
      </section>

      <section className="card space-y-3" aria-label="Surplus forecast">
        <h2>Expected surplus next 7 days</h2>
        {forecast.isLoading && <Spinner />}
        {forecast.isError && <Notice kind="warn">The forecast model is not available right now (an admin may need to retrain it).</Notice>}
        {forecast.data && (
          <>
            {forecast.data.is_synthetic && <Notice kind="warn">{forecast.data.note || "Forecast is trained on synthetic demo data, not real donations."}</Notice>}
            <div className="grid gap-4 lg:grid-cols-2">
              <MapView height={260} points={topCells.map((c) => ({ lat: c.lat, lng: c.lng, label: `${c.area_cell}: ${Math.round(c.week_total)} meals`, radius: Math.min(26, 8 + c.week_total / 60), color: "#d97706" }))} />
              <ul className="space-y-2 text-sm">
                {topCells.map((c) => (
                  <li key={c.area_cell} className="rounded-lg border border-stone-200 p-2">
                    <p className="flex justify-between font-medium"><span>{c.area_cell}</span><span>{Math.round(c.week_total)} meals / week</span></p>
                    <p className="text-xs text-stone-500">Peak: {[...c.days].sort((a, b) => b.expected_meals - a.expected_meals)[0]?.weekday} {c.days.some((x) => x.event_flag && x.event_flag !== "none") ? "· event days flagged" : ""}</p>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
