"""HTTP-сервис: POST /triage по контракту из ТЗ."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from . import __version__, llm, model, retrieve
from .admin import router as admin_router
from .pipeline import triage
from .rules import load_points


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Прогрев: модели и индекс грузятся при старте, а не на первом запросе (p95 ≤ 5 с).
    load_points(), model.load(), retrieve.load()
    triage({"kind": "report", "messages": [{"text": "прогрев"}]})
    yield


app = FastAPI(title="Support Copilot", version=__version__, lifespan=lifespan)
app.include_router(admin_router)


class Message(BaseModel):
    role: str = "player"
    text: str = ""
    attachments: int = 0


class TriageRequest(BaseModel):
    kind: str = Field("report", pattern="^(complaint|report)$")
    messages: list[Message]
    rule_refs_raw: str | None = None
    reported_nick: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__,
            "model_loaded": model.load() is not None, "index_loaded": retrieve.load() is not None,
            "llm": llm.enabled()}


@app.post("/triage")
def triage_endpoint(req: TriageRequest) -> dict:
    return triage(req.model_dump())
