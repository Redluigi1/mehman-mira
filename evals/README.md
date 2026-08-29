# Eval harness

```bash
python evals/runner.py record   # regenerate evals/fixtures/ after editing a case
python evals/runner.py run      # replay-only — no LLM, no credentials — scores + writes REPORT.md
```

`run` is what a reviewer executes. It reads only `evals/fixtures/*.json` through the
real `ReplayClient` (`backend/app/llm/replay.py`) and never touches a model.

## Why "recording" is itself scripted

Plan §13 describes recording fixtures from the live Claude CLI. This harness instead
uses `evals/case_llm.py`'s `CaseScriptedLLM` as the `record`-mode `ReplayClient`'s inner
client: each case's `extracted_delta` (hand-authored, schema-valid `StateDelta`) stands
in for the extraction call, and `complete_text` raises unless a case sets
`scripted_reply`, which forces the deterministic, always-grounded template fallback
(Decision 005) instead of live text generation.

Two reasons, not one:

1. **Decision 003 is still open.** The dev LLM backend shells out to a real `claude -p`
   subprocess. Calling that dozens of times from *inside* an already-running assistant
   session to record fixtures is exactly the kind of nested-agent-spawn this project's
   safety rules single out as something to avoid doing casually, and it would burn real
   time/tokens against a human's account for a mechanical, repeatable task.
2. **It isolates what this harness actually tests.** With extraction scripted, every
   assertion failure is a real regression in the deterministic core (reconcile ->
   conflicts -> policy -> tools -> pricing -> grounding) — never noise from the model
   phrasing something differently today than it did when the fixture was recorded.

The honest cost: this harness does not measure extraction accuracy or natural-language
response quality against the real model. `evals/REPORT.md`'s methodology section says so
up front, and the advisory LLM-judge score from plan §13 is reported as **N/A**, not a
misleadingly-perfect zero. Wiring a real recording pass against `ClaudeCliClient` once
Decision 003 resolves is a natural next step — the `ReplayClient` mechanism underneath
is unchanged either way, only what feeds the `record` pass differs.

## Case format

See `evals/case_schema.py`. Each `evals/cases/*.yaml` is a scripted conversation: guest
messages, the `StateDelta` each one should produce, and per-turn assertions
(`next_action`, `tools_called`, dotted-path `state` checks, `price_total`,
`shortlist_contains`, `top3_property_id`, `grounding_verdict`, `must_not_say`).
