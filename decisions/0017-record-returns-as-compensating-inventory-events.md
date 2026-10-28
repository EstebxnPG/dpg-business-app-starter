# 0017 - Record returns as compensating inventory events

Date: 2026-10-28
Status: Accepted

## Context

Confirmed sales are historical facts and must not be deleted or rewritten when a cashier makes an error or a customer returns merchandise. Returned products can be physically present without being safe or suitable for resale. A second manual step for recording a cash refund would also be easy to forget.

## Decision

An administrator processes either a partial return or a full void as a new, idempotent document linked to the original sale. Sale rows and original inventory movements remain unchanged. A row lock on the sale serializes overlapping return requests, and cumulative returned quantities may never exceed each sold line.

Inventory balances and movements carry a condition. `AVAILABLE` is the only condition that sales and transfers may consume. `DAMAGED` records physical stock that cannot be sold. Return lines choose `RESTOCK`, which credits `AVAILABLE`, or `DAMAGED`, which credits `DAMAGED`. Voids are full operations, are allowed only before another adjustment, and restore every line to `AVAILABLE`.

Every operation closes its immediate financial outcome with `REFUNDED_NOW` or `NO_REFUND`. It stores both merchandise return value and actual refunded amount. The receipt derives its status and exposes the immutable adjustment history.

## Alternatives considered

- Delete or edit the original sale. This destroys auditability and changes historical analytics.
- Keep damaged products outside inventory. This loses physical accountability and understates losses.
- Use a single undifferentiated stock balance. This could make damaged products available to sell.
- Record the refund in a later manual step. This creates an operational task that can easily be forgotten.

## Consequences

The system can distinguish sellable stock from damaged physical stock, preserve gross sales and returns separately, and explain every compensating movement. The MVP does not yet support exchanges, store credit, repair or quarantine states, payment-gateway refunds, or damaged-to-available reclassification. Those workflows can extend the same immutable movement model later.
