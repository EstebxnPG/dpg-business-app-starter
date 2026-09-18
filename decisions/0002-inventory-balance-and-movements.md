# 0002 - Keep inventory balances and movements consistent

Date: 2026-09-18
Status: Accepted

## Context

An inventory operator needs a current balance without repeatedly summing every historical movement. The business also needs to know who changed stock, when, by how much, and why. If the balance and movement history are updated independently, they can disagree after a failure or concurrent request.

## Decision

Store a current balance per organization, product, and warehouse, alongside an append-only movement history. A stock-changing request must validate the operation, update the balance, and insert its movement in one database transaction. A stock issue must not make the balance negative. The movement records the actor, type, quantity, reason, and timestamp; corrections create new movements instead of editing confirmed ones.

Idempotency and concurrent requests must be handled when implementing this transaction so a retry cannot apply a movement twice and distinct requests cannot overspend stock. The exact database constraints and API contract will be defined with the implementation.

## Alternatives considered

- Calculate the balance from all movements on every read: simpler write path, but repeated balance lookups grow with the relevant movement history.
- Update the balance now and write the movement later in a scheduled job: a crash or delayed job could leave unexplained stock, so the history would not reliably describe committed operations.
- Store only the balance: fast to read, but loses the reason and actor behind each change.

## Consequences

Balance lookups remain direct and every committed stock change has a corresponding movement. Writes require a transaction and tests for failures, retries, and concurrency. A scheduled reconciliation job may later compare balances against movements and report discrepancies, but it must not be required to create the history or silently change balances.
