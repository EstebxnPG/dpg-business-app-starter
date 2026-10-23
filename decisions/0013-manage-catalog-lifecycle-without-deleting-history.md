# 0013 - Manage catalog lifecycle without deleting history

Date: 2026-10-23
Status: Accepted

## Context

Administrators need to find, inspect, rename, deactivate, and reactivate products and warehouses. These entities are referenced by inventory history, so physical deletion would either fail through foreign keys or destroy the context needed to explain past movements. Deactivation can also race with a concurrent stock receipt and leave inventory trapped in an inactive context.

## Decision

Provide organization-scoped detail and update operations plus optional catalog search. Allow changes to display names and active state, but keep SKU and warehouse code immutable during this phase because external imports and integrations may treat them as stable business identifiers.

Do not expose delete operations. Permit deactivation only when total stock is zero. Lock the product or warehouse row while checking stock and updating state. New inventory movements take compatible read locks on both catalog rows and reject inactive contexts, so movement creation and deactivation cannot cross unnoticed.

Preserve reads and historical movement access for inactive entities. Record `updated_at` on products and warehouses.

## Alternatives considered

- Hard-delete catalog records: reduces visible data but breaks auditability and historical relationships.
- Allow deactivation with stock: supports discontinued sell-through scenarios, but the current boolean state cannot distinguish sellable, purchasable, blocked, and archived behavior.
- Check stock without row locking: appears sufficient in sequential tests, but a concurrent receipt could add stock immediately after the check.
- Allow SKU and code edits: convenient for corrections, but requires an audit trail and clear behavior for external references that the MVP does not yet provide.

## Consequences

Catalog history remains intact and inactive contexts cannot silently accumulate new inventory. Businesses must reduce stock to zero before deactivation. A richer lifecycle such as discontinued, blocked, or archived can replace the boolean later when sales and purchasing workflows define those meanings.
