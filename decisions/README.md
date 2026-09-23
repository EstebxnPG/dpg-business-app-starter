# Project decisions

This directory records decisions that affect the product or its architecture. Each record explains the context, the choice, the alternatives considered, and its consequences. It is a history of reasoning, not a list of immutable rules.

## Index

| ID | Decision | Status |
| --- | --- | --- |
| 0001 | [Build a reusable backend through an inventory reference workflow](0001-inventory-reference-workflow.md) | Accepted |
| 0002 | [Keep inventory balances and movements consistent](0002-inventory-balance-and-movements.md) | Accepted |
| 0003 | [Assign access through organization memberships](0003-organization-memberships.md) | Accepted |
| 0004 | [Enforce inventory ownership in the database](0004-enforce-inventory-ownership-in-database.md) | Accepted |
| 0005 | [Make inventory movements idempotent](0005-idempotent-inventory-movements.md) | Accepted |
| 0006 | [Authenticate API users with signed access tokens](0006-authenticate-api-users-with-signed-tokens.md) | Accepted |

## Recording a decision

Add a numbered Markdown file when a choice changes scope, data ownership, security, architecture, or operational behavior. Use this structure:

```text
# NNNN - Short decision title

Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded

## Context
What problem or uncertainty led to this decision?

## Decision
What will we do?

## Alternatives considered
What other reasonable paths did we consider, and why not now?

## Consequences
What becomes easier, harder, or remains unknown?
```

Keep old records when direction changes. Mark them as superseded and link to the newer decision so the reasoning stays visible.
