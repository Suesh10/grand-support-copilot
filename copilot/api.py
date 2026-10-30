"""HTTP-сервис: POST /triage по контракту из ТЗ."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, llm, model, reputation, retrieve
from .admin import router as admin_router
from .dedupe import Deduper
from .pipeline import triage
from .rules import load_points

_dedupe = Deduper()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Прогрев: модели и индекс грузятся при старте, а не на первом запросе (p95 ≤ 5 с).
    load_points(), model.load(), retrieve.load(), reputation.load()
    triage({"kind": "report", "messages": [{"text": "прогрев"}]})
    yield


app = FastAPI(title="Support Copilot", version=__version__, lifespan=lifespan)
app.include_router(admin_router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


class Message(BaseModel):
    role: str = "player"
    text: str = ""
    attachments: int = 0


class TriageRequest(BaseModel):
    kind: str = Field("report", pattern="^(complaint|report)$")
    messages: list[Message]
    rule_refs_raw: str | None = None
    reported_nick: str | None = None
    # Необязательные поля для отсева дублей: без них дубль не определяется.
    reporter_hash: str | None = None
    reported_hash: str | None = None
    created_at: str | None = None


@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse("/admin")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__,
            "model_loaded": model.load() is not None, "index_loaded": retrieve.load() is not None,
            "llm": llm.enabled()}


@app.post("/triage")
def triage_endpoint(req: TriageRequest) -> dict:
    request = req.model_dump()
    request["is_duplicate"] = _dedupe.is_duplicate(request)
    result = triage(request)
    if req.kind == "complaint":
        reputation.remember(req.reported_hash, result["category"])
    return result
