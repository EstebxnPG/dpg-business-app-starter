# 0004 - Enforce inventory ownership in the database

Date: 2026-09-18
Status: Accepted

## Context

Products and warehouses each belong to an organization. A stock balance must never combine a product from one organization with a warehouse from another. Independent foreign keys to product and warehouse IDs only prove that both records exist; they do not prove common ownership.

## Decision

Identify each stock balance by its organization, product, and warehouse. Add unique `(organization_id, id)` pairs to products and warehouses so PostgreSQL can enforce composite foreign keys from the balance to both records. Reject negative balances with a database check constraint.

## Alternatives considered

- Check ownership only in application code: necessary for clear API errors, but another code path could bypass the check.
- Use separate foreign keys to product and warehouse IDs: both references could be valid while pointing to different organizations.
- Add a surrogate ID to each balance: it would not replace the needed uniqueness of the organization, product, and warehouse combination.

## Consequences

The database rejects cross-organization balances and negative quantities even when application code is wrong. The parent tables gain additional unique indexes, and migrations must create those constraints before the balance table. This does not replace authorization checks or the transaction needed to keep balances and movements consistent.
