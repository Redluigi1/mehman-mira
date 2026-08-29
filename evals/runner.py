"""Eval harness (plan §13). Two passes:

    python -m evals.runner record   # populate evals/fixtures/ from the scripted LLM
    python -m evals.runner run      # replay-only: no LLM, no credentials; scores + reports

`run` is what CI / a reviewer executes — it never touches an LLM. `record`
exists only to regenerate fixtures after a case file changes; see
`evals/README.md` for why the "recording" is itself scripted rather than a
live model call.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT))

from app.data.indexes import CityIndex  # noqa: E402
from app.data.loader import build_database  # noqa: E402
from app.data.repo import Repo  # noqa: E402
from app.llm.replay import ReplayClient  # noqa: E402
from app.pipeline.engine import ConversationEngine  # noqa: E402
from app.store.conversations import ConversationStore  # noqa: E402
from app.store.holds import HoldStore  # noqa: E402

from evals.case_llm import CaseScriptedLLM  # noqa: E402
from evals.case_schema import EvalCase, EvalTurn, load_cases  # noqa: E402

CASES_DIR = EVALS_DIR / "cases"
FIXTURES_DIR = EVALS_DIR / "fixtures"
RESULTS_PATH = EVALS_DIR / "results.json"
REPORT_PATH = EVALS_DIR / "REPORT.md"
DB_PATH = EVALS_DIR / "_eval.db"


def _build_repo() -> tuple[Repo, CityIndex, date]:
    conn = build_database(BACKEND_DIR / "data", DB_PATH)
    repo = Repo(conn)
    return repo, CityIndex(repo), repo.get_demo_today()


def _get_path(obj, path: str):
    for part in path.split("."):
        if obj is None:
            return None
        if isinstance(obj, list):
            idx = int(part)
            obj = obj[idx] if -len(obj) <= idx < len(obj) else None
        elif isinstance(obj, dict):
            obj = obj[part]
        else:
            obj = getattr(obj, part, None)
    if hasattr(obj, "value") and hasattr(type(obj), "__members__"):  # Enum
        return obj.value
    return obj


@dataclass
class AssertionResult:
    kind: str
    expected: object
    actual: object
    passed: bool
    detail: str = ""


@dataclass
class TurnResult:
    case_id: str
    turn_index: int
    guest_message: str
    reply: str
    assertions: list[AssertionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(a.passed for a in self.assertions)


def _evaluate_turn(case_id: str, turn_index: int, turn: EvalTurn, reply: str, state, trace) -> TurnResult:
    result = TurnResult(case_id=case_id, turn_index=turn_index, guest_message=turn.guest_message, reply=reply)
    a = turn.assert_

    if a.next_action is not None:
        actual = trace.next_action.type.value
        result.assertions.append(AssertionResult("next_action", a.next_action, actual, actual == a.next_action))

    if a.tools_called is not None:
        actual = sorted(tc.name for tc in trace.tool_calls)
        expected = sorted(a.tools_called)
        result.assertions.append(AssertionResult("tools_called", expected, actual, actual == expected))

    for path, expected_value in a.state.items():
        actual_value = _get_path(state, path)
        result.assertions.append(AssertionResult(f"state:{path}", expected_value, actual_value, actual_value == expected_value))

    if a.price_total is not None:
        actual = state.quote.total if state.quote else None
        passed = actual is not None and abs(actual - a.price_total) < 0.01
        result.assertions.append(AssertionResult("price_total", a.price_total, actual, passed))

    if a.top3_property_id is not None:
        top3 = [o.property_id for o in state.shortlist[:3]]
        result.assertions.append(AssertionResult("top3_property_id", a.top3_property_id, top3, a.top3_property_id in top3))

    if a.shortlist_contains is not None:
        ids = [o.property_id for o in state.shortlist]
        result.assertions.append(AssertionResult("shortlist_contains", a.shortlist_contains, ids, a.shortlist_contains in ids))

    if a.grounding_verdict is not None:
        actual = trace.grounding_verdict.value
        result.assertions.append(AssertionResult("grounding_verdict", a.grounding_verdict, actual, actual == a.grounding_verdict))

    for phrase in a.must_not_say:
        violated = phrase.lower() in reply.lower()
        result.assertions.append(AssertionResult("must_not_say", phrase, reply, not violated,
                                                   detail="hallucination/leak check"))

    return result


def record(cases: list[EvalCase]) -> None:
    repo, city_index, today = _build_repo()
    for case in cases:
        llm = ReplayClient(FIXTURES_DIR, mode="record", inner=CaseScriptedLLM(case))
        engine = ConversationEngine(llm=llm, repo=repo, city_index=city_index, hold_store=HoldStore(),
                                     store=ConversationStore(), today=today)
        for turn in case.turns:
            engine.handle_message(case.conversation_id, turn.guest_message)
        print(f"recorded fixtures for {case.id} ({len(case.turns)} turn(s))")


def run(cases: list[EvalCase]) -> list[TurnResult]:
    results: list[TurnResult] = []
    repo, city_index, today = _build_repo()
    for case in cases:
        llm = ReplayClient(FIXTURES_DIR, mode="replay")
        engine = ConversationEngine(llm=llm, repo=repo, city_index=city_index, hold_store=HoldStore(),
                                     store=ConversationStore(), today=today)
        for i, turn in enumerate(case.turns, start=1):
            reply, state, trace = engine.handle_message(case.conversation_id, turn.guest_message)
            results.append(_evaluate_turn(case.id, i, turn, reply, state, trace))
    return results


def _scorecard(results: list[TurnResult]) -> dict:
    def rate(kind: str) -> tuple[int, int]:
        rows = [a for r in results for a in r.assertions if a.kind == kind or (kind == "state" and a.kind.startswith("state:"))]
        return sum(1 for a in rows if a.passed), len(rows)

    def pct(n: int, d: int) -> float:
        return round(100.0 * n / d, 1) if d else 100.0

    metrics = {}
    for kind, label in [
        ("next_action", "next_action_accuracy"), ("tools_called", "tool_selection_accuracy"),
        ("state", "state_assertion_pass_rate"), ("price_total", "pricing_exactness"),
        ("top3_property_id", "top3_hit_rate"), ("grounding_verdict", "grounding_verdict_accuracy"),
    ]:
        n, d = rate(kind)
        metrics[label] = {"passed": n, "total": d, "pct": pct(n, d)}

    n, d = rate("must_not_say")
    metrics["hallucination_rate_pct"] = {"passed": d - n, "total": d, "pct": pct(d - n, d) if d else 0.0}

    total_turns = len(results)
    passed_turns = sum(1 for r in results if r.passed)
    metrics["overall_turn_pass_rate"] = {"passed": passed_turns, "total": total_turns, "pct": pct(passed_turns, total_turns)}
    return metrics


def _write_report(cases: list[EvalCase], results: list[TurnResult], scorecard: dict) -> None:
    lines = [
        "# Eval report", "",
        f"**{len(cases)} cases, {len(results)} turns.** Generated by `evals/runner.py run` — deterministic, no LLM credentials.",
        "",
        "## Methodology (read before the numbers)", "",
        "This harness scripts the two LLM calls (state extraction, response generation) per",
        "turn instead of recording them from a live model backend. See `evals/README.md` for",
        "why. The consequence: this is a regression harness for the **deterministic core**",
        "(reconcile -> conflicts -> policy -> tools -> pricing -> grounding), not a measure of",
        "extraction accuracy or natural-language quality against the real model. The advisory",
        "LLM-judge response-quality score from plan §13 is **not run** for the same reason —", "N/A, not a zero.",
        "",
        "`state_assertion_pass_rate` checks that asserted fields end up correct after",
        "reconciliation — not a true precision/recall against a gold parse, since extraction",
        "itself is scripted here rather than produced (and gradeable) independently.",
        "",
        "## Scorecard", "",
        "| Metric | Passed / Total | % |", "| --- | --- | ---: |",
    ]
    for key, row in scorecard.items():
        lines.append(f"| {key} | {row['passed']} / {row['total']} | {row['pct']}% |")

    lines += ["", "## Per-case results", "", "| Case | Turn | Guest message | Result |", "| --- | ---: | --- | --- |"]
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        msg = r.guest_message.replace("|", "/")
        lines.append(f"| {r.case_id} | {r.turn_index} | {msg[:70]} | {mark} |")

    failures = [r for r in results if not r.passed]
    if failures:
        lines += ["", "## Failure detail", ""]
        for r in failures:
            lines.append(f"### {r.case_id} turn {r.turn_index}")
            for a in r.assertions:
                if not a.passed:
                    lines.append(f"- `{a.kind}`: expected `{a.expected}`, got `{a.actual}`" + (f" ({a.detail})" if a.detail else ""))
            lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    cases = load_cases(CASES_DIR)
    if mode == "record":
        FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        record(cases)
        return
    results = run(cases)
    scorecard = _scorecard(results)
    RESULTS_PATH.write_text(json.dumps({
        "scorecard": scorecard,
        "turns": [
            {"case_id": r.case_id, "turn_index": r.turn_index, "guest_message": r.guest_message, "reply": r.reply,
             "passed": r.passed,
             "assertions": [{"kind": a.kind, "expected": a.expected, "actual": a.actual, "passed": a.passed} for a in r.assertions]}
            for r in results
        ],
    }, indent=2, default=str), encoding="utf-8")
    _write_report(cases, results, scorecard)
    total = scorecard["overall_turn_pass_rate"]
    print(f"{total['passed']}/{total['total']} turns passed ({total['pct']}%) — see evals/REPORT.md")


if __name__ == "__main__":
    main()
