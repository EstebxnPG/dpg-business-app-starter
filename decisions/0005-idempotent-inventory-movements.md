# 0005 - Make inventory movements idempotent

Date: 2026-09-22
Status: Accepted

## Context

A client may retry a stock-changing request when a response is delayed or lost. Applying every copy would change inventory more than once. Two copies may also arrive concurrently, so an application-level lookup alone cannot guarantee uniqueness.

## Decision

Require an idempotency key for every inventory movement and make it unique within the organization. Store a fingerprint of the movement request and the resulting balance with the confirmed movement.

When the same organization and key are received again with the same fingerprint, return the original movement ID and balance without changing inventory. Reject reuse of the key with different movement data. Use PostgreSQL's unique constraint as the final concurrency guard; if concurrent requests race, the losing transaction rolls back its balance change and then returns the committed movement.

## Alternatives considered

- Disable repeated submissions in the user interface: useful feedback, but it cannot prevent network retries or concurrent API clients.
- Check for an existing key only in application code: two concurrent requests can both pass the check before either writes.
- Keep keys only in a cache: expiration or cache loss could allow a duplicate business operation.

## Consequences

Retries are safe and return the original result. Clients must generate a new key for each new business operation and reuse it only for retries. Confirmed movements store additional request metadata. Key retention currently follows movement retention; an expiration policy can be introduced only after its business consequences are defined.
