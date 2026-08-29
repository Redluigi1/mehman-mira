# Mira — a guest-facing hotel booking agent

A working booking agent that understands a guest in natural conversation, maintains
state across turns, calls deterministic tools over a real catalogue, refuses to invent
facts, and moves toward a booking.

Built as a case study for **Mehman.io** (AI Engineer). Assignment brief distilled in
[`docs/00-brief.md`](docs/00-brief.md).

> **Status: planning complete, implementation not started.**
> This README is a stub. It becomes the real setup document in Phase 6.

## How it works, in one diagram

```
guest message
  -> LLM #1   structured state delta (JSON, schema-constrained)
  -> code     reconcile state, detect conflicts
  -> code     next-action policy: ask, search, answer, quote, upsell, hold
  -> code     tool execution (search, availability, policy, pricing, hold)
  -> code     build GroundingPacket, the only facts the response may state
  -> LLM #2   natural response, restricted to the packet
  -> code     grounding validator, then repair or template fallback
  -> reply + full trace
```

Two narrow LLM calls per turn. Everything between them is typed, deterministic and
unit-tested. Every number the guest sees was computed in Python.

## Documentation

| File | What it holds |
| --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | Orientation and invariants for assistant sessions |
| [`docs/00-brief.md`](docs/00-brief.md) | The assignment, distilled |
| [`docs/01-proposal.md`](docs/01-proposal.md) | Architecture rationale, and what was rejected |
| [`docs/02-plan.md`](docs/02-plan.md) | Detailed implementation plan |
| [`docs/03-tasks.md`](docs/03-tasks.md) | Phase-by-phase checklist — live build status |
| [`docs/04-decisions.md`](docs/04-decisions.md) | Numbered decision log |

## Setup

To be written in Phase 6, covering: prerequisites, backend and frontend install, dataset
build, environment variables, running the CLI and the web UI, and running the eval suite.
