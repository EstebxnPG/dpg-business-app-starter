# 0015 - Confirm priced sales with controlled discounts

Date: 2026-10-23
Status: Accepted

## Context

A physical sale must preserve the price and cost that applied when it happened, decrement every requested product atomically, and accommodate routine negotiation without forcing employees to share administrator credentials. Catalog prices and costs can change later, so they cannot reconstruct a historical sale reliably.

## Decision

A confirmed sale belongs to one warehouse and contains unique product lines. Each line snapshots the catalog price, actual unit price, and current recorded unit cost. Sale creation, stock decrements, lines, totals, and linked inventory movements share one database transaction and one client idempotency key.

Organizations define the maximum discount rate a salesperson may apply. Discounts within that policy require a reason but no interruption. Larger discounts require a six-digit PIN from a specific administrator, whose identity is recorded on the sale. PINs are hashed, never returned, and locked for 15 minutes after five consecutive failures. Administrators may authorize their own exceptional discounts through their authenticated session. Prices below recorded cost are rejected.

## Alternatives considered

- Always require administrator approval for any discount. This does not match ordinary counter negotiation and encourages workarounds.
- Leave the final price unrestricted. This allows accidental or unauthorized margin loss.
- Store only the current product price and calculate historical sales later. This rewrites history when catalog values change.
- Create pending sales and reserve stock while waiting for remote approval. This adds expiration and reservation workflows that the initial in-person scenario does not need.

## Consequences

Sales provide reliable revenue, discount, seller, approver, and gross-margin inputs for the future data platform. The current `Product.cost` is a simple recorded cost, not FIFO, weighted-average, tax-inclusive, or landed-cost inventory valuation. Those methods require a later explicit decision. Payment processing, returns, taxes, customers, receipts, and multi-warehouse fulfillment remain outside this increment.
