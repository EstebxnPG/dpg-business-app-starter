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

## Run locally

Python 3.11 or newer and a running Docker engine are required. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
docker compose up -d --wait db
$env:DATABASE_URL = "postgresql+psycopg://dpg_dev:dpg_dev@127.0.0.1:5433/dpg_app"
$env:JWT_SECRET_KEY = "replace-with-at-least-32-random-characters"
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API documentation. `GET /health` confirms that the API process responds. `GET /ready` returns 200 only when the API can query PostgreSQL; it returns 503 otherwise. The Compose credentials are for local development only. Do not reuse them for a deployed instance.

Each schema change is recorded in `migrations/versions/` and applied with `alembic upgrade head`. Review generated migration files before applying them; autogeneration does not decide whether a schema change is correct for the business.

## Inventory movement API

The first write endpoint is:

```text
POST /organizations/{organization_id}/inventory/movements
```

It requires an `Idempotency-Key` header and an access token in `Authorization: Bearer <token>`. Obtain a 30-minute token by posting an email and password to `POST /auth/token`. The API derives the actor from the signed token instead of trusting a user identifier supplied by the client.

```json
{
  "product_id": "00000000-0000-0000-0000-000000000000",
  "warehouse_id": "00000000-0000-0000-0000-000000000000",
  "movement_type": "RECEIPT",
  "quantity": "10",
  "reason": "Supplier delivery",
  "reference": "PO-1001"
}
```

A new movement returns 201. A safe replay returns the original result with 200. Business and validation errors use a stable envelope containing `code`, `message`, `details`, and `request_id`.

Organization access is resolved from the authenticated user's membership. Inventory receipts and issues are available to `admin` and `warehouse_manager`; `salesperson` can read inventory but cannot create movements directly. Missing organization access returns 404 to avoid exposing private organization identifiers, while a known member without the required permission receives 403.

Run the initial checks with:

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m ruff format --check .
```

Catalog constraint tests use PostgreSQL when `DATABASE_URL` is set. They are skipped when no database URL is configured.
