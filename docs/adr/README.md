# Architecture Decision Records

Long-form decisions that affect more than one PR's worth of code or
that establish a contract the rest of the repo will rely on.

## Why a separate `docs/adr/`?

Two layers of decision logging coexist on this repo:

| Layer | Location | Scope |
|---|---|---|
| ADR-lite (per-session) | `.ai_bridge/DECISIONS.md` | Tactical decisions during a session — "we picked Streamlit over FastAPI for cockpit MVP". Append-only. |
| Decision log (per cycle) | `docs/learning/decision_log.md` | Cross-session learnings keyed `DL-NNN` — "two pipeline tracks coexist". Append-only. |
| **Architecture Decision Records** | **`docs/adr/`** (this dir) | **Contracts that span multiple PRs / files / future cycles. Each ADR is a discrete proposal with status, alternatives, consequences, rollback.** |

When does an ADR-lite or DL entry get promoted to a full ADR?

- The decision affects **>1 file** or **>1 future PR's** semantics.
- The decision establishes a **schema** or **API contract**.
- The decision needs **rollback documentation** because it's
  genuinely costly to undo.
- A future agent / human reading just the chat won't be able to
  derive the contract.

ADRs live here, are numbered, never deleted. When a decision is
superseded, the superseding ADR's `Status:` references the
predecessor and the predecessor's `Status:` becomes
`Superseded by ADR-NNN`.

## Index

| ID | Title | Status | Date |
|---|---|---|---|
| [ADR-001](ADR-001-validation-cockpit-mutation-surface.md) | Validation Cockpit Mutation Surface | Proposed | 2026-05-08 |

## ADR template

```markdown
# ADR-NNN — <short title>

> **Status:** Proposed | Accepted | Superseded by ADR-MMM | Rejected
> **Date:** YYYY-MM-DD
> **Author:** <agent or human>
> **Related:** <files / docs / other ADRs>

## 1. Context
<why this decision is needed now>

## 2. Decision
<what was decided, in detail>

## 3. Alternatives considered
<and why each was rejected>

## 4. Consequences
### Positive
### Negative / costs
### Reversibility

## 5. Rollback procedure
<exact steps if the decision proves wrong>

## 6. References
```
