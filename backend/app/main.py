from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.channels.web import router as web_router
from app.config import get_settings
from app.data.indexes import CityIndex
from app.data.loader import build_database
from app.data.repo import Repo
from app.llm.claude_cli import ClaudeCliClient
from app.logging_config import configure_logging
from app.pipeline.engine import ConversationEngine
from app.store.conversations import ConversationStore
from app.store.holds import HoldStore

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = build_database(settings.data_dir, settings.sqlite_path)
    repo = Repo(conn)
    today = date.fromisoformat(settings.today_override) if settings.today_override else repo.get_demo_today()
    app.state.engine = ConversationEngine(
        llm=ClaudeCliClient(model=settings.llm_model, timeout_s=settings.llm_timeout_s),
        repo=repo, city_index=CityIndex(repo), hold_store=HoldStore(),
        store=ConversationStore(), today=today,
    )
    try:
        yield
    finally:
        conn.close()  # release the OS file lock — otherwise a same-process restart can't rebuild the DB


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(web_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
