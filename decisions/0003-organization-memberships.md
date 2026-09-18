# 0003 - Assign access through organization memberships

Date: 2026-09-18
Status: Accepted

## Context

A person may work for more than one organization and have different responsibilities in each. Inventory data belongs to an organization, while a person's account can exist independently of any one organization. A global role on the user account would grant the same access everywhere.

## Decision

Keep users and organizations as separate entities. Represent access with a membership linking one user to one organization and assigning that membership a role. Authorization for an inventory request must use both the authenticated user and the organization in which the request is being made. Products, warehouses, balances, and movements must remain within that organization's data boundary.

Movement history records the responsible user's identity and the organization in which the operation occurred. Removing or changing a membership later must not erase the historical attribution of confirmed movements.

## Alternatives considered

- Store an organization and role directly on each user: simple for one company, but cannot express different roles across companies without duplicate accounts.
- Store a global role on each user: would incorrectly apply the same permissions in every organization.
- Trust an organization identifier supplied by the client: would allow cross-organization access unless the server checks the user's membership on every protected operation.

## Consequences

One account can work in multiple organizations with different access. Each request needs an explicit organization context and a membership check. Data creation and lookup must also enforce that referenced products and warehouses belong to that organization. The exact role and permission tables can be defined when the first protected workflow is implemented.
