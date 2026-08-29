# 03 — Task list

**This file is the source of truth for build status.** Tick boxes as work lands.
Details behind each task are in `docs/02-plan.md`.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (say why)

---

## Phase 0 — Scaffold and data (4h)

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

## Phase 1 — Happy path (6h)

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

## Phase 2 — Tools, pricing, grounding (5h)

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

## Phase 3 — Edge cases (4h)

- [ ] Conflict engine — capacity, budget, policy, min-stay, past dates, contradictions
- [ ] Relaxation lane — `date_shift`, `over_budget`, `capacity_split`, `policy_conflict`, `min_stay`
- [ ] `find_alternatives` — date shift, nearby property, room split, cheaper tier
- [ ] EC1 relative dates
- [ ] EC2 mid-conversation modification
- [ ] EC3 no availability, date-shift offer
- [ ] EC4 capacity conflict, split or upgrade
- [ ] EC5 policy conflict, surfaced not silently filtered
- [ ] EC6 unknown information, with `resolution_path`
- [ ] EC7 impossible budget, honest floor
- [ ] EC8 prompt injection in a guest message, deflected
- [ ] Test per edge case

## Phase 4 — UI (5h)

- [ ] `lib/api.ts` and `types.ts` generated or mirrored from the Pydantic models
- [ ] `Chat.tsx` — message list, composer, error surfacing
- [ ] `StatePanel.tsx` — the brief's field sketch, changed-this-turn highlighting, assumption and unknown markers
- [ ] `TracePanel.tsx` — user act, next-action chip, tool cards with args/result/latency, grounding badge
- [ ] `TurnTimeline.tsx` — click a turn to time-travel the console
- [ ] Console collapse toggle (chat-only view)
- [ ] Empty, loading and error states
- [ ] Confirm no chain of thought is rendered anywhere

## Phase 5 — Bonuses (4h)

- [ ] `suggest_addons` — eligibility rules, segment affinity, at most two with reasons
- [ ] Upsell timing rule — only after engagement with an option
- [ ] Referent registry wired into extraction and reconciliation
- [ ] Recovery behaviours: "yes", "too expensive", "whichever is better", "what about the other one?", "any cheaper option?"
- [ ] `evals/runner.py` — assertion types, scorecard maths, JSON and markdown output
- [ ] Write 16 cases in `evals/cases/*.yaml` (happy paths, all 8 edge cases, all 5 recovery phrases)
- [ ] Record fixtures, verify the suite runs deterministically with no API key
- [ ] Commit `evals/REPORT.md`

## Phase 6 — Ship (2h)

- [ ] **Resolve Decision 003** — a reviewer must be able to run this without a local Claude Code CLI
- [ ] `README.md` — setup, architecture diagram, env vars, assumptions, known limitations
- [ ] `ENGINEERING_NOTE.md` — architecture, model choice, agent flow, state management, tool calling, hallucination prevention, tradeoffs, what to improve next (include the segmentation and RAG extensions, and the owner write-back loop)
- [ ] Fresh-clone smoke test on a clean checkout
- [ ] Demo script: happy path, 2+ edge cases, tool calls, state updates, key decisions
- [ ] Record the 5-minute demo, no slides
- [ ] Send to `ashish@mehman.io`, subject `Mehman <> Assignment - Ayush Kumar + AI Engineer`

## Phase 7 — Optional, only if hours remain

- [ ] `escalate_to_property` tool plus escalations table
- [ ] Owner Console tab, mock owner replies
- [ ] Resume-on-owner-reply path producing an unprompted outbound message
- [ ] Write-back of the answer into the property record with `source: owner_verified`
- [ ] TTL fallback, dedup, rate limit

---

## Cross-cutting, do not skip

- [ ] `ChannelAdapter` interface with `web` and `cli` real, `whatsapp` stubbed
- [x] Structured logging with `conversation_id` and `turn_index` on every record
- [x] `.env.example` committed
- [ ] Every architectural change appended to `docs/04-decisions.md`
