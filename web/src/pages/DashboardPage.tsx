import { useEffect, useState } from "react";
import { ArrowRight, Boxes, CircleDollarSign, PackageCheck, ReceiptText, TriangleAlert } from "lucide-react";
import { api, money, shortDate } from "../api";
import type { Organization, Product, SaleSummary, Warehouse } from "../types";
import { PageHeader } from "../ui";

export function DashboardPage({ token, organization, navigate }: { token: string; organization: Organization; navigate: (view: "catalog" | "inventory" | "sales") => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [sales, setSales] = useState<SaleSummary[]>([]);

  useEffect(() => {
    Promise.all([
      api<{ items: Product[] }>(`/organizations/${organization.id}/products?limit=100`, {}, token),
      api<{ items: Warehouse[] }>(`/organizations/${organization.id}/warehouses?limit=100`, {}, token),
      api<{ items: SaleSummary[] }>(`/organizations/${organization.id}/sales?limit=5`, {}, token),
    ]).then(([productResult, warehouseResult, saleResult]) => {
      setProducts(productResult.items);
      setWarehouses(warehouseResult.items);
      setSales(saleResult.items);
    }).catch(() => undefined);
  }, [organization.id, token]);

  const today = new Date().toDateString();
  const todaySales = sales.filter((sale) => new Date(sale.created_at).toDateString() === today);
  const todayRevenue = todaySales.reduce((total, sale) => total + Number(sale.total), 0);

  return (
    <>
      <PageHeader title={`Good to see you at ${organization.name}`} description="A live view of the workflows that keep the operation moving." />
      <section className="metrics-grid">
        <article className="metric"><Boxes /><span>Active products</span><strong>{products.filter((item) => item.active).length}</strong><small>Catalog records ready to sell</small></article>
        <article className="metric"><PackageCheck /><span>Warehouses</span><strong>{warehouses.filter((item) => item.active).length}</strong><small>Active inventory locations</small></article>
        <article className="metric"><ReceiptText /><span>Sales today</span><strong>{todaySales.length}</strong><small>Confirmed operations</small></article>
        <article className="metric accent"><CircleDollarSign /><span>Revenue today</span><strong>{money(todayRevenue)}</strong><small>Before returns and adjustments</small></article>
      </section>
      <section className="dashboard-grid">
        <div className="section-block">
          <div className="section-heading"><div><h2>Recent sales</h2><p>Latest confirmed transactions</p></div><button className="text-button" onClick={() => navigate("sales")}>Open sales <ArrowRight size={15} /></button></div>
          {sales.length === 0 ? <div className="empty-state"><ReceiptText />No sales have been registered yet.</div> : (
            <div className="compact-list">{sales.map((sale) => <div key={sale.id}><span><strong>{money(sale.total)}</strong><small>{shortDate(sale.created_at)}</small></span><span className="muted">{sale.id.slice(0, 8)}</span></div>)}</div>
          )}
        </div>
        <div className="section-block actions-block">
          <div className="section-heading"><div><h2>Quick actions</h2><p>Continue the daily operation</p></div></div>
          <button onClick={() => navigate("sales")}><CircleDollarSign /><span><strong>Register a sale</strong><small>Build a cart and confirm stock</small></span><ArrowRight /></button>
          <button onClick={() => navigate("inventory")}><PackageCheck /><span><strong>Check inventory</strong><small>Available and damaged balances</small></span><ArrowRight /></button>
          <button onClick={() => navigate("catalog")}><Boxes /><span><strong>Manage catalog</strong><small>Products, prices and warehouses</small></span><ArrowRight /></button>
        </div>
      </section>
      {products.some((item) => Number(item.sale_price) === 0) && <div className="notice"><TriangleAlert size={18} /><span>Some products still have a zero price and cannot produce meaningful sales.</span></div>}
    </>
  );
}
