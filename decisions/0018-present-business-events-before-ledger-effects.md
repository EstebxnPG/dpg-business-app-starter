# 0018 - Present business events before inventory ledger effects

Date: 2026-10-28
Status: Accepted

## Context

One business action can produce several inventory movements. A warehouse transfer is one decision by an operator, but it creates an issue at the source and a receipt at the destination. Showing both rows as unrelated top-level audit entries makes the activity appear duplicated and forces users to reconstruct what happened from implementation details.

The same distinction will later matter for multi-line sales, returns, imports, and external integrations.

## Decision

Operational audit views present the business document or event as the top-level record. A transfer appears once with its product, quantity, source, destination, actor, reason, reference, and timestamp. Its debit and credit movements remain immutable and are available as expandable details.

Inventory movement history remains the technical ledger used to explain balance changes. Read APIs must preserve explicit identifiers such as `transfer_id`, `sale_id`, and `sale_return_id` so clients can associate effects with their originating event without guessing from timestamps or text.

## Alternatives considered

- Show every ledger movement as an independent audit event. This is technically accurate but operationally confusing and duplicates multi-effect actions.
- Deduplicate movements in the frontend using matching timestamps, quantities, or references. This is fragile and can combine unrelated concurrent operations.
- Hide the underlying movements completely. This simplifies the screen but removes the evidence needed to investigate balance changes.

## Consequences

The main audit experience follows the language of the business while retaining drill-down traceability. The backend needs event-oriented read models in addition to the movement ledger. This is not full event sourcing: current balances and business documents remain ordinary transactional state, and the audit projection is a read concern.
