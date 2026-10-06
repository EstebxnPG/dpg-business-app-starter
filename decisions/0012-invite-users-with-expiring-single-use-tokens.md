# 0012 - Invite users with expiring single-use tokens

Date: 2026-10-05
Status: Accepted

## Context

Organization administrators need to add employees without choosing or learning their passwords. The same person may belong to multiple organizations with a different role in each. Email delivery is not yet integrated, but membership onboarding must not depend on manually inserting users or sharing credentials.

## Decision

Allow members with `members:manage` to create invitations containing an email and organization role. Generate a cryptographically random token, return it once during the MVP, and store only its SHA-256 hash. Revoke previous pending invitations for the same organization and email, expire invitations after 24 hours, and lock the invitation row while accepting it so concurrent attempts cannot both succeed.

For a new email, require the invited person to choose a password and create the user and membership atomically. For an existing email, require a valid access token for that exact user and create only the new membership; never replace the existing password. Mark the invitation accepted in the same transaction.

Keep email delivery outside the invitation transaction. A future Outbox event and delivery adapter will send the acceptance link without changing membership rules.

## Alternatives considered

- Let administrators create employee passwords: simpler, but administrators could impersonate employees and passwords would be shared insecurely.
- Create duplicate users per organization: avoids cross-organization membership logic, but fragments identity and forces one person to maintain multiple accounts.
- Store invitation tokens in plaintext: easy to compare, but a database leak would expose active invitations.
- Accept existing-user invitations without authentication: possession of a leaked invitation link could attach an organization to the wrong active session or disclose account existence.

## Consequences

One account can safely join multiple organizations while roles remain membership-specific. Invitation acceptance is retry-safe at the business level because used, revoked, or expired tokens are rejected. Until email delivery exists, the returned plaintext token must be treated as a secret and shared only through a trusted development channel.
