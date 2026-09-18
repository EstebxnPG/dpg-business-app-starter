# 0001 - Build a reusable backend through an inventory reference workflow

Date: 2026-09-18
Status: Accepted

## Context

DPG wants a reusable foundation for operational applications and a source of reliable data for future analytics. There is no confirmed pilot client or validated requirement to replace an existing POS. Building a generic enterprise framework without an application workflow would leave its boundaries untested.

## Decision

Build the starter as a modular backend, using inventory control as its first reference application. The first complete workflow is product creation, stock receipt, stock issue, balance lookup, and movement history under organization-specific access control. Keep inventory-specific rules inside the inventory module and introduce shared capabilities only when the workflow demonstrates a need for them.

Sales registration, POS replacement, and analytics are outside this first workflow. DPG Data Platform may later consume this application's data as well as data from POS and spreadsheet sources.

## Alternatives considered

- Build a POS from the start: this adds sales, payment, and invoicing responsibilities before the operational foundation has been proven.
- Build a generic backend framework first: this risks abstractions that have no tested business use.
- Make inventory the entire product: this would constrain the intended reuse for other operational applications.

## Consequences

The first milestone has a concrete acceptance case and exposes important rules around stock consistency, traceability, and organization isolation. It will not answer questions about revenue or salespeople until sales data is integrated or a sales module exists. The boundary between reusable core and inventory remains provisional and should be reviewed after another use case is implemented.
