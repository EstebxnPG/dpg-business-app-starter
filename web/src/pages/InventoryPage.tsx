import { useCallback, useEffect, useState } from "react";
import { ArrowDownToLine, ArrowUpFromLine, PackageCheck, PackageX, RefreshCw } from "lucide-react";
import { api, idempotencyKey } from "../api";
import type { Organization, Product, Warehouse } from "../types";
import { Button, Field, PageHeader } from "../ui";

type Balance = { product_id: string; warehouse_id: string; quantity: string; damaged_quantity: string };

export function InventoryPage({ token, organization }: { token: string; organization: Organization }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [productId, setProductId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [balance, setBalance] = useState<Balance | null>(null);
  const [form, setForm] = useState({ movement_type: "RECEIPT", quantity: "", reason: "" });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api<{ items: Product[] }>(`/organizations/${organization.id}/products?limit=100`, {}, token),
      api<{ items: Warehouse[] }>(`/organizations/${organization.id}/warehouses?limit=100`, {}, token),
    ]).then(([productResult, warehouseResult]) => {
      setProducts(productResult.items);
      setWarehouses(warehouseResult.items);
      setProductId(productResult.items[0]?.id ?? "");
      setWarehouseId(warehouseResult.items[0]?.id ?? "");
    }).catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Could not load inventory context."));
  }, [organization.id, token]);

  const loadBalance = useCallback(async () => {
    if (!productId || !warehouseId) return;
    setLoading(true); setError("");
    try {
      setBalance(await api<Balance>(`/organizations/${organization.id}/inventory/stock/${productId}/warehouses/${warehouseId}`, {}, token));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not read stock.");
    } finally { setLoading(false); }
  }, [organization.id, productId, token, warehouseId]);

  useEffect(() => { void loadBalance(); }, [loadBalance]);

  async function recordMovement(event: React.FormEvent) {
    event.preventDefault(); setLoading(true); setError(""); setMessage("");
    try {
      await api(`/organizations/${organization.id}/inventory/movements`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey() },
        body: JSON.stringify({ product_id: productId, warehouse_id: warehouseId, ...form }),
      }, token);
      setForm({ ...form, quantity: "", reason: "" });
      setMessage(form.movement_type === "RECEIPT" ? "Inventory received." : "Inventory issued.");
      await loadBalance();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not record movement.");
    } finally { setLoading(false); }
  }

  const canMove = organization.role === "admin" || organization.role === "warehouse_manager";
  return (
    <>
      <PageHeader title="Inventory" description="Inspect sellable and damaged stock without mixing their operational meaning." actions={<Button variant="secondary" onClick={loadBalance} loading={loading}><RefreshCw size={16} /> Refresh</Button>} />
      <section className="inventory-context section-block">
        <Field label="Product"><select value={productId} onChange={(event) => setProductId(event.target.value)}>{products.map((item) => <option value={item.id} key={item.id}>{item.sku} · {item.name}</option>)}</select></Field>
        <Field label="Warehouse"><select value={warehouseId} onChange={(event) => setWarehouseId(event.target.value)}>{warehouses.map((item) => <option value={item.id} key={item.id}>{item.code} · {item.name}</option>)}</select></Field>
      </section>
      <section className="balance-grid">
        <article className="balance-card available"><PackageCheck /><div><span>Available to sell</span><strong>{balance?.quantity ?? "0"}</strong><small>Consumed by sales and transfers</small></div></article>
        <article className="balance-card damaged"><PackageX /><div><span>Damaged stock</span><strong>{balance?.damaged_quantity ?? "0"}</strong><small>Physically present, never sellable</small></div></article>
      </section>
      {canMove && <section className="section-block movement-panel">
        <div className="section-heading"><div><h2>Record movement</h2><p>Manual receipts and issues affect available inventory.</p></div></div>
        <form onSubmit={recordMovement} className="movement-form">
          <div className="segmented"><button type="button" className={form.movement_type === "RECEIPT" ? "active" : ""} onClick={() => setForm({ ...form, movement_type: "RECEIPT" })}><ArrowDownToLine size={16} /> Receipt</button><button type="button" className={form.movement_type === "ISSUE" ? "active" : ""} onClick={() => setForm({ ...form, movement_type: "ISSUE" })}><ArrowUpFromLine size={16} /> Issue</button></div>
          <Field label="Quantity"><input type="number" min="0.000001" step="0.000001" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} required /></Field>
          <Field label="Reason"><input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="Supplier delivery, correction..." required /></Field>
          <Button type="submit" loading={loading}>Record movement</Button>
        </form>
      </section>}
      {message && <div className="success-message">{message}</div>}
      {error && <div className="form-error">{error}</div>}
    </>
  );
}
