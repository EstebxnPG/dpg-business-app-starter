# 0008 - Coordinate business actions in application use cases

Date: 2026-09-23
Status: Accepted

## Context

HTTP endpoints initially coordinated permissions, actor identity, command construction, and calls to inventory domain logic. Future entry points such as sales workflows, imports, scheduled jobs, or message consumers must not duplicate that coordination or bypass authorization accidentally. Domain inventory rules should not depend on HTTP or know every business role.

## Decision

Introduce an application use-case layer between transport adapters and domain services. A manual inventory movement use case verifies that the membership belongs to the command's organization, requires the permission associated with the movement type, derives the actor from the trusted membership, and then calls the inventory service.

Routers remain responsible for HTTP concerns such as headers, status codes, request models, and error responses. The inventory service remains responsible for stock invariants, idempotency, persistence, and transactional consistency.

Different business actions may use the same domain capability through different use cases. For example, a future sale will require `sales:create` and produce a referenced stock issue; it will not grant the salesperson permission to create arbitrary manual inventory issues.

## Alternatives considered

- Keep coordination in routers: fewer files initially, but non-HTTP callers could bypass or duplicate security rules.
- Put role checks directly in the inventory service: protects every call, but couples domain rules to application roles and prevents legitimate workflows such as sales from using inventory through their own authorization policy.
- Build a generic command bus now: potentially useful at larger scale, but unnecessary abstraction for the current number of use cases.

## Consequences

Entry points become thinner and application actions gain a reusable security boundary. There is an additional layer and command type, but each has a distinct responsibility. Transaction ownership still resides in the inventory service for the current single-domain operation; cross-module use cases may require moving transaction coordination outward when they are implemented.
