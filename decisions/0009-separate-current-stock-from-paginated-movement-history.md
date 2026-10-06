# 0009 - Separate current stock from paginated movement history

Date: 2026-09-28
Status: Accepted

## Context

Inventory users need both the current quantity and the movements that produced it. The balance is a small point lookup, while movement history grows continuously and may contain thousands of records for one product and warehouse. Returning an unbounded history or recalculating the balance from every movement would make routine reads increasingly expensive.

## Decision

Expose current stock and movement history as separate read operations. Read the materialized `stock_balances` row for current quantity and return zero when a valid product and warehouse have no movements yet. Preserve access to inactive products so historical queries remain available.

Paginate history in reverse chronological order with a maximum page size of 100. Use the last movement ID as an opaque cursor; resolve its `(created_at, id)` position inside the same organization, product, and warehouse before loading the next page. Order by both fields so equal timestamps remain deterministic.

Create a composite PostgreSQL index on `(organization_id, product_id, warehouse_id, created_at, id)` to support the filter and keyset ordering.

## Alternatives considered

- Return balance and all movements in one response: convenient for tiny histories, but couples a constant-size read to unbounded data.
- Recalculate stock by summing movement history: simple as a source-of-truth model, but wastes work on every operational read.
- Use offset pagination: familiar, but increasingly expensive on deep pages and unstable when new movements are inserted while a user navigates.
- Encode timestamps directly in the public cursor: avoids a cursor lookup, but exposes pagination internals and requires signed encoding to prevent malformed positions.

## Consequences

Operational balance reads remain constant in size, while history can grow without unbounded responses. Cursor navigation is forward-only and requires the referenced movement to remain available. The additional index consumes storage and adds a small cost to movement inserts in exchange for predictable history reads.
