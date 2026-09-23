# 0007 - Authorize organization actions with fixed role policies

Date: 2026-09-23
Status: Accepted

## Context

Authentication identifies a user but does not prove that the user belongs to the organization in a request or may perform a particular action there. Putting role comparisons in every endpoint would duplicate policy and make newly introduced roles easy to authorize accidentally.

## Decision

Resolve access from the authenticated user and the organization membership on each protected request. Represent business capabilities as named permissions and map the initial `admin`, `warehouse_manager`, and `salesperson` roles to fixed permission sets in application code. Unknown roles receive no permissions by default.

Return 404 when the user has no membership in the requested organization so private organization identifiers cannot be enumerated. Return 403 when a member can access the organization but lacks the permission for an action. Keep authentication failures as 401.

Inventory receipt and issue use distinct permissions even though they currently share one endpoint. Salespeople will eventually create sales; the sales workflow, rather than a direct inventory permission, will produce the corresponding stock movement.

## Alternatives considered

- Compare role names directly in every endpoint: initially simple, but it duplicates policy and couples transport code to role definitions.
- Store configurable roles and permissions in normalized database tables now: flexible, but adds management workflows and migration complexity before a client needs custom roles.
- Store permissions in access tokens: removes a lookup, but organization access and permission changes can remain stale until token expiration.
- Return 403 for every missing membership: semantically reasonable, but confirms that a private organization identifier exists.

## Consequences

Permission checks are deny-by-default and reusable across modules. Adding a fixed role or capability requires a code change and deployment. If customers later need custom roles, the permission vocabulary can remain while role assignments move to database tables.

Platform operators are not organization roles and do not bypass these policies. A separate, audited support-access design will be required before platform administration is implemented.
