/** Thin fetch wrapper: JSON, bearer auth, one automatic token refresh, uniform ApiError. */
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

export type Tokens = { access_token: string; refresh_token: string };
const KEY = "fb_tokens";
const BASE: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

export function getTokens(): Tokens | null {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "null");
  } catch {
    return null;
  }
}

export function setTokens(t: Tokens | null): void {
  try {
    if (t) localStorage.setItem(KEY, JSON.stringify(t));
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable (private mode): tokens stay in memory only */
  }
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const t = getTokens();
  if (!t) return false;
  refreshing ??= fetch(`${BASE}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: t.refresh_token }),
  })
    .then(async (r) => {
      if (!r.ok) return false;
      setTokens(await r.json());
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

type Opts = { method?: string; body?: unknown; query?: Record<string, unknown>; auth?: boolean; text?: boolean };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const { method = "GET", body, query, auth = true, text = false } = opts;
  const qs = query
    ? "?" + new URLSearchParams(Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => [k, String(v)])).toString()
    : "";
  const run = async (): Promise<Response> => {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const tok = getTokens();
    if (auth && tok) headers.Authorization = `Bearer ${tok.access_token}`;
    return fetch(`${BASE}/api/v1${path}${qs}`, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  };
  let res = await run();
  if (res.status === 401 && auth && getTokens()) {
    if (await tryRefresh()) res = await run();
    else {
      setTokens(null);
      window.dispatchEvent(new Event("fb:logout"));
    }
  }
  if (!res.ok) {
    let code = "http_error", message = `Request failed (${res.status})`, details: unknown;
    try {
      const j = await res.json();
      code = j?.error?.code ?? code;
      message = j?.error?.message ?? message;
      details = j?.error?.details;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, message, details);
  }
  if (text) return (await res.text()) as unknown as T;
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export function wsUrl(token: string): string {
  const base = BASE || window.location.origin;
  return `${base.replace(/^http/, "ws")}/ws?token=${encodeURIComponent(token)}`;
}
