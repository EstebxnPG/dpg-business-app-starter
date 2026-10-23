# 0014 - Transfer stock as one atomic operation

Date: 2026-10-23
Status: Accepted

## Context

Moving inventory between warehouses affects two balances. Exposing the move as an unrelated issue followed by a receipt would allow partial success, separate idempotency keys, and no reliable way to prove that both movements belong to the same business action.

## Decision

A transfer is a first-class organization-scoped operation. One database transaction validates the active product and warehouses, conditionally debits the source, credits the destination, records a `StockTransfer`, and writes linked `ISSUE` and `RECEIPT` movements.

The transfer owns one client idempotency key. Its resulting balances are stored so retries can return the original result without applying stock twice. Both balance rows are created when absent and locked in deterministic warehouse identifier order to reduce deadlock risk when opposite transfers overlap.

## Alternatives considered

- Make the client call the movement endpoint twice. This cannot guarantee atomicity across requests and pushes business consistency into every client.
- Record only the two movements. This preserves balance history but loses the explicit operation that connects their shared intent.
- Introduce a generic workflow or event-sourcing framework. The current domain needs one concrete transactional use case, not that operational complexity.

## Consequences

Transfers are atomic, idempotent, attributable to a member, and traceable through both warehouse histories. The schema and service contain additional records and constraints. Cross-database or cross-service transfers remain out of scope; if inventory ownership is split later, the consistency model must be reconsidered.
