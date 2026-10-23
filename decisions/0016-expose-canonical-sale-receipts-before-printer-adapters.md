# 0016 - Expose canonical sale receipts before printer adapters

Date: 2026-10-23
Status: Accepted

## Context

Businesses need to retrieve completed sales and produce receipts. Thermal printers, PDF documents, browser printing, and electronic invoicing use different protocols and legal or operational rules. Coupling sale correctness directly to one output device would make hardware availability part of the transaction and complicate testing.

Product names and SKUs can also change after a sale. Reading current catalog values would silently rewrite old receipts even though their monetary snapshots remain correct.

## Decision

The backend exposes an organization-scoped, receipt-ready JSON representation of a confirmed sale. Sale lines snapshot SKU and product name in addition to quantity, catalog price, final price, and recorded cost. Sales can be listed through cursor pagination and retrieved individually without depending on printer hardware.

Receipt renderers and hardware integrations will consume this canonical representation through adapters. A future electronic-invoicing integration will remain a separate concern because a commercial receipt is not itself a fiscal document.

## Alternatives considered

- Generate ESC/POS commands inside the sale transaction. Printer failures must not roll back an otherwise valid sale, and hardware-specific code does not belong in the domain transaction.
- Read SKU and product name from the current catalog. This would make historical receipts mutable.
- Generate PDF as the only receipt representation. JSON is a more reusable contract for web, PDF, email, messaging, and thermal-printer adapters.

## Consequences

Receipts are testable without physical devices and remain historically stable after catalog edits. The system stores a small amount of deliberate duplicate text on every sale line. Layout, PDF generation, printer discovery, retrying print jobs, and electronic invoicing remain later adapters rather than responsibilities of the sales transaction.
