import { ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import type { Role } from "./api/types";
import { homeFor, useAuth } from "./store/auth";
import Landing from "./pages/Landing";
import { Login, Register } from "./pages/Auth";
import DonorDashboard from "./pages/donor/Dashboard";
import PostListing from "./pages/donor/PostListing";
import DonorListingDetail from "./pages/donor/ListingDetail";
import NgoDashboard from "./pages/ngo/Dashboard";
import VolunteerDashboard from "./pages/volunteer/Dashboard";
import AdminDashboard from "./pages/admin/Admin";
import Impact from "./pages/Impact";

/** Route guard: anonymous users go to /login, wrong-role users go to their own home page. */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Spinner text="Checking your session..." />;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (!roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />;
  return <>{children}</>;
}

function NotFound() {
  return (
    <div className="mx-auto max-w-md py-20 text-center">
      <h1>Page not found</h1>
      <p className="mt-2 text-stone-600">That page does not exist.</p>
      <Link to="/" className="btn-primary mt-4">Go home</Link>
    </div>
  );
}

const guard = (roles: Role[], el: ReactNode) => <RequireRole roles={roles}>{el}</RequireRole>;

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/donor" element={guard(["donor"], <DonorDashboard />)} />
        <Route path="/donor/new" element={guard(["donor"], <PostListing />)} />
        <Route path="/donor/listings/:id" element={guard(["donor", "admin"], <DonorListingDetail />)} />
        <Route path="/ngo" element={guard(["ngo"], <NgoDashboard />)} />
        <Route path="/volunteer" element={guard(["volunteer"], <VolunteerDashboard />)} />
        <Route path="/impact" element={guard(["donor", "ngo", "admin"], <Impact />)} />
        <Route path="/admin" element={guard(["admin"], <AdminDashboard />)} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}
