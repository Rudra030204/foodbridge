import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getTokens, setTokens } from "../api/client";
import type { Me, Role, User } from "../api/types";

interface AuthState {
  user: User | null;
  profile: Record<string, any> | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (body: Record<string, unknown>) => Promise<User>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export const homeFor = (role: Role): string =>
  ({ donor: "/donor", ngo: "/ngo", volunteer: "/volunteer", admin: "/admin" })[role];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState<boolean>(!!getTokens());

  const reload = useCallback(async () => {
    if (!getTokens()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      setMe(await api<Me>("/auth/me"));
    } catch {
      setTokens(null);
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    const onLogout = () => setMe(null);
    window.addEventListener("fb:logout", onLogout);
    return () => window.removeEventListener("fb:logout", onLogout);
  }, [reload]);

  const login = useCallback(async (email: string, password: string) => {
    const t = await api("/auth/login", { method: "POST", body: { email, password }, auth: false });
    setTokens(t);
    const m = await api<Me>("/auth/me");
    setMe(m);
    return m.user;
  }, []);

  const register = useCallback(
    async (body: Record<string, unknown>) => {
      await api("/auth/register", { method: "POST", body, auth: false });
      return login(String(body.email), String(body.password));
    },
    [login],
  );

  const logout = useCallback(async () => {
    const t = getTokens();
    if (t) await api("/auth/logout", { method: "POST", body: { refresh_token: t.refresh_token }, auth: false }).catch(() => undefined);
    setTokens(null);
    setMe(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user: me?.user ?? null, profile: me?.profile ?? null, loading, login, register, logout, reload }),
    [me, loading, login, register, logout, reload],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}
