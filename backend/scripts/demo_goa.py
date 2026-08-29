"""Manual e2e demo: the brief's Goa example across multiple turns, run
against the real Codex CLI. Not a pytest — this needs local Codex authentication
and is for eyeballing pipeline behavior during development / the recorded
5-minute demo.
"""
from pathlib import Path

from app.data.indexes import CityIndex
from app.data.loader import build_database
from app.data.repo import Repo
from app.llm.codex_cli import CodexCliClient
from app.pipeline.engine import ConversationEngine
from app.store.conversations import ConversationStore
from app.store.holds import HoldStore

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "runtime" / "mira_demo.db"

TURNS = [
    "Looking for something in Goa this weekend for my 2 friends and me. Something private would be nice.",
    "The first one looks great, let's go with that.",
    "Is the pool heated there?",
    "Ok sounds good, what's the total price?",
    "Great, let's book it.",
]


def main() -> None:
    conn = build_database(DATA_DIR, DB_PATH)
    repo = Repo(conn)
    today = repo.get_demo_today()

    engine = ConversationEngine(
        llm=CodexCliClient(model="gpt-5.6-terra", reasoning_effort="low", timeout_s=90),
        repo=repo, city_index=CityIndex(repo), hold_store=HoldStore(),
        store=ConversationStore(), today=today,
    )

    cid = "demo-goa"
    engine.start_conversation(cid)

    for msg in TURNS:
        print(f"GUEST: {msg}")
        reply, state, trace = engine.handle_message(cid, msg)
        print(f"MIRA: {reply}")
        print(f"  [next_action={trace.next_action.type.value} "
              f"tools={[t.name for t in trace.tool_calls]} "
              f"verdict={trace.grounding_verdict.value} stage={state.stage.value}]")
        print()


if __name__ == "__main__":
    main()
