# ADR 002: Gate recovery with approval and idempotency

- Status: Accepted
- Date: 2026-10-09

## Context

A sender-side timeout does not prove that delivery failed. The recipient may
have stored the report and then responded too slowly. Automatically retrying
from stale investigation evidence could therefore deliver the same report
twice.

The investigator uses an LLM to interpret evidence, but execution needs a
smaller and more predictable trust boundary. Approval can also be delayed, so
the evidence observed during investigation may no longer describe the current
delivery state when a person responds.

Concurrent retries create an additional race. A check followed by an insert is
unsafe because two requests can both observe no receipt before either creates
one.

## Decision

Keep recovery in a deterministic LangGraph workflow separate from the LLM
investigation loop.

The recovery workflow will:

1. Pause with LangGraph `interrupt()` and persist its state through a caller-
   supplied checkpointer.
2. Continue only after explicit human approval.
3. Recheck recipient receipts after approval.
4. Stop as `already_delivered` when a receipt is present.
5. Execute only the allow-listed `retry_delivery` action when no receipt is
   present.
6. Use the sender's stable delivery key for every retry.

The recipient will insert the receipt directly under a database `UNIQUE`
constraint on `delivery_key`. If that constraint reports a conflict, the
recipient loads and returns the original receipt. It rejects reuse of the same
key for a different report.

The database constraint, rather than an application-level preflight query, is
the authority that decides which concurrent request creates the receipt.

## Consequences

- A diagnosis or recommendation cannot directly cause an external side effect.
- Approval is necessary but not sufficient; recovery also requires a fresh
  state check.
- A repeated request with the same delivery identity is safe and observable.
- Recovery adds a database read and human latency, which is appropriate for a
  potentially duplicating operation.
- The in-memory checkpointer used in tests is not production persistence. A
  deployed workflow needs a durable checkpointer and authenticated approval
  metadata.
- New executable recovery actions must be explicitly added to the allow list
  and given their own safety rules.
