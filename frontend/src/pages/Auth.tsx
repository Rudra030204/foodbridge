import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { Notice, Spinner } from "../components/ui";
import { homeFor, useAuth } from "../store/auth";

export function Login() {
  const { user, login, loading } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (loading) return <Spinner />;
  if (user) return <Navigate to={homeFor(user.role)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const u = await login(email.trim().toLowerCase(), password);
      const from = (loc.state as { from?: string } | null)?.from;
      nav(from && from !== "/login" ? from : homeFor(u.role), { replace: true });
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-sm">
      <h1>Log in</h1>
      <form onSubmit={submit} className="card mt-4 space-y-3" aria-label="Login form">
        {err && <Notice kind="error">{err}</Notice>}
        <div><label className="label" htmlFor="email">Email</label><input id="email" type="email" required autoComplete="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><label className="label" htmlFor="password">Password</label><input id="password" type="password" required autoComplete="current-password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Signing in..." : "Log in"}</button>
        <p className="text-center text-sm text-stone-600">New here? <Link className="text-brand-700 underline" to="/register">Create an account</Link></p>
      </form>
      <div className="mt-4 rounded-lg border border-dashed border-stone-300 p-3 text-xs text-stone-500">
        <p className="font-medium text-stone-600">Demo accounts (password <code>Demo@1234</code>)</p>
        <p>donor1@demo.com · ngo1@demo.com · volunteer1@demo.com · admin@demo.com</p>
      </div>
    </div>
  );
}

const DEFAULT_LAT = "28.4744", DEFAULT_LNG = "77.5040"; // Greater Noida, the seeded demo region

export function Register() {
  const { user, register } = useAuth();
  const nav = useNavigate();
  const [role, setRole] = useState<"donor" | "ngo" | "volunteer">("donor");
  const [f, setF] = useState({
    name: "", email: "", password: "", phone: "", org_name: "", address: "", lat: DEFAULT_LAT, lng: DEFAULT_LNG,
    donor_type: "restaurant", fssai: "", capacity: "200", accepts_veg: true, accepts_nonveg: true, reg_no: "",
    vehicle_type: "bike", vol_capacity: "60",
  });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={homeFor(user.role)} replace />;
  const set = (k: keyof typeof f, v: string | boolean) => setF((p) => ({ ...p, [k]: v }));

  const useMyLocation = () =>
    navigator.geolocation?.getCurrentPosition((p) => { set("lat", p.coords.latitude.toFixed(5)); set("lng", p.coords.longitude.toFixed(5)); });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    const lat = Number(f.lat), lng = Number(f.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) return setErr("Enter valid latitude and longitude.");
    if (f.password.length < 8 || !/[A-Za-z]/.test(f.password) || !/\d/.test(f.password)) return setErr("Password needs 8+ characters with letters and digits.");
    const body: Record<string, unknown> = { name: f.name.trim(), email: f.email.trim().toLowerCase(), password: f.password, phone: f.phone || null, role };
    if (role === "donor") body.donor = { org_name: f.org_name, donor_type: f.donor_type, address: f.address, lat, lng, fssai_license_no: f.fssai || null };
    if (role === "ngo") body.ngo = { org_name: f.org_name, address: f.address, lat, lng, daily_capacity_meals: Number(f.capacity) || 200, accepts_veg: f.accepts_veg, accepts_nonveg: f.accepts_nonveg, registration_no: f.reg_no || null };
    if (role === "volunteer") body.volunteer = { vehicle_type: f.vehicle_type, capacity_meals: Number(f.vol_capacity) || 60, home_lat: lat, home_lng: lng };
    setBusy(true);
    try {
      const u = await register(body);
      nav(homeFor(u.role), { replace: true });
    } catch (ex) {
      if (ex instanceof ApiError && ex.status === 422) setErr("Some details are invalid: " + ex.message);
      else setErr(ex instanceof ApiError ? ex.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  };

  const text = (id: keyof typeof f, lbl: string, type = "text", req = true) => (
    <div><label className="label" htmlFor={id}>{lbl}</label>
      <input id={id} type={type} required={req} className="input" value={String(f[id])} onChange={(e) => set(id, e.target.value)} /></div>
  );

  return (
    <div className="mx-auto max-w-xl">
      <h1>Create your account</h1>
      <div className="mt-4 flex gap-2" role="tablist" aria-label="Account type">
        {(["donor", "ngo", "volunteer"] as const).map((r) => (
          <button key={r} role="tab" aria-selected={role === r} type="button" className={`tab ${role === r ? "tab-active" : ""}`} onClick={() => setRole(r)}>
            {{ donor: "Food donor", ngo: "NGO", volunteer: "Volunteer" }[r]}
          </button>
        ))}
      </div>
      <form onSubmit={submit} className="card mt-3 space-y-3" aria-label="Registration form">
        {err && <Notice kind="error">{err}</Notice>}
        <div className="grid gap-3 sm:grid-cols-2">
          {text("name", "Your name")}{text("email", "Email", "email")}
          {text("password", "Password", "password")}{text("phone", "Phone (optional)", "tel", false)}
        </div>
        {role !== "volunteer" && (
          <div className="grid gap-3 sm:grid-cols-2">
            {text("org_name", "Organisation name")}{text("address", "Address")}
          </div>
        )}
        {role === "donor" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div><label className="label" htmlFor="donor_type">Donor type</label>
              <select id="donor_type" className="input" value={f.donor_type} onChange={(e) => set("donor_type", e.target.value)}>
                {["hostel", "restaurant", "wedding", "caterer", "event", "other"].map((t) => <option key={t} value={t}>{t}</option>)}
              </select></div>
            {text("fssai", "FSSAI licence no. (optional)", "text", false)}
          </div>
        )}
        {role === "ngo" && (
          <div className="grid gap-3 sm:grid-cols-2">
            {text("capacity", "Daily capacity (meals)", "number")}{text("reg_no", "Registration no. (optional)", "text", false)}
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.accepts_veg} onChange={(e) => set("accepts_veg", e.target.checked)} /> Accepts veg</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.accepts_nonveg} onChange={(e) => set("accepts_nonveg", e.target.checked)} /> Accepts non-veg</label>
          </div>
        )}
        {role === "volunteer" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div><label className="label" htmlFor="vehicle_type">Vehicle</label>
              <select id="vehicle_type" className="input" value={f.vehicle_type} onChange={(e) => set("vehicle_type", e.target.value)}>
                {["walk", "bike", "car", "van"].map((t) => <option key={t} value={t}>{t}</option>)}
              </select></div>
            {text("vol_capacity", "Carry capacity (meals)", "number")}
          </div>
        )}
        <div className="grid items-end gap-3 sm:grid-cols-3">
          {text("lat", role === "volunteer" ? "Home latitude" : "Latitude")}{text("lng", role === "volunteer" ? "Home longitude" : "Longitude")}
          <button type="button" className="btn-outline" onClick={useMyLocation}>Use my location</button>
        </div>
        {role !== "volunteer" && <Notice>Donor and NGO accounts are reviewed by an admin before they can post or claim food.</Notice>}
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Creating..." : "Create account"}</button>
        <p className="text-center text-sm text-stone-600">Already registered? <Link className="text-brand-700 underline" to="/login">Log in</Link></p>
      </form>
    </div>
  );
}
