# 02 — Implementation plan

The *what and how*. Rationale lives in `docs/01-proposal.md`; status lives in
`docs/03-tasks.md`.

---

## 1. Repository layout

```
mehman-mira/
  README.md                  # setup, architecture, env vars, assumptions, limitations
  CLAUDE.md                  # orientation for assistant sessions
  ENGINEERING_NOTE.md        # the ~1 page deliverable
  docs/                      # brief, proposal, plan, tasks, decisions
  reference/                 # original assignment PDF (gitignored)

  backend/
    app/
      main.py                # FastAPI app, routes, error handlers
      config.py              # settings via pydantic-settings
      domain/
        intent.py            # Slot[T], GuestIntent, PartyProfile, segmentation
        state.py             # ConversationState, Stage, ReferentRegistry
        supply.py            # Property, RoomType, Policy, AddOn, RateCalendar
        events.py            # ConversationEvent union (guest msg, system, owner reply)
        trace.py             # TurnTrace, ToolCall, GroundingVerdict
      pipeline/
        extract.py           # LLM #1: message -> StateDelta
        reconcile.py         # delta -> state, provenance, conflict detection
        policy.py            # NextActionPolicy: state -> NextAction
        act.py               # tool dispatch + result validation
        ground.py            # GroundingPacket build + response validator
        respond.py           # LLM #2: packet -> natural language
        engine.py            # the ~400 line loop that wires the above
      tools/
        registry.py          # name -> (schema, callable), JSON schema export
        search.py  availability.py  pricing.py  policy_tool.py
        addons.py  alternatives.py  booking.py
      data/
        loader.py            # JSON -> SQLite at boot
        repo.py              # query layer (the interface that survives Postgres)
        indexes.py           # city index, AvailabilityIndex
      llm/
        base.py              # LLMClient protocol
        codex_cli.py         # local Codex CLI, GPT-5.6 Terra (dev default)
        claude_cli.py        # optional legacy local backend
        vertex.py            # direct Vertex AI backend, API key or ADC
        anthropic_api.py     # API-key client (deferred, Decision 003)
        replay.py            # record/replay fixtures for deterministic evals
      channels/
        base.py              # ChannelAdapter
        web.py  cli.py  whatsapp_stub.py
      store/
        conversations.py     # durable event-sourced conversation store
    tests/
    data/
      properties.json        # source of truth, human-readable, in git
      rates.json  inventory.json  addons.json
      seed.py                # generator for the non-curated properties

  frontend/                  # Vite + React + TS + Tailwind
    src/
      components/Chat.tsx  StatePanel.tsx  TracePanel.tsx  TurnTimeline.tsx
      lib/api.ts  types.ts

  evals/
    cases/*.yaml             # 16 scripted conversations with assertions
    runner.py                # scorecard producer
    fixtures/                # recorded LLM responses for replay
    REPORT.md                # committed scorecard
```

---

## 2. Domain model

### 2.1 Guest side

Every extracted field is wrapped so provenance survives:

```python
class Slot(BaseModel, Generic[T]):
    value: T | None
    confidence: float          # 0..1, from the extractor
    source_turn: int | None    # which turn set it
    asked_count: int = 0       # times we asked; blocks re-asking
    is_assumption: bool = False
```

```python
class GuestIntent(BaseModel):
    destination:   Slot[Destination]        # {city, area?, flexible: bool}
    stay:          Slot[StayWindow]         # {check_in, check_out, nights, flex_days}
    party:         Slot[Party]              # {adults, children:[{age}], rooms_needed?}
    budget:        Slot[Budget]             # {amount, basis: per_night|total, hard: bool}
    property_prefs:      Slot[list[PropertyType]]
    room_prefs:          Slot[RoomPrefs]    # bed type, view, private pool, connecting
    amenities_required:  Slot[list[str]]
    amenities_nice:      Slot[list[str]]
    policy_needs:        Slot[PolicyNeeds]  # smoking, pets, early ci, late co, party
    special_requirements: Slot[list[str]]   # accessibility, dietary, decor
    trip_purpose:  Slot[TripPurpose]
    occasion:      Slot[Occasion]           # only when explicitly stated
    # derived, never asked:
    party_type:    PartyType                # solo/couple/family_with_kids/friends/...
```

```python
class ConversationState(BaseModel):
    conversation_id: str
    turn_index: int
    stage: Stage                 # discover|search|present|negotiate|confirm|held
    intent: GuestIntent
    shortlist: list[OptionRef]
    referents: ReferentRegistry  # ordinal + id for every option shown
    focused_option: OptionRef | None
    quote: Quote | None
    hold: BookingHold | None
    rejected: list[Rejection]    # {option_id, reason: price|location|capacity|...}
    conflicts: list[Conflict]
    open_questions: list[str]
    unknowns_surfaced: list[UnknownFact]   # carries resolution_path (Decision 011)
```

### 2.2 Supply side

```
Property     id, name, city, area, geo, type, star_tier, description,
             amenities[], images[], check_in_time, check_out_time
RoomType     id, property_id, name, base_occupancy, max_occupancy,
             max_adults, max_children, extra_bed_allowed, extra_bed_price,
             bed_config, size_sqft, view, amenities[], units_total
RateCalendar (room_type_id, date) -> price, min_stay, closed_to_arrival
Inventory    (room_type_id, date) -> units_available
Policy       property_id, key, value | not_applicable | unknown, source
AddOn        id, scope(property|global), category, name, price, price_basis,
             eligibility, segment_affinity[]
TaxRule      slab thresholds -> GST %, plus fixed fees
```

**Unknown semantics are load-bearing.** A policy value is one of:
`{"status": "known", "value": ...}` / `{"status": "not_applicable"}` /
`{"status": "unknown"}`. Nothing is implicitly false.

---

## 3. The turn pipeline

### Stage 1 — Extract (LLM call #1)

Input: last N turns (windowed), a compact rendering of current state, today's date and
timezone, and the enum vocabularies. Output: schema-constrained `StateDelta`:

```python
class StateDelta(BaseModel):
    user_act: UserAct        # new_request|modify|answer|select|objection|question|chitchat|other
    set_fields: dict[str, Any]
    clear_fields: list[str]
    referent_mentions: list[str]   # "the villa", "the second one"
    date_expression: str | None    # raw phrase; code resolves it
    objection: Objection | None    # {kind: price|location|..., detail}
    confidence: dict[str, float]
```

The model proposes; it does not decide. Relative dates come back as the raw phrase and are
resolved deterministically against an explicit `today` anchor.

### Stage 2 — Reconcile (deterministic)

Applies the delta with provenance. `modify` updates in place, never resets. Runs conflict
detection: party size vs capacity, budget vs cheapest available, policy needs vs property
policy, min-stay vs requested nights, dates in the past, contradictory statements.

### Stage 3 — Decide (deterministic policy)

A readable table from state to a single `NextAction`:

| Condition | Action |
| --- | --- |
| Destination missing | `ASK(destination)` |
| Dates missing or unresolvable | `ASK(dates)` |
| Party size missing | `ASK(party)` |
| Minimum viable set present, no search yet | `SEARCH` |
| Search returned only near-misses | `PRESENT_ALTERNATIVES` |
| Search returned nothing at all | `WIDEN_OR_ASK` |
| Results present, none shown yet | `PRESENT` |
| Guest raised an objection | `REFINE_SEARCH` |
| Guest asked a factual question | `ANSWER_FACTUAL` |
| Fact not in dataset | `SURFACE_UNKNOWN` |
| Unresolved conflict | `RESOLVE_CONFLICT` |
| Option focused, quote not built | `QUOTE` |
| Quote accepted | `UPSELL` then `HOLD` |
| Off-topic or injection attempt | `DEFLECT` |

**Minimum viable search set = destination + dates + party size.** Everything else is
optional refinement. The agent must not interrogate; budget and preferences are inferred
from results and asked only when they would change the answer.

### Stage 4 — Act (tools)

Deterministic Python. Each tool has a JSON schema, validated args, a typed result, and
emits a `ToolCall` trace record with args, result summary and latency.

| Tool | Purpose |
| --- | --- |
| `search_properties` | city + dates + party + filters -> `{exact[], near_miss[]}` |
| `check_availability` | units available for a room type over a date range |
| `get_room_details` | full room record, amenities, capacity, bed config |
| `get_property_policies` | policy lookup with explicit unknown semantics |
| `calculate_quote` | deterministic price breakdown (see 5) |
| `suggest_addons` | contextual add-ons ranked by segment and stage (Bonus 1) |
| `find_alternatives` | date shift, nearby property, room split, cheaper tier |
| `create_booking_hold` | hold with TTL and idempotency key |

At least 3 were required; 8 are planned, all genuinely used by the policy.

### Stage 5 — Ground

Tool results compile into a `GroundingPacket`: an allow-list of facts (ids, names, numbers,
dates, policy values, explicit UNKNOWNs) plus the `NextAction`. Nothing else reaches the
response model.

### Stage 6 — Respond (LLM call #2)

Persona Mira, given the packet, the next action, and tone hints derived from
`party_type` / `trip_purpose`. Then the validator: every number, property name and room
name in the draft must appear in the packet. Fail -> one repair pass -> deterministic
template fallback. The verdict (`clean` / `repaired` / `fallback`) is recorded and shown
in the UI.

### Stage 7 — Persist

Append the `TurnTrace` and the resulting state snapshot to the event log.

---

## 4. Search, pruning and ranking

Filter cascade, cheapest predicate first: `city index -> availability -> capacity ->
budget ceiling -> required amenities -> policy compatibility -> score`.

Relaxation thresholds (configurable): date shift up to ±2 days, budget overshoot up to
20%, capacity satisfied by splitting into at most 2 rooms. Inside a threshold a candidate
becomes a `near_miss` with a typed `Relaxation`; outside it, it is dropped.

Ranking is a transparent weighted score with per-signal contributions logged, so the trace
panel can show *why* something ranked first:

```
score = w_fit*constraint_fit + w_price*price_fit + w_seg*segment_affinity
      + w_amen*amenity_overlap + w_qual*quality - penalty(relaxations)
```

`AvailabilityIndex` holds sorted intervals per room type with binary search. At this scale
a linear scan would do; the interface is what matters.

---

## 5. Pricing engine (fully deterministic)

```
per-night rate from RateCalendar (seasonal / weekend aware)
  + extra-bed charges for guests above base occupancy
  x nights
  = room subtotal
  + add-ons (per_stay | per_night | per_person basis)
  - discounts (length-of-stay, early bird)
  + taxes (GST slab on the per-night tariff) + fixed fees
  = total
```

Returns a line-item breakdown that the UI renders and the response model may only quote,
never recompute. Unit-tested against hand-computed fixtures. The LLM never produces a
number.

---

## 6. Upsell (Bonus 1)

`suggest_addons` filters by eligibility (an airport pickup needs an airport, early check-in
needs the room free the prior night), ranks by `segment_affinity x stage x price fit`, and
returns at most two with a one-line reason each. Offered **after** the guest has engaged
with an option, never during discovery — pushing add-ons before a room is chosen is the
failure mode.

---

## 7. Conversation recovery (Bonus 2)

Backed by the referent registry and the rejection log:

| Guest says | Mechanism |
| --- | --- |
| "yes" | resolve against the last `pending_confirmation` in state |
| "too expensive" | record `Rejection(price)`, re-search with a learned ceiling |
| "whichever is better" | agent picks by score and *states the reason* |
| "what about the other one?" | referent registry ordinal lookup |
| "any cheaper option?" | re-rank within the same constraint set |

---

## 8. Dataset

**24 properties across 8 cities** (Goa dense, since the brief's example is Goa; plus
Jaipur, Udaipur, Rishikesh, Manali, Coorg, Lonavala, Alibaug), 2–5 room types each,
roughly 70 room types. Generated by a seeded script for reproducibility, with about 8
hand-authored properties that plant the edge cases:

- one booked out to exactly +2 days from a demo date (the date-shift case)
- one with `pool_heated: unknown` (the unknown-information case)
- one no-smoking-only property (the policy-conflict case)
- one room capped at 2 guests (the capacity-conflict case)
- one villa sleeping 8 (the capacity-split resolution)
- one with a sharp seasonal price cliff (pricing correctness)
- one with a 3-night minimum stay
- one fully booked across the demo window

JSON is the source of truth and lives in git; SQLite is built at boot and never committed.
Search returns only top-N to the LLM regardless of catalogue size.

---

## 9. Persistence and events

Conversations are an append-only event log keyed by `conversation_id`. Event types:
`GuestMessage`, `SystemEvent`, and (reserved) `OwnerReply`. State at turn *n* is a fold
over events up to *n* — which gives time travel in the UI almost free, and is the
precondition for async escalation (Decision 011).

---

## 10. API surface

```
POST /conversations                 -> {conversation_id}
POST /conversations/{id}/messages   -> {reply, state, next_action, trace, errors}
GET  /conversations/{id}            -> full event log + per-turn snapshots
GET  /conversations/{id}/turns/{n}  -> state and trace as of turn n   (time travel)
GET  /catalogue/properties/{id}     -> raw record, for the trace panel drill-down
GET  /health
```

Errors return a typed envelope; the UI surfaces them rather than swallowing them, since
the brief explicitly asks to see errors.

---

## 11. UI

Two panes. Left: chat. Right: **Agent Console** with three tabs.

- **State** — the brief's own sketch, rendered live: destination, dates, guests, budget,
  action, result, next. Fields changed this turn are highlighted; assumptions are marked;
  unknowns are marked.
- **Trace** — per turn: user act, next action chip, tool cards (name, args, result
  summary, latency), grounding verdict badge, errors.
- **Timeline** — every turn; clicking one time-travels the whole console to that turn.

A toggle collapses the console to a plain chat, per the whiteboard note that tool calls
and flow should be *optionally* visible. No private chain of thought is ever rendered —
structured decisions and traces only, as the brief requires.

---

## 12. Edge cases

**Implemented (8):**

1. Relative dates — "next weekend", anchored to an explicit today, resolved in code
2. Mid-conversation modification — "4 people and one more night" updates, never restarts
3. No availability — date-shift alternative within ±2 days, framed as an offer
4. Capacity conflict — 5 guests vs a 2-cap room, resolved by split or a larger unit
5. Policy conflict — smoking / pets, surfaced rather than silently filtered
6. Unknown information — "is the pool heated?", answered honestly with a `resolution_path`
7. Impossible budget — cheapest available plus an honest "nothing under X"
8. Prompt injection in a guest message — deflected, and covered by an eval case

**Documented, not built:** ambiguous destination (Goa is a state, not a place), tool
failure and timeout degradation, past or far-future dates, min-stay violations, multi-city
requests.

---

## 13. Evaluation (Bonus 3)

**16 scripted conversations** in `evals/cases/*.yaml`. Each turn carries assertions:
expected next-action class, expected tool set, slot-level state assertions, exact expected
price, a grounding assertion, and a must-not-say list.

Scorecard dimensions, mapped to the brief's own list: tool selection accuracy, slot-level
state precision/recall/F1, recommendation top-3 hit rate, pricing exactness, hallucination
rate, next-action accuracy. Deterministic assertions are primary; a small LLM judge scores
response quality and is reported as **advisory only**. Runs against `ReplayClient` so
results are deterministic and need no credentials. Output committed to `evals/REPORT.md`.

---

## 14. Phases

| Phase | Work |
| --- | --- |
| 0 | Scaffold, domain schemas, dataset, JSON to SQLite loader, event store |
| 1 | Happy path: extract, reconcile, policy, respond; CLI first |
| 2 | Tools, deterministic pricing, grounding packet and validator |
| 3 | Edge cases, conflict engine, near-miss and relaxation lane |
| 4 | UI: chat, state panel, trace panel, timeline, time travel |
| 5 | Bonuses: upsell, conversation recovery, eval harness and report |
| 6 | README, engineering note, runnability fix (Decision 003), demo recording |
| 7 | *Optional, not attempted:* owner escalation and Owner Console |

Phase 6 is a real phase, not a scramble. The engineering note and the 5-minute demo are
graded deliverables and get their own tasks.

---

## 15. Known risks

| Risk | Mitigation |
| --- | --- |
| Demo machine lacks an authenticated Codex CLI | Preflight `codex --version` and `codex login status`; Decision 003 |
| Small-model extraction quality on messy input | Tight schema, enum vocabularies, confidence thresholds, eval coverage |
| Dataset generation becomes a time sink | Seeded generator; only 8 properties hand-authored |
| UI polish eats reliability time | UI is deliberately simple and comes after the core works |
| Scope creep from the extras list | Extras are strictly post-Phase-5 |
