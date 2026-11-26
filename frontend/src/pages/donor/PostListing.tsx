import { useMutation, useQuery } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import { Countdown, Notice } from "../../components/ui";
import { CATEGORIES, STORAGES } from "../../lib/format";
import { FormErrors, hasErrors, ListingForm, validateListing } from "../../lib/validation";
import { useAuth } from "../../store/auth";

const EMPTY: ListingForm = { title: "", food_category: "cooked_meal", storage_condition: "room", is_veg: true, quantity_meals: "", cooked_minutes_ago: "30", expiry_at: "", pickup_address: "" };

interface Estimate { ok: boolean; safe_until?: string; minutes_left?: number; rescuable?: boolean; message?: string | null; disclaimer?: string }

export default function PostListing() {
  const { user, profile } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState<ListingForm>(EMPTY);
  const [hotDay, setHotDay] = useState(false);
  const [desc, setDesc] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [serverErr, setServerErr] = useState<string | null>(null);
  const sealed = f.food_category === "sealed_packaged";

  const set = <K extends keyof ListingForm>(k: K, v: ListingForm[K]) => setF((p) => ({ ...p, [k]: v }));
  const onCategory = (c: string) =>
    setF((p) => ({ ...p, food_category: c, storage_condition: c === "sealed_packaged" ? "sealed_packaged" : p.storage_condition === "sealed_packaged" ? "room" : p.storage_condition, is_veg: c === "nonveg_cooked" ? false : p.is_veg }));

  const cookedAtIso = () => new Date(Date.now() - (Number(f.cooked_minutes_ago) || 0) * 60000).toISOString();
  const expiryIso = () => (f.expiry_at ? new Date(f.expiry_at).toISOString() : undefined);

  // Debounced live safe-time preview (server is the source of truth for the rules).
  const [debounced, setDebounced] = useState(f);
  useEffect(() => { const t = setTimeout(() => setDebounced(f), 400); return () => clearTimeout(t); }, [f]);
  const previewable = !hasErrors(validateListing({ ...debounced, title: "xxx", quantity_meals: "1" }));
  const estimate = useQuery({
    queryKey: ["safety-estimate", debounced.food_category, debounced.storage_condition, debounced.cooked_minutes_ago, debounced.expiry_at, hotDay],
    enabled: previewable,
    queryFn: () => api<Estimate>("/listings/safety-estimate", { query: {
      food_category: debounced.food_category, storage_condition: debounced.storage_condition, hot_day: hotDay,
      cooked_at: sealed ? undefined : new Date(Date.now() - (Number(debounced.cooked_minutes_ago) || 0) * 60000).toISOString(),
      expiry_at: debounced.expiry_at ? new Date(debounced.expiry_at).toISOString() : undefined } }),
  });

  const create = useMutation({
    mutationFn: () => api<{ id: number }>("/listings", { method: "POST", body: {
      title: f.title.trim(), description: desc.trim() || null, food_category: f.food_category, is_veg: f.is_veg,
      quantity_meals: Number(f.quantity_meals), storage_condition: f.storage_condition, hot_day: hotDay,
      cooked_at: sealed ? null : cookedAtIso(), expiry_at: sealed ? expiryIso() : null,
      pickup_address: f.pickup_address.trim() || null } }),
    onSuccess: (l) => nav(`/donor/listings/${l.id}`),
    onError: (e) => setServerErr(e instanceof ApiError ? e.message : "Could not reach the server."),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setServerErr(null);
    const errs = validateListing(f);
    setErrors(errs);
    if (!hasErrors(errs)) create.mutate();
  };
  const err = (k: keyof ListingForm) => errors[k] && <p className="field-error" role="alert">{errors[k]}</p>;
  const est = estimate.data;

  return (
    <div className="mx-auto max-w-2xl">
      <h1>Post surplus food</h1>
      {!user?.is_verified && <div className="mt-3"><Notice kind="warn">Your account is not verified yet, so the server will refuse new listings until an admin approves you.</Notice></div>}
      <form onSubmit={submit} noValidate className="card mt-4 space-y-4" aria-label="Post surplus form">
        {serverErr && <Notice kind="error">{serverErr}</Notice>}
        <div><label className="label" htmlFor="title">What is it?</label>
          <input id="title" className="input" placeholder="e.g. Veg biryani and raita" value={f.title} onChange={(e) => set("title", e.target.value)} />{err("title")}</div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div><label className="label" htmlFor="cat">Food type</label>
            <select id="cat" className="input" value={f.food_category} onChange={(e) => onCategory(e.target.value)}>{CATEGORIES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></div>
          <div><label className="label" htmlFor="stor">Storage</label>
            <select id="stor" className="input" value={f.storage_condition} disabled={sealed} onChange={(e) => set("storage_condition", e.target.value)}>{STORAGES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>{err("storage_condition")}</div>
          <div><label className="label" htmlFor="qty">Quantity (meals)</label>
            <input id="qty" inputMode="numeric" className="input" value={f.quantity_meals} onChange={(e) => set("quantity_meals", e.target.value)} />{err("quantity_meals")}</div>
          {sealed ? (
            <div><label className="label" htmlFor="exp">Printed expiry</label>
              <input id="exp" type="datetime-local" className="input" value={f.expiry_at} onChange={(e) => set("expiry_at", e.target.value)} />{err("expiry_at")}</div>
          ) : (
            <div><label className="label" htmlFor="cooked">Cooked how many minutes ago?</label>
              <input id="cooked" inputMode="numeric" className="input" value={f.cooked_minutes_ago} onChange={(e) => set("cooked_minutes_ago", e.target.value)} />{err("cooked_minutes_ago")}</div>
          )}
        </div>
        <div className="flex flex-wrap gap-6 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={f.is_veg} onChange={(e) => set("is_veg", e.target.checked)} /> Vegetarian</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={hotDay} onChange={(e) => setHotDay(e.target.checked)} /> Hot day (above 35 °C)</label>
        </div>
        {err("is_veg")}
        <div><label className="label" htmlFor="addr">Pickup address <span className="font-normal text-stone-400">(optional, defaults to your registered address{profile?.address ? `: ${profile.address}` : ""})</span></label>
          <input id="addr" className="input" value={f.pickup_address} onChange={(e) => set("pickup_address", e.target.value)} /></div>
        <div><label className="label" htmlFor="desc">Notes for the NGO (optional)</label>
          <textarea id="desc" rows={2} className="input" value={desc} onChange={(e) => setDesc(e.target.value)} /></div>

        <div aria-live="polite" data-testid="safety-preview">
          {previewable && estimate.isFetching && <p className="text-sm text-stone-500">Calculating safe time...</p>}
          {est?.ok && est.safe_until && (
            <div className={`rounded-lg border p-3 text-sm ${est.rescuable ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
              <p className="flex flex-wrap items-center gap-2">Safe for another <Countdown safeUntil={est.safe_until} /></p>
              {est.message && <p className="mt-1 text-red-700">{est.message}</p>}
              {est.disclaimer && <p className="mt-1 text-xs text-stone-500">{est.disclaimer}</p>}
            </div>
          )}
          {est && !est.ok && <Notice kind="error">{est.message}</Notice>}
        </div>
        <button className="btn-primary w-full" disabled={create.isPending}>{create.isPending ? "Posting..." : "Post and notify NGOs"}</button>
      </form>
    </div>
  );
}
