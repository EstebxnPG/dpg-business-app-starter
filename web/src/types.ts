export type Organization = {
  id: string;
  name: string;
  role: "admin" | "warehouse_manager" | "salesperson";
  active: boolean;
};

export type Product = {
  id: string;
  sku: string;
  name: string;
  cost: string;
  sale_price: string;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type Warehouse = {
  id: string;
  code: string;
  name: string;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type SaleSummary = {
  id: string;
  warehouse_id: string;
  sold_by_id: string;
  approved_by_id: string | null;
  subtotal: string;
  discount_total: string;
  total: string;
  cost_total: string;
  created_at: string;
};

export type ReceiptLine = {
  product_id: string;
  sku: string;
  name: string;
  quantity: string;
  list_unit_price: string;
  unit_price: string;
  unit_cost: string;
  line_total: string;
};

export type SaleAdjustment = {
  id: string;
  kind: "RETURN" | "VOID";
  processed_by_id: string;
  refund_resolution: "REFUNDED_NOW" | "NO_REFUND";
  return_value: string;
  refunded_amount: string;
  reason: string;
  created_at: string;
};

export type SaleReceipt = {
  sale_id: string;
  organization_name: string;
  warehouse_id: string;
  warehouse_code: string;
  warehouse_name: string;
  sold_by_id: string;
  approved_by_id: string | null;
  approval_reason: string | null;
  subtotal: string;
  discount_total: string;
  total: string;
  cost_total: string;
  created_at: string;
  status: "CONFIRMED" | "PARTIALLY_RETURNED" | "RETURNED" | "VOIDED";
  lines: ReceiptLine[];
  adjustments: SaleAdjustment[];
};

export type ApiError = {
  code: string;
  message: string;
  details: unknown;
  request_id: string;
};
