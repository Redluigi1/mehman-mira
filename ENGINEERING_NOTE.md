# Engineering Note

## Architecture and model choice

Mira uses a FastAPI and Pydantic backend with a React client. Reviewable catalogue JSON is loaded into SQLite for queries. The main design choice was separating language understanding from booking logic. The LLM extracts a validated state update and later words the reply. Conflict checks, search, ranking, pricing, tool selection, and holds stay in typed Python.

The default is GPT-5.6 Terra through the Codex CLI. An `LLMClient` interface keeps the provider separate, so a tester can select Codex CLI, Claude Code CLI, or Vertex AI from `.env` without changing the pipeline.

## Agent flow and state

Each turn follows a fixed flow: extract a state delta, reconcile it, detect conflicts, choose the next action, call the required tool, build a grounding packet, generate the reply, and validate it. The model interprets language, but it does not control the loop.

The six high-level stages are discover, search, present, negotiate, confirm, and held. They tell the policy and UI where the guest is in the booking journey. Typed state stores the guest's intent, shortlist, selected and rejected options, conflicts, quote, add-ons, and hold. The LLM produces only a state delta, which Python validates and merges.

A referent registry lets "the second one" resolve to an option that was actually shown. Changing an option or search field clears stale quotes and holds, preventing a later confirmation from booking the wrong room. Turn snapshots and traces make replay and UI time travel straightforward.

Dates are treated as booking constraints, not suggestions. Extracted dates must be valid ISO values, and Python checks them before any booking action. A past check-in remains a hard conflict and blocks search, quoting, and holding until it is corrected. It is never silently moved to next year. Invalid date ranges, non-positive party sizes, and impossible budgets are flagged in the same way.

## Tool calling and hallucination control

Tool calls are not chosen by the LLM. A deterministic policy reads the current state and guest action, then selects one next action. The tool registry validates every call and result with Pydantic and records it in the turn trace.

`search_properties` filters and ranks exact matches and useful near misses, while `find_alternatives` relaxes preferences when nothing matches. `check_availability`, `get_room_details`, and `get_property_policies` retrieve booking facts. `calculate_quote` computes the full price breakdown, `suggest_addons` returns only eligible extras, and `create_booking_hold` creates an expiring, idempotent hold.

The response model only receives a `GroundingPacket` built from state and tool results. Python calculates all prices. A validator checks names and numbers, attempts one repair, then uses a safe template if needed. Facts distinguish known, not applicable, and unknown, so missing information is admitted instead of guessed. A code-side prompt-injection guard can prevent tool execution entirely.

## Tradeoffs and next steps

This is less flexible than a free-running agent because every new behaviour needs a policy branch, but it is easier to test and trust. CLI backends add latency, while Vertex needs credentials and monitoring. The store is currently in memory, and calendar interpretation still begins in the extractor. Soft option conflicts are surfaced once, while production should require clearer confirmation.

Next I would persist events and holds in Postgres, cross-check dates, and add provider monitoring. I would also build asynchronous owner escalation with verified answers written back into the property record. RAG would be useful for unstructured policies and reviews. Other follow-ups are child-aware pricing, grounded point-of-interest ranking, and live-model quality monitoring.
