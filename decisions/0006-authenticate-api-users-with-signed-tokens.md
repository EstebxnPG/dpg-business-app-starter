# 0006 - Authenticate API users with signed access tokens

Date: 2026-09-23
Status: Accepted

## Context

The inventory API previously trusted an `X-User-Id` supplied by the client. Anyone could impersonate another user by changing that header, so it was useful only while exercising the domain rules locally. The API needs a verified identity before organization membership and role checks can be meaningful.

## Decision

Store passwords as Argon2 hashes and never store the original password. Exchange valid credentials for a short-lived JWT access token signed by the application. Derive the actor from the token subject and query the database on protected requests to confirm that the user still exists and is active.

Use a server-side secret of at least 32 characters with the fixed HS256 algorithm and issuer. Tokens expire after 30 minutes. Return the same authentication error for unknown users, incorrect passwords, invalid tokens, and inactive users so the API does not reveal which account state failed.

Authentication proves who the user is. Organization memberships and permissions remain separate authorization rules.

## Alternatives considered

- Keep trusting a user ID header: simple, but it provides no proof of identity.
- Use opaque server-side sessions: they support immediate revocation naturally, but require session storage and cookie or token lifecycle management that the current API does not yet need.
- Use an external identity provider: valuable for mature products and social or enterprise login, but adds operational and product complexity before the first workflow is validated.
- Put roles and memberships only in the JWT: this avoids a database read, but permissions can remain stale until the token expires and organization access becomes harder to revoke promptly.

## Consequences

Protected endpoints no longer trust actor IDs from clients. Password verification is intentionally expensive, and protected requests currently add a user lookup that allows deactivation to take effect immediately. JWT contents are signed but not encrypted, so secrets and sensitive business data must never be placed in the payload.

The first version has no refresh tokens, password reset, rate limiting, or user provisioning endpoint. Those capabilities should be introduced with their actual workflows. Authorization must still reject users who lack the required membership or permission.
