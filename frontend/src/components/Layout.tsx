import { ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useRealtime, useToast } from "../hooks/useRealtime";
import { homeFor, useAuth } from "../store/auth";
import NotificationBell from "./NotificationBell";
import { Notice } from "./ui";

const NAV: Record<string, [string, string][]> = {
  donor: [["/donor", "My listings"], ["/donor/new", "Post surplus"], ["/impact", "Impact"]],
  ngo: [["/ngo", "Offers & pickups"], ["/impact", "Impact"]],
  volunteer: [["/volunteer", "My pickups"]],
  admin: [["/admin", "Admin"], ["/impact", "Impact"]],
};

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { connected } = useRealtime();
  const { toasts, dismiss } = useToast();
  const nav = useNavigate();
  const needsVerification = user && ["donor", "ngo"].includes(user.role) && !user.is_verified;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3">
          <Link to={user ? homeFor(user.role) : "/"} className="flex items-center gap-2 text-lg font-bold text-brand-800">
            <span aria-hidden>🍲</span> FoodBridge Plus
          </Link>
          <nav className="flex flex-1 flex-wrap items-center gap-1" aria-label="Main">
            {user && NAV[user.role].map(([to, text]) => (
              <NavLink key={to} to={to} end className={({ isActive }) => `tab ${isActive ? "tab-active" : ""}`}>{text}</NavLink>
            ))}
          </nav>
          {user ? (
            <div className="flex items-center gap-2">
              <span title={connected ? "Live updates connected" : "Reconnecting..."} className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-500" : "bg-stone-300"}`} />
              <NotificationBell />
              <span className="hidden text-sm text-stone-600 sm:inline">{user.name} · <span className="capitalize">{user.role}</span></span>
              <button className="btn-outline btn-sm" onClick={async () => { await logout(); nav("/"); }}>Log out</button>
            </div>
          ) : (
            <div className="flex gap-2">
              <Link to="/login" className="btn-outline btn-sm">Log in</Link>
              <Link to="/register" className="btn-primary btn-sm">Join</Link>
            </div>
          )}
        </div>
      </header>
      {needsVerification && (
        <div className="mx-auto mt-3 w-full max-w-6xl px-4">
          <Notice kind="warn">Your organisation is awaiting admin verification. You can browse, but {user!.role === "ngo" ? "claiming" : "posting"} food unlocks once you are verified.</Notice>
        </div>
      )}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
      <footer className="border-t border-stone-200 py-4 text-center text-xs text-stone-500">
        FoodBridge Plus · student capstone · safe-time estimates are conservative heuristics, not medical advice.
      </footer>
      <div className="fixed bottom-4 right-4 z-40 flex w-80 max-w-[90vw] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="rounded-xl border border-stone-200 bg-white p-3 shadow-lg">
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-semibold">{t.title}</p>
              <button aria-label="Dismiss" className="text-stone-400 hover:text-stone-700" onClick={() => dismiss(t.id)}>×</button>
            </div>
            <p className="text-xs text-stone-600">{t.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
