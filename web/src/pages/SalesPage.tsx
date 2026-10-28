import { useCallback, useEffect, useState } from "react";
import { Minus, Plus, ReceiptText, RotateCcw, Search, ShoppingCart, Trash2, Undo2 } from "lucide-react";
import { api, idempotencyKey, money, RequestError, shortDate } from "../api";
import type { Organization, Product, SaleReceipt, SaleSummary, Warehouse } from "../types";
import { Button, EmptyState, Field, Modal, PageHeader } from "../ui";

type CartLine = Product & { quantity: number; unitPrice: string };

export function SalesPage({ token, organization }: { token: string; organization: Organization }) {
  const [mode, setMode] = useState<"register" | "history">("register");
  const [products, setProducts] = useState<Product[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [sales, setSales] = useState<SaleSummary[]>([]);
  const [warehouseId, setWarehouseId] = useState("");
  const [cart, setCart] = useState<CartLine[]>([]);
  const [search, setSearch] = useState("");
  const [discountReason, setDiscountReason] = useState("");
  const [approverId, setApproverId] = useState("");
  const [pin, setPin] = useState("");
  const [receipt, setReceipt] = useState<SaleReceipt | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [productResult, warehouseResult, saleResult] = await Promise.all([
      api<{ items: Product[] }>(`/organizations/${organization.id}/products?limit=100`, {}, token),
      api<{ items: Warehouse[] }>(`/organizations/${organization.id}/warehouses?limit=100`, {}, token),
      api<{ items: SaleSummary[] }>(`/organizations/${organization.id}/sales?limit=50`, {}, token),
    ]);
    setProducts(productResult.items);
    setWarehouses(warehouseResult.items);
    setSales(saleResult.items);
    setWarehouseId((current) => current || warehouseResult.items[0]?.id || "");
  }, [organization.id, token]);

  useEffect(() => { void load().catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Could not load sales.")); }, [load]);

  const filtered = products.filter((item) => `${item.sku} ${item.name}`.toLowerCase().includes(search.toLowerCase()));
  const subtotal = cart.reduce((sum, line) => sum + Number(line.sale_price) * line.quantity, 0);
  const total = cart.reduce((sum, line) => sum + Number(line.unitPrice) * line.quantity, 0);
  const discounted = total < subtotal;
  const canReturn = organization.role === "admin";

  function addProduct(product: Product) {
    setCart((current) => {
      const existing = current.find((line) => line.id === product.id);
      return existing ? current.map((line) => line.id === product.id ? { ...line, quantity: line.quantity + 1 } : line) : [...current, { ...product, quantity: 1, unitPrice: product.sale_price }];
    });
  }

  function updateLine(id: string, updates: Partial<CartLine>) { setCart((current) => current.map((line) => line.id === id ? { ...line, ...updates } : line)); }

  async function confirmSale() {
    if (!cart.length || !warehouseId) return;
    setLoading(true); setError("");
    try {
      const body: Record<string, unknown> = {
        warehouse_id: warehouseId,
        lines: cart.map((line) => ({ product_id: line.id, quantity: String(line.quantity), unit_price: line.unitPrice })),
        discount_reason: discounted ? discountReason : null,
      };
      if (approverId && pin) body.approval = { approver_user_id: approverId, pin };
      const created = await api<{ sale_id: string }>(`/organizations/${organization.id}/sales`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey() }, body: JSON.stringify(body) }, token);
      setReceipt(await api<SaleReceipt>(`/organizations/${organization.id}/sales/receipts/${created.sale_id}`, {}, token));
      setCart([]); setDiscountReason(""); setApproverId(""); setPin(""); await load();
    } catch (requestError) {
      if (requestError instanceof RequestError && requestError.code === "DISCOUNT_APPROVAL_REQUIRED") setError("This discount needs an administrator user ID and approval PIN.");
      else setError(requestError instanceof Error ? requestError.message : "Could not confirm sale.");
    } finally { setLoading(false); }
  }

  async function openReceipt(saleId: string) {
    setLoading(true); setError("");
    try { setReceipt(await api<SaleReceipt>(`/organizations/${organization.id}/sales/receipts/${saleId}`, {}, token)); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not open receipt."); }
    finally { setLoading(false); }
  }

  return (
    <>
      <PageHeader title="Sales" description="Confirm traceable sales and keep every later adjustment attached to its receipt." />
      <div className="toolbar-row"><div className="segmented"><button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}><ShoppingCart size={16} /> Register sale</button><button className={mode === "history" ? "active" : ""} onClick={() => setMode("history")}><ReceiptText size={16} /> History</button></div></div>
      {mode === "register" ? <div className="pos-layout">
        <section className="product-browser section-block">
          <div className="search-box"><Search size={17} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by SKU or product" /></div>
          <div className="product-list">{filtered.map((product) => <button key={product.id} onClick={() => addProduct(product)}><span><strong>{product.name}</strong><small>{product.sku}</small></span><span><strong>{money(product.sale_price)}</strong><Plus size={16} /></span></button>)}</div>
        </section>
        <section className="cart-panel section-block">
          <div className="section-heading"><div><h2>Current sale</h2><p>{cart.length} distinct products</p></div><ShoppingCart /></div>
          <Field label="Warehouse"><select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>{warehouses.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></Field>
          <div className="cart-lines">{cart.length === 0 ? <EmptyState>Add products from the catalog.</EmptyState> : cart.map((line) => <div className="cart-line" key={line.id}><div className="cart-product"><strong>{line.name}</strong><small>{line.sku}</small></div><div className="stepper"><button onClick={() => line.quantity > 1 && updateLine(line.id, { quantity: line.quantity - 1 })}><Minus size={14} /></button><span>{line.quantity}</span><button onClick={() => updateLine(line.id, { quantity: line.quantity + 1 })}><Plus size={14} /></button></div><input aria-label={`Price for ${line.name}`} type="number" min={line.cost} max={line.sale_price} value={line.unitPrice} onChange={(e) => updateLine(line.id, { unitPrice: e.target.value })} /><button className="icon-button danger-text" onClick={() => setCart((current) => current.filter((item) => item.id !== line.id))}><Trash2 size={17} /></button></div>)}</div>
          {discounted && <div className="discount-fields"><Field label="Discount reason"><input value={discountReason} onChange={(e) => setDiscountReason(e.target.value)} required /></Field><details><summary>Administrator approval</summary><div className="form-grid"><Field label="Administrator user ID"><input value={approverId} onChange={(e) => setApproverId(e.target.value)} /></Field><Field label="6-digit PIN"><input inputMode="numeric" maxLength={6} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} /></Field></div></details></div>}
          <div className="cart-summary"><span><small>Subtotal</small><strong>{money(subtotal)}</strong></span><span className="discount"><small>Discount</small><strong>-{money(subtotal - total)}</strong></span><span className="total"><small>Total</small><strong>{money(total)}</strong></span></div>
          {error && <div className="form-error">{error}</div>}
          <Button onClick={confirmSale} loading={loading} disabled={!cart.length || (discounted && !discountReason)}>Confirm sale</Button>
        </section>
      </div> : <SalesHistory sales={sales} openReceipt={openReceipt} loading={loading} />}
      {receipt && <ReceiptModal receipt={receipt} canReturn={canReturn} token={token} organizationId={organization.id} onClose={() => setReceipt(null)} onChanged={() => openReceipt(receipt.sale_id)} />}
    </>
  );
}

function SalesHistory({ sales, openReceipt, loading }: { sales: SaleSummary[]; openReceipt: (id: string) => void; loading: boolean }) {
  return <div className="table-wrap">{sales.length ? <table><thead><tr><th>Date</th><th>Reference</th><th>Subtotal</th><th>Discount</th><th>Total</th><th></th></tr></thead><tbody>{sales.map((sale) => <tr key={sale.id}><td>{shortDate(sale.created_at)}</td><td className="mono">{sale.id.slice(0, 8)}</td><td>{money(sale.subtotal)}</td><td>{money(sale.discount_total)}</td><td><strong>{money(sale.total)}</strong></td><td><Button variant="ghost" disabled={loading} onClick={() => openReceipt(sale.id)}><ReceiptText size={16} /> Receipt</Button></td></tr>)}</tbody></table> : <EmptyState>No sales have been confirmed.</EmptyState>}</div>;
}

function ReceiptModal({ receipt, canReturn, token, organizationId, onClose, onChanged }: { receipt: SaleReceipt; canReturn: boolean; token: string; organizationId: string; onClose: () => void; onChanged: () => void }) {
  const [returning, setReturning] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(receipt.lines[0]?.product_id ?? "");
  const [quantity, setQuantity] = useState("1");
  const [disposition, setDisposition] = useState("RESTOCK");
  const [resolution, setResolution] = useState("REFUNDED_NOW");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submitReturn() {
    setLoading(true); setError("");
    try {
      await api(`/organizations/${organizationId}/sales/${receipt.sale_id}/returns`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey() }, body: JSON.stringify({ lines: [{ product_id: selectedProduct, quantity, disposition }], refund_resolution: resolution, reason }) }, token);
      setReturning(false); onChanged();
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not process return."); }
    finally { setLoading(false); }
  }

  async function voidSale() {
    if (!window.confirm("Void this complete sale and restore every product to available stock?")) return;
    const voidReason = window.prompt("Reason for voiding this sale:");
    if (!voidReason) return;
    setLoading(true); setError("");
    try {
      await api(`/organizations/${organizationId}/sales/${receipt.sale_id}/void`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey() }, body: JSON.stringify({ refund_resolution: "REFUNDED_NOW", reason: voidReason }) }, token);
      onChanged();
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Could not void sale."); }
    finally { setLoading(false); }
  }

  return <Modal title={`Receipt ${receipt.sale_id.slice(0, 8)}`} onClose={onClose} wide><div className="receipt-header"><div><span>{receipt.organization_name}</span><strong>{receipt.warehouse_name}</strong><small>{shortDate(receipt.created_at)}</small></div><span className={`status ${receipt.status === "CONFIRMED" ? "success" : receipt.status === "VOIDED" ? "danger" : "warning"}`}>{receipt.status.replace("_", " ")}</span></div><div className="receipt-lines">{receipt.lines.map((line) => <div key={line.product_id}><span><strong>{line.name}</strong><small>{line.sku} · {line.quantity} × {money(line.unit_price)}</small></span><strong>{money(line.line_total)}</strong></div>)}</div><div className="receipt-totals"><span>Subtotal <strong>{money(receipt.subtotal)}</strong></span><span>Discount <strong>-{money(receipt.discount_total)}</strong></span><span>Total <strong>{money(receipt.total)}</strong></span></div>{receipt.adjustments.length > 0 && <div className="adjustment-history"><h3>Adjustments</h3>{receipt.adjustments.map((item) => <div key={item.id}><span><strong>{item.kind}</strong><small>{item.reason} · {shortDate(item.created_at)}</small></span><span>{item.refund_resolution === "REFUNDED_NOW" ? `Refunded ${money(item.refunded_amount)}` : "No refund"}</span></div>)}</div>}{error && <div className="form-error">{error}</div>}{canReturn && receipt.status !== "VOIDED" && <footer className="receipt-actions"><Button variant="secondary" onClick={() => setReturning(!returning)}><RotateCcw size={16} /> Return item</Button><Button variant="danger" onClick={voidSale} loading={loading} disabled={receipt.adjustments.length > 0}><Undo2 size={16} /> Void sale</Button></footer>}{returning && <div className="return-form"><div className="form-grid"><Field label="Product"><select value={selectedProduct} onChange={(e) => setSelectedProduct(e.target.value)}>{receipt.lines.map((line) => <option key={line.product_id} value={line.product_id}>{line.name}</option>)}</select></Field><Field label="Quantity"><input type="number" min="0.000001" step="0.000001" value={quantity} onChange={(e) => setQuantity(e.target.value)} /></Field><Field label="Disposition"><select value={disposition} onChange={(e) => setDisposition(e.target.value)}><option value="RESTOCK">Return to available stock</option><option value="DAMAGED">Damaged stock</option></select></Field><Field label="Financial outcome"><select value={resolution} onChange={(e) => setResolution(e.target.value)}><option value="REFUNDED_NOW">Refunded now</option><option value="NO_REFUND">No refund</option></select></Field></div><Field label="Reason"><input value={reason} onChange={(e) => setReason(e.target.value)} required /></Field><div className="modal-actions"><Button variant="secondary" onClick={() => setReturning(false)}>Cancel</Button><Button onClick={submitReturn} loading={loading} disabled={!reason}>Confirm return</Button></div></div>}</Modal>;
}
