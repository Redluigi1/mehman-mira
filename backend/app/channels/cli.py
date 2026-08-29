"""Terminal channel — lets a whole conversation run before any UI exists."""
from __future__ import annotations

import uuid

from app.channels.base import ChannelAdapter
from app.pipeline.engine import ConversationEngine


class CliChannel(ChannelAdapter):
    def receive(self) -> str | None:
        try:
            text = input("You: ").strip()
        except EOFError:
            return None
        return text or None

    def send(self, text: str) -> None:
        print(f"Mira: {text}")


def run_cli_conversation(engine: ConversationEngine, conversation_id: str | None = None) -> None:
    conversation_id = conversation_id or f"cli-{uuid.uuid4().hex[:8]}"
    engine.start_conversation(conversation_id)
    channel = CliChannel()
    print(f"(conversation {conversation_id} — type 'exit' to quit)")
    while True:
        message = channel.receive()
        if message is None or message.lower() in ("exit", "quit"):
            break
        reply, _state, _trace = engine.handle_message(conversation_id, message)
        channel.send(reply)


if __name__ == "__main__":
    from datetime import date
    from pathlib import Path

    from app.config import get_settings
    from app.data.indexes import CityIndex
    from app.data.loader import build_database
    from app.data.repo import Repo
    from app.llm import build_llm_client
    from app.logging_config import configure_logging
    from app.store.conversations import ConversationStore
    from app.store.holds import HoldStore

    configure_logging()
    settings = get_settings()
    conn = build_database(settings.data_dir, settings.sqlite_path)
    repo = Repo(conn)
    today = date.fromisoformat(settings.today_override) if settings.today_override else repo.get_demo_today()

    engine = ConversationEngine(
        llm=build_llm_client(
            backend=settings.llm_backend,
            model=settings.llm_model,
            timeout_s=settings.llm_timeout_s,
            reasoning_effort=settings.llm_reasoning_effort,
            vertex_project=settings.vertex_project,
            vertex_location=settings.vertex_location,
            vertex_api_key=settings.vertex_api_key,
            vertex_credentials_file=settings.google_application_credentials,
        ),
        repo=repo, city_index=CityIndex(repo), hold_store=HoldStore(),
        store=ConversationStore(), today=today,
    )
    run_cli_conversation(engine)
