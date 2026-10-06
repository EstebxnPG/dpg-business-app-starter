# 0011 - Bootstrap the first organization through a local command

Date: 2026-10-05
Status: Accepted

## Context

Every protected API operation requires an authenticated user with an organization membership. A new installation therefore needs a trusted way to create its first organization and administrator before normal authorization can operate. A public bootstrap endpoint would allow an unauthenticated caller to claim administrative access unless deployment-specific controls were added.

## Decision

Provide a local administrative command that creates the organization, user, and `admin` membership in one PostgreSQL transaction. Read the password interactively with hidden input and confirmation so it is not placed in command history or process arguments. Normalize the email, require a minimum password length, hash it with Argon2 before opening the transaction, and reject existing user emails.

Use this command for controlled development and initial deployments. Do not expose bootstrap through the HTTP API. Customer self-service signup, invitations, existing-user membership assignment, and platform support access remain separate future workflows.

## Alternatives considered

- Expose an unauthenticated registration endpoint: convenient, but unsafe without invitation, verification, abuse prevention, and ownership policies.
- Seed a fixed administrator through a migration: repeatable, but would place credentials or credential-generation behavior in schema deployment and create secret-management risk.
- Insert records manually with SQL: possible, but easy to create an unhashed password, omit the membership, or leave partial data.
- Accept the password as a command argument: automation-friendly, but leaks it through shell history and process inspection.

## Consequences

Fresh installations can establish their first tenant safely without bypassing the data model. The command requires direct execution in a trusted environment with `DATABASE_URL` configured. It is intentionally not the long-term customer onboarding experience and does not attach an existing user to a new organization.
