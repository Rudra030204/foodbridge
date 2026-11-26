import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RequireRole } from "./App";

const auth = vi.hoisted(() => ({ state: { user: null as any, loading: false } }));
vi.mock("./store/auth", () => ({
  useAuth: () => auth.state,
  homeFor: (r: string) => ({ donor: "/donor", ngo: "/ngo", volunteer: "/volunteer", admin: "/admin" } as Record<string, string>)[r],
}));
// App imports pages that pull in Leaflet/Recharts; stub them so this test only exercises the guard.
vi.mock("./components/Layout", () => ({ default: ({ children }: any) => <>{children}</> }));
vi.mock("./pages/Landing", () => ({ default: () => null }));
vi.mock("./pages/Auth", () => ({ Login: () => <p>login page</p>, Register: () => null }));
vi.mock("./pages/donor/Dashboard", () => ({ default: () => null }));
vi.mock("./pages/donor/PostListing", () => ({ default: () => null }));
vi.mock("./pages/donor/ListingDetail", () => ({ default: () => null }));
vi.mock("./pages/ngo/Dashboard", () => ({ default: () => null }));
vi.mock("./pages/volunteer/Dashboard", () => ({ default: () => null }));
vi.mock("./pages/admin/Admin", () => ({ default: () => null }));
vi.mock("./pages/Impact", () => ({ default: () => null }));

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<p>login page</p>} />
        <Route path="/donor" element={<p>donor home</p>} />
        <Route path="/ngo" element={<p>ngo home</p>} />
        <Route path="/admin" element={<RequireRole roles={["admin"]}><p>admin secret</p></RequireRole>} />
      </Routes>
    </MemoryRouter>,
  );

describe("RequireRole", () => {
  beforeEach(() => { auth.state = { user: null, loading: false }; });

  it("sends anonymous visitors to /login", () => {
    renderAt("/admin");
    expect(screen.getByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("admin secret")).not.toBeInTheDocument();
  });
  it("sends a donor away from the admin page to their own home", () => {
    auth.state = { user: { role: "donor" }, loading: false };
    renderAt("/admin");
    expect(screen.getByText("donor home")).toBeInTheDocument();
    expect(screen.queryByText("admin secret")).not.toBeInTheDocument();
  });
  it("lets an admin in", () => {
    auth.state = { user: { role: "admin" }, loading: false };
    renderAt("/admin");
    expect(screen.getByText("admin secret")).toBeInTheDocument();
  });
  it("shows a spinner, not a redirect, while the session is loading", () => {
    auth.state = { user: null, loading: true };
    renderAt("/admin");
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("login page")).not.toBeInTheDocument();
  });
});
