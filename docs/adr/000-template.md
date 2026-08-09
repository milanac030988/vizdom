# ADR-NNN: Short Title (what is decided, not what the problem is)

## Status

Proposed | Accepted | Accepted (implemented) | Deprecated | Superseded by ADR-NNN

## Date

YYYY-MM-DD

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| YYYY-MM-DD | 1.0 | Initial version |

## Context

The forces at play, stated so a reader who was not there can judge the decision:
what problem appeared, what evidence exists (measurements, failures observed,
constraints), and which ranked driver it touches. Prefer facts over adjectives —
"a 3B model called a top-left element 'top right'" beats "models are unreliable".

## Considered options

### Option A — ...

- ✓ what it buys
- ✗ what it costs

### Option B — ...

...

Keep the rejected options here with their real trade-offs. An ADR whose
alternatives are strawmen documents nothing.

## Decision

What was chosen, in the imperative, and *why this one* against the drivers. If a
weighted comparison was used, show the matrix and say plainly which criteria the
winner loses on — the accepted cost is part of the decision.

## Consequences

**Positive**

- ...

**Negative / limits**

- The honest list: what is now harder, what is not covered, what could still go
  wrong. A `Proposed` ADR that defers work should also name the **trigger
  conditions** that would make it necessary — that is what distinguishes
  deferral from drift (see ADR-025 for the pattern).

## References

- Related ADRs, the code that implements this, the measurement that justifies it.
