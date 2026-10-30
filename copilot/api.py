"""HTTP-сервис: POST /triage по контракту из ТЗ."""

from fastapi import FastAPI
from pydantic import BaseModel, Field

from . import __version__
from .pipeline import triage

app = FastAPI(title="Support Copilot", version=__version__)


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
    return {"status": "ok", "version": __version__}


@app.post("/triage")
def triage_endpoint(req: TriageRequest) -> dict:
    return triage(req.model_dump())
