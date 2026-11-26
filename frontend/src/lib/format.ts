/** The API returns naive-UTC ISO strings (no "Z"); treat them as UTC, not local time. */
export function utcMs(iso: string | Date | null | undefined): number {
  if (!iso) return NaN;
  if (iso instanceof Date) return iso.getTime();
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z").getTime();
}

export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

export function urgencyOf(msLeft: number): "green" | "amber" | "red" {
  const min = msLeft / 60000;
  return min < 60 ? "red" : min < 120 ? "amber" : "green";
}

export const URGENCY_CLASS = {
  green: "bg-emerald-100 text-emerald-800 border-emerald-300",
  amber: "bg-amber-100 text-amber-800 border-amber-300",
  red: "bg-red-100 text-red-800 border-red-300",
} as const;

export const URGENCY_HEX = { green: "#059669", amber: "#d97706", red: "#dc2626" } as const;

export function fmtDateTime(iso: string | null | undefined): string {
  const t = utcMs(iso);
  return Number.isNaN(t) ? "-" : new Date(t).toLocaleString([], { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function fmtTime(iso: string | null | undefined): string {
  const t = utcMs(iso);
  return Number.isNaN(t) ? "-" : new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export const pct = (v: number | null | undefined): string => (v == null ? "-" : `${(v * 100).toFixed(0)}%`);
export const label = (s: string): string => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const CATEGORIES = [
  ["cooked_meal", "Cooked meal (rice / curry / dal)"], ["dairy_paneer", "Dairy / paneer dish"],
  ["nonveg_cooked", "Cooked non-veg"], ["bakery_dry", "Bakery / dry snacks"], ["fruits_veg", "Fruits / vegetables"],
  ["sealed_packaged", "Sealed packaged food"],
] as const;
export const STORAGES = [
  ["room", "Room temperature"], ["hot_holding", "Hot holding (above 60 C)"], ["refrigerated", "Refrigerated"],
  ["sealed_packaged", "Sealed package"],
] as const;
