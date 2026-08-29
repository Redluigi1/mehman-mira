# CLAUDE.md — orientation for any assistant session on this repo

## What this is

**Mira** — a simplified version of Mehman.io's guest-facing hotel-booking AI agent.
This is a **take-home case study for an AI Engineer role at Mehman.io**. Submission goes
to `ashish@mehman.io` with subject `Mehman <> Assignment - {Name + Role}`.

Owner: Ayush Kumar (`ayush171003@gmail.com`).

## Read these first, in order

| File | What it holds |
| --- | --- |
| `docs/00-brief.md` | The assignment requirements, distilled from the company's PDF |
| `docs/01-proposal.md` | The architecture proposal + why, including options rejected |
| `docs/02-plan.md` | The detailed implementation plan (data model, pipeline, tools, UI) |
| `docs/03-tasks.md` | Phase-by-phase task checklist — **the live status of the build** |
| `docs/04-decisions.md` | Numbered decision log (ADR style) with status per decision |

The **original assignment PDF** is at `reference/Mehman_Case_Study.pdf` (gitignored;
original also at `C:\Users\AYUSH\Downloads\Mehman __ Case Study.pdf`).

## Non-negotiable invariants

These were decided deliberately. Do not quietly change them — if a change looks right,
raise it and add a numbered entry to `docs/04-decisions.md`.

1. **The LLM does not run the agent loop.** Exactly two narrow LLM calls per turn
   (structured state extraction, then response generation). Everything between them —
   reconciliation, conflict detection, next-action choice, search, pricing, ranking —
   is deterministic, typed, unit-testable Python.
2. **Nothing is stated to the guest that did not come from a tool result.** The response
   model sees only a `GroundingPacket`; a validator checks the draft against it afterwards.
3. **Pricing is deterministic application logic.** The LLM never computes a number.
4. **Conversation state is durable and event-sourced.** Guest messages and system events
   are the same kind of input. This is the precondition for async human-in-the-loop
   escalation (see Decision 011) and is free now, expensive to retrofit.
5. **Unknown means unknown.** Dataset fields distinguish `value` / `not_applicable` /
   `unknown`. The agent says it does not know rather than guessing.
6. **No agent framework, no vector DB, no RAG.** The data is structured; retrieval here
   is a query. Owning the ~400-line loop is the point being graded.
7. **Guest segmentation is a soft hint, never a hard filter, and never spoken aloud.**
   Never infer age. Only use explicitly stated signals.

## Stack

- Backend: Python 3.11, FastAPI, Pydantic v2, SQLite (seeded from JSON in git)
- Frontend: Vite + React + TypeScript + Tailwind
- LLM: pluggable `LLMClient`. The default dev backend is the **local Codex CLI on
  GPT-5.6 Terra** (`codex exec --model gpt-5.6-terra`), with low reasoning effort for
  local demo latency. Claude CLI and the direct Vertex AI adapter are optional. Selection
  is through `LLM_BACKEND` and `LLM_MODEL` — see Decisions 003 and 024.

## Working conventions

- Update `docs/03-tasks.md` checkboxes as work lands. It is the source of truth for status.
- Any architectural change gets a numbered entry in `docs/04-decisions.md`.
- Keep the dataset JSON human-readable and in git; SQLite is a build artifact, never committed.
- Commit messages: plain, imperative, scoped (`data: seed Goa properties`).
