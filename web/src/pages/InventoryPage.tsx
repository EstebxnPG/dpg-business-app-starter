import { useCallback, useEffect, useState } from "react";
import { ArrowDownToLine, ArrowRight, ArrowUpFromLine, PackageCheck, PackageX, RefreshCw } from "lucide-react";
import { api, idempotencyKey, shortDate } from "../api";
import type { Organization, Product, Warehouse } from "../types";
import { Button, Field, PageHeader } from "../ui";

type Balance = { product_id: string; warehouse_id: string; quantity: string; damaged_quantity: string };
type TransferEvent = {
  id: string; source_warehouse_id: string; source_warehouse_name: string;
  destination_warehouse_id: string; destination_warehouse_name: string;
  performed_by_email: string; quantity: string; source_balance_after: string;
  destination_balance_after: string; reason: string; reference: string | null; created_at: string;
};

export function InventoryPage({ token, organization }: { token: string; organization: Organization }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [productId, setProductId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [balance, setBalance] = useState<Balance | null>(null);
  const [transfers, setTransfers] = useState<TransferEvent[]>([]);
  const [form, setForm] = useState({ movement_type: "RECEIPT", quantity: "", reason: "" });
  const [transferForm, setTransferForm] = useState({ destination_warehouse_id: "", quantity: "", reason: "", reference: "" });
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
      setTransferForm((current) => ({ ...current, destination_warehouse_id: warehouseResult.items[1]?.id ?? "" }));
    }).catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Could not load inventory context."));
  }, [organization.id, token]);

  const loadBalance = useCallback(async () => {
    if (!productId || !warehouseId) return;
    setLoading(true); setError("");
    try {
      const [position, transferResult] = await Promise.all([
        api<Balance>(`/organizations/${organization.id}/inventory/stock/${productId}/warehouses/${warehouseId}`, {}, token),
        api<{ items: TransferEvent[] }>(`/organizations/${organization.id}/inventory/transfers?product_id=${productId}&warehouse_id=${warehouseId}&limit=50`, {}, token),
      ]);
      setBalance(position);
      setTransfers(transferResult.items);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not read stock.");
    } finally { setLoading(false); }
  }, [organization.id, productId, token, warehouseId]);

  useEffect(() => { void loadBalance(); }, [loadBalance]);

  useEffect(() => {
    if (transferForm.destination_warehouse_id !== warehouseId) return;
    setTransferForm((current) => ({
      ...current,
      destination_warehouse_id: warehouses.find((item) => item.id !== warehouseId)?.id ?? "",
    }));
  }, [transferForm.destination_warehouse_id, warehouseId, warehouses]);

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

  async function transferStock(event: React.FormEvent) {
    event.preventDefault(); setLoading(true); setError(""); setMessage("");
    try {
      await api(`/organizations/${organization.id}/inventory/transfers`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey() },
        body: JSON.stringify({
          product_id: productId,
          source_warehouse_id: warehouseId,
          ...transferForm,
          reference: transferForm.reference || null,
        }),
      }, token);
      setTransferForm({ ...transferForm, quantity: "", reason: "", reference: "" });
      setMessage("Inventory transferred atomically.");
      await loadBalance();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not transfer inventory.");
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
      {canMove && warehouses.length > 1 && <section className="section-block movement-panel">
        <div className="section-heading"><div><h2>Transfer stock</h2><p>Move available inventory as one atomic business operation.</p></div></div>
        <form onSubmit={transferStock} className="transfer-form">
          <Field label="Destination warehouse"><select value={transferForm.destination_warehouse_id} onChange={(e) => setTransferForm({ ...transferForm, destination_warehouse_id: e.target.value })}>{warehouses.filter((item) => item.id !== warehouseId).map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></Field>
          <Field label="Quantity"><input type="number" min="0.000001" step="0.000001" value={transferForm.quantity} onChange={(e) => setTransferForm({ ...transferForm, quantity: e.target.value })} required /></Field>
          <Field label="Reason"><input value={transferForm.reason} onChange={(e) => setTransferForm({ ...transferForm, reason: e.target.value })} placeholder="Store replenishment..." required /></Field>
          <Field label="Reference"><input value={transferForm.reference} onChange={(e) => setTransferForm({ ...transferForm, reference: e.target.value })} placeholder="Optional" /></Field>
          <Button type="submit" loading={loading} disabled={!transferForm.destination_warehouse_id}><ArrowRight size={16} /> Transfer</Button>
        </form>
      </section>}
      <section className="section-block transfer-audit">
        <div className="section-heading"><div><h2>Transfer audit</h2><p>One business event with its two inventory effects available for inspection.</p></div></div>
        {transfers.length === 0 ? <p className="empty-audit">No transfers involve this product and warehouse.</p> : transfers.map((transfer) => <details key={transfer.id} className="audit-event">
          <summary><span><strong>{transfer.source_warehouse_name} <ArrowRight size={14} /> {transfer.destination_warehouse_name}</strong><small>{transfer.reason} · {shortDate(transfer.created_at)}</small></span><span><strong>{transfer.quantity}</strong><small>units</small></span></summary>
          <div className="audit-details"><p><span>Responsible</span><strong>{transfer.performed_by_email}</strong></p><p><span>Reference</span><strong>{transfer.reference || "—"}</strong></p><div className="ledger-effects"><div><ArrowUpFromLine size={16} /><span>Issue from {transfer.source_warehouse_name}</span><strong>Balance {transfer.source_balance_after}</strong></div><div><ArrowDownToLine size={16} /><span>Receipt at {transfer.destination_warehouse_name}</span><strong>Balance {transfer.destination_balance_after}</strong></div></div></div>
        </details>)}
      </section>
      {message && <div className="success-message">{message}</div>}
      {error && <div className="form-error">{error}</div>}
    </>
  );
}
