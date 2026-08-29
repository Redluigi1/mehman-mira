# Engineering Note

## Architecture and model choice

Mira uses a FastAPI and Pydantic backend with a React client. The catalogue stays as reviewable JSON and is loaded into SQLite for indexed queries. The main design choice was separating language understanding from booking logic. The LLM is called only twice per turn: once to turn the guest's message into a schema-validated state update, and once to word the final reply. Reconciliation, conflict checks, search, ranking, pricing, tool selection, and holds are handled by typed Python.

The local demo uses GPT-5.6 Terra with low reasoning effort through the Codex CLI. The tasks are narrow enough that a larger model would mostly add cost and latency. An `LLMClient` interface keeps the provider separate. A tester can select Codex CLI, Claude Code CLI, or Vertex AI from `.env` and choose a model supported by that provider without changing the pipeline.

## Agent flow and state

Each turn follows a fixed flow: extract a state delta, reconcile it, detect conflicts, choose the next action, call the required tool, build a grounding packet, generate the reply, and validate it. The model interprets language, but it does not control the loop.

Conversation state is typed and event-sourced. It stores the guest's intent, shortlist, selected and rejected options, conflicts, quote, add-ons, and booking hold. A referent registry lets "the second one" resolve to an option that was actually shown. Changing an option or search field clears stale quotes and holds, preventing a later confirmation from booking the wrong room. Turn snapshots and traces also make replay and UI time travel straightforward.

Dates are treated as booking constraints, not suggestions. Extracted dates must be valid ISO values, and Python checks them before any booking action. A past check-in remains a hard conflict and blocks search, quoting, and holding until it is corrected. It is never silently moved to next year. Invalid date ranges, non-positive party sizes, and impossible budgets are flagged in the same way.

## Tool calling and hallucination control

A deterministic policy selects one next action from the current state. Tools have Pydantic argument and result schemas, so every call is validated and traceable. They cover search, availability, room and policy lookup, alternatives, exact quotes, eligible add-ons, and idempotent booking holds with an expiry. Search returns both exact matches and typed near misses instead of hiding useful alternatives.

The response model only receives a `GroundingPacket` built from state and tool results. Prices and totals are calculated in Python, never by the model. A validator checks names and numbers, attempts one repair, then uses a deterministic fallback if the draft is still unsafe. Catalogue facts distinguish known, not applicable, and unknown, so missing information is admitted instead of guessed. Prompt injection also has a code-side guard that prevents tool execution.

## Tradeoffs and next steps

This is less flexible than a free-running agent because every new behaviour needs a policy branch, but it is easier to test and trust. The CLI backends add process latency, while Vertex needs external credentials and provider-specific monitoring. The conversation store is currently in memory, and calendar interpretation still depends on the extractor before Python validates it. Soft option conflicts are surfaced once and then treated as accepted, while production should require clearer confirmation.

Next I would persist events and holds in Postgres, add provider-level latency and failure monitoring, cross-check extracted dates, and require explicit acceptance for material tradeoffs. I would also build asynchronous owner escalation with verified answers written back into the property record. RAG would be useful only for unstructured policies and reviews. Other useful follow-ups are child-aware pricing, grounded point-of-interest ranking for families, couples, and friends, plus live-model quality and conversion monitoring.
