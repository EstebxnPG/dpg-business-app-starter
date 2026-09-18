# DPG Business App Starter

A reusable backend foundation for business applications. Its first reference use case is inventory control, built as a small, complete workflow rather than a collection of generic modules.

## Purpose

DPG should be able to build operational applications without rebuilding organization access, authorization, validation, and auditability for every project. The starter will capture reliable business events that can later be used by DPG Data Platform or other systems.

The intended first users are a business administrator who manages access and catalog data, and an operator who records inventory activity. Specific roles and permissions will be refined when the workflows require them.

## First functional milestone

An authorized user can create a product, receive 10 units into a warehouse, issue 3 units, and see a balance of 7 with a traceable history of both movements. This workflow will guide the first implementation and its tests.

Initial inventory rules:

- Every movement belongs to an organization, product, and warehouse, and records who performed it.
- Confirmed movements remain in the history; corrections create a new movement.
- An issue cannot make stock negative by default.
- Stock-changing operations must preserve a consistent balance when requests overlap or fail.
- Users cannot access another organization's data through a supplied identifier.

## Scope

The first reference application covers organizations, access control, products, warehouses, inventory movements, balances, and the audit trail needed for that workflow. CSV imports, transfers, and more detailed permissions can follow once the first workflow works end to end.

This starter does not initially process sales, payments, or electronic invoices. Existing POS and spreadsheet data may become inputs to DPG Data Platform. Sales rankings and revenue comparisons require sales data; inventory movements alone cannot answer those questions.

## Technical direction

The current direction is a modular monolith in Python with FastAPI and PostgreSQL. One application and one database keep the initial deployment manageable. Shared business capabilities and domain-specific modules should have clear boundaries, but abstractions should be introduced only when a concrete workflow needs them. The stack will be added incrementally as the implementation begins.

## How we will work

1. Define one observable workflow and its acceptance criteria before expanding the architecture.
2. Implement a small vertical slice across API, business rules, persistence, and tests.
3. Prioritize correctness, organization isolation, and traceability where mistakes would affect business data.
4. Record significant choices in [`decisions/`](decisions/README.md), including alternatives and consequences.
5. Revisit assumptions when a real client or a second application exposes different needs. Reuse is a goal to validate, not a reason to generalize every component now.

The repository is currently in its definition phase. Setup and run instructions will be added with the first executable application.
