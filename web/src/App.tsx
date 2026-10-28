import { useEffect, useState } from "react";
import {
  BarChart3,
  Boxes,
  LogOut,
  PackageSearch,
  PanelLeftClose,
  PanelLeftOpen,
  ReceiptText,
  ShoppingCart,
} from "lucide-react";
import { api, RequestError } from "./api";
import { CatalogPage } from "./pages/CatalogPage";
import { DashboardPage } from "./pages/DashboardPage";
import { InventoryPage } from "./pages/InventoryPage";
import { LoginPage } from "./pages/LoginPage";
import { SalesPage } from "./pages/SalesPage";
import type { Organization } from "./types";

type View = "overview" | "catalog" | "inventory" | "sales";

const views = [
  { id: "overview" as const, label: "Overview", icon: BarChart3 },
  { id: "catalog" as const, label: "Catalog", icon: Boxes },
  { id: "inventory" as const, label: "Inventory", icon: PackageSearch },
  { id: "sales" as const, label: "Sales", icon: ShoppingCart },
];

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem("dpg_token") ?? "");
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationId, setOrganizationId] = useState(
    () => localStorage.getItem("dpg_organization") ?? "",
  );
  const [view, setView] = useState<View>("overview");
  const [collapsed, setCollapsed] = useState(false);
  const [loading, setLoading] = useState(Boolean(token));
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    api<{ items: Organization[] }>("/organizations", {}, token)
      .then(({ items }) => {
        setOrganizations(items);
        const selected = items.some((item) => item.id === organizationId)
          ? organizationId
          : (items[0]?.id ?? "");
        setOrganizationId(selected);
        if (selected) localStorage.setItem("dpg_organization", selected);
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof RequestError && requestError.status === 401) logout();
        else setError(requestError instanceof Error ? requestError.message : "Could not load organizations.");
      })
      .finally(() => setLoading(false));
  }, [organizationId, token]);

  function onLogin(accessToken: string) {
    localStorage.setItem("dpg_token", accessToken);
    setToken(accessToken);
    setError("");
  }

  function logout() {
    localStorage.removeItem("dpg_token");
    localStorage.removeItem("dpg_organization");
    setToken("");
    setOrganizationId("");
    setOrganizations([]);
  }

  function selectOrganization(id: string) {
    setOrganizationId(id);
    localStorage.setItem("dpg_organization", id);
  }

  if (!token) return <LoginPage onLogin={onLogin} />;
  if (loading) return <div className="app-loading"><ReceiptText size={28} /> Loading workspace...</div>;

  const organization = organizations.find((item) => item.id === organizationId);
  if (!organization) {
    return (
      <main className="centered-message">
        <Boxes size={30} />
        <h1>No organization available</h1>
        <p>Your account does not have an active business membership.</p>
        {error && <p className="error-text">{error}</p>}
        <button className="button secondary" onClick={logout}>Sign out</button>
      </main>
    );
  }

  return (
    <div className={`app-shell ${collapsed ? "collapsed" : ""}`}>
      <aside className="sidebar">
        <div className="brand-mark"><span>DPG</span><strong>Business</strong></div>
        <button className="collapse-button" onClick={() => setCollapsed(!collapsed)} aria-label="Toggle sidebar">
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
        <nav>
          {views.map(({ id, label, icon: Icon }) => (
            <button key={id} className={view === id ? "active" : ""} onClick={() => setView(id)} title={label}>
              <Icon size={19} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button onClick={logout} title="Sign out"><LogOut size={18} /><span>Sign out</span></button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="organization-switcher">
            <span>Organization</span>
            <select value={organizationId} onChange={(event) => selectOrganization(event.target.value)}>
              {organizations.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
            </select>
          </div>
          <span className="role-badge">{organization.role.replace("_", " ")}</span>
        </header>
        <main className="page-content">
          {view === "overview" && <DashboardPage token={token} organization={organization} navigate={setView} />}
          {view === "catalog" && <CatalogPage token={token} organization={organization} />}
          {view === "inventory" && <InventoryPage token={token} organization={organization} />}
          {view === "sales" && <SalesPage token={token} organization={organization} />}
        </main>
      </div>
    </div>
  );
}
