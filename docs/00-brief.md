# 00 — The assignment, distilled

Source: `reference/Mehman_Case_Study.pdf` (original at
`C:\Users\AYUSH\Downloads\Mehman __ Case Study.pdf`). This file is a faithful
condensation so later sessions need not re-read the PDF; the PDF wins on any conflict.

## Context

Mehman.io builds an AI-powered guest and revenue layer for hospitality across
**WhatsApp, Instagram, web and phone**. The brief asks for a simplified version of
**Mira**, their guest-facing agent.

> "Don't just vibe code design; every UI component and interaction must have a reason behind it."

## The core question

Can you build a working hotel-booking AI agent that **understands the guest, remembers
context, retrieves the right information, calls the right tools, handles ambiguity, and
moves the conversation toward booking?** The system must actually run.

Worked example from the brief:

> Guest: "Looking for something in Goa this weekend for my 2 friends and me. Something private would be nice."

The system must identify and maintain: **destination, dates, guests, budget, room
preferences, amenities, special requirements** — then decide *what is known, what is
missing, whether to ask a question or use a tool, and what happens next*.

## Expected flow

```
Guest message
  → understand intent and update state
  → ask for missing information or call a tool
  → retrieve and validate hotel information
  → recommend, calculate, or continue
  → generate a natural response
  → move toward booking
```

"The interaction should feel conversational, not like filling a form."

The brief's own summary of a strong submission:

```
guest message → update state → decide next action → call tool
  → validate result → respond naturally → continue toward booking
```

## Hotel data (as specified)

Minimum asked for: **3 properties, 2–4 room types each**, including *location, pricing,
availability, capacity, amenities, policies, optional add-ons*. Storage: JSON, SQLite,
PostgreSQL, or anything simple.

> We are deliberately exceeding this — see Decision 006.

## Required capabilities

1. **Conversation understanding** — "Need something in Goa next weekend", "Travelling with
   my wife and 2 kids", "Something with a private pool under 20k".
2. **Conversation state** — remember and *correctly update*. "Actually make that 4 people
   and stay one more night" must update existing state, not restart the conversation.
3. **Grounded responses** — never invent prices, availability, room types, amenities,
   policies, capacity. If something is unknown, say so.
4. **Tool calling** — at least **3 functional tools**. Suggested shapes:
   `search_properties()`, `check_availability()`, `get_room_details()`,
   `calculate_price()`, `get_policy()`, `create_booking_hold()`.
   Graded on *when* the model picks a tool and *how it uses the result*.
5. **Recommendation and pricing** — recommend the most relevant property/room.
   **Pricing calculations should be handled through deterministic application logic where possible.**

## Edge cases

At least **3 meaningful** ones. The brief's examples:

- **Relative dates** — "Need something next weekend."
- **Changing requirements** — "Actually make that 4 people and stay till the 13th."
- **No availability** — requested room unavailable, suggest the best alternative.
- **Conflicting requirements** — five guests request a room that only supports two.
- **Unknown information** — guest asks whether a pool is heated; the dataset does not say.

> "Choose cases that show how thoughtfully your system behaves beyond the happy path."

## Bonus (only after the core works reliably)

1. **Intelligent upselling** — contextual add-ons: airport pickup, breakfast, upgrades,
   early check-in, late checkout, experiences.
2. **Conversation recovery** — handle "yes", "too expensive", "whichever is better",
   "what about the other one?", "any cheaper option?".
3. **Evaluation** — 10–20 test conversations scored on tool selection, state updates,
   recommendation accuracy, pricing, hallucination control, next action.

## What to submit

1. **Working implementation** — GitHub repo with README, setup instructions,
   architecture, environment variables, assumptions, known limitations. Must be runnable.
2. **5-minute demo** — one happy path, at least two edge cases, tool calls, state updates,
   key engineering decisions. No slides; show the actual system.
3. **Short engineering note** — ~1 page max, covering architecture, model choice, agent
   flow, state management, tool calling, hallucination prevention, tradeoffs, and what
   you would improve next.

## UI expectations

Production quality is *not* required. React, Next.js, Streamlit, Gradio, CLI — anything
simple. But the reviewer must be able to see: **guest conversation, current state, tool
calls, tool results, next action, errors.** The brief's own sketch:

```
Destination: Goa
Dates: Sep 10 to 13
Guests: 4
Budget: ₹20k/night
Action: check_availability
Result: 2 matching rooms
Next: Recommend Pool Villa
```

> "Do not expose private chain of thought. Structured decisions and traces are enough."

## How it is graded

| Weight | Dimension | Detail |
| ---: | --- | --- |
| 30% | Reliability | State, factual accuracy, tool usage, calculations, hallucination control |
| 25% | AI system design | Prompt design, tools, context, state, agent flow |
| 20% | Engineering quality | Code clarity, architecture, error handling, setup |
| 15% | Edge cases | How deliberately the system handles ambiguity and failure |
| 10% | Product judgment | Whether the conversation feels useful and progresses toward the goal |

## Guidance given

- Build the happy path first, then add edge cases.
- Keep the architecture simple.
- Use AI tools freely, but understand everything you submit.
- **"A smaller system that actually works is better than an ambitious system that does not."**
