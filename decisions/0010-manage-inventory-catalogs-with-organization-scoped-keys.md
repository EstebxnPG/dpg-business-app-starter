# 0010 - Manage inventory catalogs with organization-scoped keys

Date: 2026-10-05
Status: Accepted

## Context

Inventory movements require products and warehouses, but these records could previously be created only through direct database access or test fixtures. Product SKUs and warehouse codes are business identifiers: they must be unique inside one organization, while different organizations may legitimately use the same values.

## Decision

Provide authenticated create and list operations for products and warehouses. Require `catalog:manage` for creation and `inventory:read` for listing. Normalize SKU and warehouse code by trimming whitespace and converting to uppercase; trim display names without changing their casing.

Use the existing organization-scoped unique constraints as the final concurrency guarantee and translate duplicate identifiers into stable 409 responses. List active records by default, allow explicitly including inactive records, and paginate by `(created_at, id)` with pages of at most 100 records.

Keep the first catalog contract limited to identifiers, names, active state, and timestamps. Pricing, costs, descriptions, barcodes, units, and categories will be added only with their own business workflows and validation rules.

## Alternatives considered

- Make SKU and warehouse code globally unique: simpler lookup, but incorrect for a multi-tenant product where organizations control their own identifiers.
- Return every catalog record: workable for tiny businesses, but unsuitable for the expected catalogs of thousands of products.
- Add pricing and all anticipated catalog attributes now: appears complete, but would encode undefined rules and expand the MVP before the inventory workflow is usable.
- Check duplicates only in application code: gives an early error but remains vulnerable to concurrent requests without a database unique constraint.

## Consequences

The inventory workflow can create its required catalog context through the API. Identifier normalization prevents accidental case and whitespace duplicates. Cursor pagination and supporting indexes keep active catalog listing predictable as catalogs grow. Clients must request inactive records explicitly when administering historical catalog entries.
