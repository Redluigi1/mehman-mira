# 03 — Task list

**This file is the source of truth for build status.** Tick boxes as work lands.
Details behind each task are in `docs/02-plan.md`.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (say why)

---

## Phase 0 — Scaffold and data

- [x] `backend/` skeleton: FastAPI app, `config.py` via pydantic-settings, `/health`
- [x] `frontend/` skeleton: Vite + React + TS + Tailwind, dev proxy to backend
- [x] Domain schemas — `domain/intent.py`: `Slot[T]`, `GuestIntent`, `Party`, `StayWindow`, `Budget`
- [x] Domain schemas — `domain/state.py`: `ConversationState`, `Stage`, `ReferentRegistry`, `Rejection`, `Conflict`
- [x] Domain schemas — `domain/supply.py`: `Property`, `RoomType`, `Policy`, `AddOn`, `RateCalendar`, `TaxRule`
- [x] Domain schemas — `domain/events.py` and `domain/trace.py` (`TurnTrace`, `ToolCall`, `GroundingVerdict`)
- [x] Policy value type with `known` / `not_applicable` / `unknown` — used everywhere
- [x] `data/seed.py` — seeded generator for the 16 non-curated properties
- [x] Hand-author 8 edge-case properties (see plan §8 for the exact list)
- [x] `data/loader.py` — JSON to SQLite at boot, with schema and indices
- [x] `data/repo.py` — query layer; `data/indexes.py` — city index + `AvailabilityIndex`
- [x] `store/conversations.py` — append-only event log, state as fold over events
- [x] Sanity test: load dataset, assert counts and that every planted edge case exists

## Phase 1 — Happy path

- [x] `llm/base.py` — `LLMClient` protocol (`complete_json`, `complete_text`)
- [x] `llm/claude_cli.py` — local Claude Code CLI on Haiku, JSON output, timeout, retry
- [x] `llm/replay.py` — record to `evals/fixtures/`, replay by prompt hash
- [x] `pipeline/extract.py` — `StateDelta` schema, extraction prompt, enum vocabularies
- [x] Deterministic date resolution from `date_expression` against an explicit `today`
- [x] `pipeline/reconcile.py` — apply delta with provenance; modify must not reset
- [x] `pipeline/policy.py` — `NextActionPolicy` per plan §3 table
- [x] `pipeline/respond.py` — Mira persona, response prompt
- [x] `pipeline/engine.py` — wire the loop, emit `TurnTrace`
- [x] `channels/cli.py` — run whole conversations in the terminal before any UI exists
- [x] End-to-end: the brief's Goa example produces a sensible multi-turn conversation
      (verified live via `backend/scripts/demo_goa.py` against the real Claude CLI —
      search → select → quote → factual question → price re-query → hold, all grounded)

## Phase 2 — Tools, pricing, grounding

- [x] `tools/registry.py` — name to (schema, callable), JSON schema export, arg validation
- [x] `search_properties` — filter cascade, exact and near-miss buckets, ranked
- [x] `check_availability`
- [x] `get_room_details`
- [x] `get_property_policies` — explicit unknown semantics
- [x] `calculate_quote` — deterministic breakdown per plan §5
- [x] Pricing unit tests against hand-computed fixtures (seasonal, weekend, extra bed, tax slab)
- [x] `create_booking_hold` — TTL plus idempotency key
- [x] `pipeline/ground.py` — `GroundingPacket` builder
- [x] Grounding validator — numbers, property names, room names must appear in the packet
- [x] Repair pass, then deterministic template fallback; record the verdict
- [x] Tool error handling — typed failures surface in the trace, never crash the turn

## Phase 3 — Edge cases

- [x] Conflict engine — capacity, budget, policy, min-stay, past dates, contradictions
      (`pipeline/conflicts.py`; hard conflicts recompute every turn, soft conflicts tied to
      `focused_option` are surfaced once then treated as acknowledged — Decision 014)
- [x] Relaxation lane — `date_shift`, `over_budget`, `capacity_split`, `policy_conflict`, `min_stay`
      (mechanism was already in `tools/search.py` from Phase 2; Phase 3 wires it into
      `RESOLVE_CONFLICT` via the conflict engine and extends it with `find_alternatives`)
- [x] `find_alternatives` — cheaper tier via sequenced relaxation (budget ceiling, then required
      amenities, then property type, then an honest unfiltered floor); wired to `WIDEN_OR_ASK`
      (Decision 015 — further date-shift/room-split widening beyond search's own ±2 days / 2
      rooms was deliberately not added, see decision log)
- [x] EC1 relative dates — `tests/test_edge_cases.py::test_ec1_...`
- [x] EC2 mid-conversation modification — also fixed `pipeline/dates.py` to parse relative
      night deltas ("one more night") and `reconcile.py` to recompute `check_out` from
      `check_in + nights` whenever nights changes without an explicit new check-out
- [x] EC3 no availability, date-shift offer — `test_ec3_...`
- [x] EC4 capacity conflict, split or upgrade — `test_ec4_...`
- [x] EC5 policy conflict, surfaced not silently filtered — `test_ec5_...`
- [x] EC6 unknown information, with `resolution_path` — `test_ec6_...`
- [x] EC7 impossible budget, honest floor — `test_ec7_...`
- [x] EC8 prompt injection in a guest message, deflected — deterministic regex guard in
      `pipeline/safety.py`, runs before extractor classification is trusted (Decision 001/015);
      `test_ec8_...` plus `tests/test_safety.py`
- [x] Test per edge case — `tests/test_edge_cases.py` (8), plus `test_conflicts.py` (11) and
      `test_alternatives.py` (4) for the underlying mechanisms

## Phase 4 — UI

- [x] `lib/api.ts` and `types.ts` mirrored by hand from the Pydantic models (`frontend/src/lib/`)
- [x] `Chat.tsx` — message list, composer, error surfacing (with retry)
- [x] `StatePanel.tsx` — the brief's field sketch, changed-this-turn highlighting (via each
      `Slot.source_turn`, no snapshot diffing needed), assumption and unknown markers
- [x] `TracePanel.tsx` — user act, next-action chip, tool cards with args/result/latency
      (expandable), grounding badge
- [x] `TurnTimeline.tsx` — click a turn to time-travel the console; "back to live" banner
- [x] Console collapse toggle (chat-only view)
- [x] Empty, loading and error states (boot-error screen, inline retry banner, typing indicator)
- [x] Confirm no chain of thought is rendered anywhere — the UI only ever renders
      `GroundingPacket`-sourced facts and structured trace data, never a reasoning trace
- [x] `channels/web.py` API surface wired to a real FastAPI app (`main.py` lifespan);
      design lifted from mehman.io's own visual language (warm cream/ink/purple/rust
      palette, Instrument Serif + Hanken Grotesk) at the user's request — see
      `frontend/src/index.css`
- [x] Verified live end-to-end against the real Claude CLI in the browser: search →
      select → quote → upsell → hold, time-travel, console collapse, all confirmed
      working. Caught and fixed 3 real bugs along the way (Decisions 017-019).

## Phase 5 — Bonuses

- [x] `suggest_addons` — eligibility rules, segment affinity, at most two with reasons
      (`tools/addons.py`; Decision 016)
- [x] Upsell timing rule — only after engagement with an option (`NextActionType.UPSELL`
      fires once between QUOTE and HOLD, Decision 016)
- [x] Referent registry wired into extraction and reconciliation (`pipeline/referents.py`,
      already wired into `engine.py`; extended for recovery phrases, see below)
- [x] Recovery behaviours: "yes", "too expensive", "whichever is better", "what about the
      other one?", "any cheaper option?" — `pipeline/referents.py` (`_OTHER_PHRASES`,
      `_DEFER_TO_RANKING_PHRASES`), `pipeline/act.py` (cheapest-first re-rank on a price
      objection); `tests/test_recovery.py`. Caught and fixed a real stale-quote bug along
      the way (Decision 017).
- [x] `evals/runner.py` — assertion types, scorecard maths, JSON and markdown output
- [x] Write 16 cases in `evals/cases/*.yaml` (happy paths, all 8 edge cases, all 5 recovery phrases)
- [x] Record fixtures, verify the suite runs deterministically with no API key
      (scripted extraction, not live-recorded — see `evals/README.md`)
- [x] Commit `evals/REPORT.md` (37/37 turns passing)

## Phase 6 — Ship

- [ ] **Resolve Decision 003** — a reviewer must be able to run this without a local Claude Code CLI
- [x] `README.md` — setup, architecture diagram, env vars, assumptions, known limitations
- [ ] `ENGINEERING_NOTE.md` — architecture, model choice, agent flow, state management, tool calling, hallucination prevention, tradeoffs, what to improve next (include the segmentation and RAG extensions, and the owner write-back loop)
- [ ] Fresh-clone smoke test on a clean checkout
- [ ] Demo script: happy path, 2+ edge cases, tool calls, state updates, key decisions
- [ ] Record the demo, no slides
- [ ] Send to `ashish@mehman.io`, subject `Mehman <> Assignment - Ayush Kumar + AI Engineer`

## Phase 7 — Optional, not attempted

- [ ] `escalate_to_property` tool plus escalations table
- [ ] Owner Console tab, mock owner replies
- [ ] Resume-on-owner-reply path producing an unprompted outbound message
- [ ] Write-back of the answer into the property record with `source: owner_verified`
- [ ] TTL fallback, dedup, rate limit

---

## Known limitations — not implemented, noted for future work

- [ ] **Kid vs. adult differentiation.** `Party` captures `adults` and per-child `children:
      list[ChildAge]` (`backend/app/domain/intent.py`), but capacity and pricing
      (`tools/capacity.py::rooms_needed_for`, `extra_beds_needed`) both collapse the party
      to `total_guests = adults + len(children)` and treat every head the same. A booking
      of "3 kids, 4 adults" is priced and room-matched as 7 identical guests — no reduced
      occupancy weight for children, no age-based free-stay or extra-bed-fee policy.
- [ ] **Analytics layer.** Conversations are event-sourced and durable (`store/
      conversations.py`) and every turn's trace is captured (`domain/trace.py`), but
      nothing aggregates across conversations. There is no persistence/dashboard for
      reviewing how well the agent performed after the fact (conversion rate, grounding
      failures over time, next-action accuracy in production vs. in `evals/`). The eval
      harness (`evals/runner.py`) scores fixed offline cases, not live traffic.
- [ ] **Single LLM backend.** `LLMClient` (`backend/app/llm/base.py`) is a protocol, but
      only one implementation exists — `llm/claude_cli.py`, which shells out to the local
      Claude Code CLI on Haiku. There is no Anthropic API-key client and no
      Vertex AI / Gemini / other-provider client, so this only runs on a machine with the
      Claude Code CLI installed and authenticated (see Decision 003). Swapping backends
      means writing a new class against the same protocol, not a redesign.

## Cross-cutting, do not skip

- [x] `ChannelAdapter` interface with `web` and `cli` real, `whatsapp` stubbed
      (`channels/web.py` — Decision 018; `tests/test_web_api.py`)
- [x] Structured logging with `conversation_id` and `turn_index` on every record
- [x] `.env.example` committed
- [ ] Every architectural change appended to `docs/04-decisions.md`
