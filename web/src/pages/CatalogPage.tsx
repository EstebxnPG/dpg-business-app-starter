import { useCallback, useEffect, useState } from "react";
import { Boxes, Plus, Search, Warehouse as WarehouseIcon } from "lucide-react";
import { api, money } from "../api";
import type { Organization, Product, Warehouse } from "../types";
import { Button, EmptyState, Field, Modal, PageHeader } from "../ui";

export function CatalogPage({ token, organization }: { token: string; organization: Organization }) {
  const [tab, setTab] = useState<"products" | "warehouses">("products");
  const [products, setProducts] = useState<Product[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState<"product" | "warehouse" | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [productResult, warehouseResult] = await Promise.all([
        api<{ items: Product[] }>(`/organizations/${organization.id}/products?limit=100&include_inactive=true`, {}, token),
        api<{ items: Warehouse[] }>(`/organizations/${organization.id}/warehouses?limit=100&include_inactive=true`, {}, token),
      ]);
      setProducts(productResult.items);
      setWarehouses(warehouseResult.items);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load catalog.");
    }
  }, [organization.id, token]);

  useEffect(() => { void load(); }, [load]);

  const filteredProducts = products.filter((item) => `${item.sku} ${item.name}`.toLowerCase().includes(search.toLowerCase()));
  const filteredWarehouses = warehouses.filter((item) => `${item.code} ${item.name}`.toLowerCase().includes(search.toLowerCase()));
  const canManage = organization.role === "admin";

  return (
    <>
      <PageHeader title="Catalog" description="Products, pricing and the locations where inventory lives." actions={canManage ? <Button onClick={() => setModal(tab === "products" ? "product" : "warehouse")}><Plus size={17} /> New {tab === "products" ? "product" : "warehouse"}</Button> : undefined} />
      <div className="toolbar-row">
        <div className="segmented"><button className={tab === "products" ? "active" : ""} onClick={() => setTab("products")}><Boxes size={16} /> Products</button><button className={tab === "warehouses" ? "active" : ""} onClick={() => setTab("warehouses")}><WarehouseIcon size={16} /> Warehouses</button></div>
        <div className="search-box"><Search size={17} /><input placeholder={`Search ${tab}`} value={search} onChange={(event) => setSearch(event.target.value)} /></div>
      </div>
      {error && <div className="form-error">{error}</div>}
      <div className="table-wrap">
        {tab === "products" ? (
          filteredProducts.length ? <table><thead><tr><th>SKU</th><th>Product</th><th>Cost</th><th>Sale price</th><th>Margin</th><th>Status</th></tr></thead><tbody>{filteredProducts.map((item) => <tr key={item.id}><td className="mono">{item.sku}</td><td><strong>{item.name}</strong></td><td>{money(item.cost)}</td><td>{money(item.sale_price)}</td><td>{money(Number(item.sale_price) - Number(item.cost))}</td><td><span className={`status ${item.active ? "success" : "neutral"}`}>{item.active ? "Active" : "Inactive"}</span></td></tr>)}</tbody></table> : <EmptyState>No products match this view.</EmptyState>
        ) : (
          filteredWarehouses.length ? <table><thead><tr><th>Code</th><th>Warehouse</th><th>Status</th></tr></thead><tbody>{filteredWarehouses.map((item) => <tr key={item.id}><td className="mono">{item.code}</td><td><strong>{item.name}</strong></td><td><span className={`status ${item.active ? "success" : "neutral"}`}>{item.active ? "Active" : "Inactive"}</span></td></tr>)}</tbody></table> : <EmptyState>No warehouses match this view.</EmptyState>
        )}
      </div>
      {modal === "product" && <ProductForm token={token} organizationId={organization.id} onClose={() => setModal(null)} onCreated={() => { setModal(null); load(); }} />}
      {modal === "warehouse" && <WarehouseForm token={token} organizationId={organization.id} onClose={() => setModal(null)} onCreated={() => { setModal(null); load(); }} />}
    </>
  );
}

function ProductForm({ token, organizationId, onClose, onCreated }: { token: string; organizationId: string; onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({ sku: "", name: "", cost: "", sale_price: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setLoading(true); setError("");
    try { await api(`/organizations/${organizationId}/products`, { method: "POST", body: JSON.stringify(form) }, token); onCreated(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not create product."); }
    finally { setLoading(false); }
  }
  return <Modal title="New product" onClose={onClose}><form className="modal-form" onSubmit={submit}><div className="form-grid"><Field label="SKU"><input value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} required /></Field><Field label="Name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field><Field label="Recorded cost"><input type="number" min="0" step="0.01" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} required /></Field><Field label="Catalog price"><input type="number" min="0" step="0.01" value={form.sale_price} onChange={(e) => setForm({ ...form, sale_price: e.target.value })} required /></Field></div>{error && <div className="form-error">{error}</div>}<footer className="modal-actions"><Button type="button" variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" loading={loading}>Create product</Button></footer></form></Modal>;
}

function WarehouseForm({ token, organizationId, onClose, onCreated }: { token: string; organizationId: string; onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({ code: "", name: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setLoading(true); setError("");
    try { await api(`/organizations/${organizationId}/warehouses`, { method: "POST", body: JSON.stringify(form) }, token); onCreated(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not create warehouse."); }
    finally { setLoading(false); }
  }
  return <Modal title="New warehouse" onClose={onClose}><form className="modal-form" onSubmit={submit}><Field label="Code"><input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required /></Field><Field label="Name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>{error && <div className="form-error">{error}</div>}<footer className="modal-actions"><Button type="button" variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" loading={loading}>Create warehouse</Button></footer></form></Modal>;
}
