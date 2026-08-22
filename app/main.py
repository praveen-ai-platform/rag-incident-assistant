from fastapi import FastAPI
from datetime import datetime
from typing import List, Dict, Any, Literal

from pydantic import BaseModel, Field

from .alert_noise import reduce_alert_noise
from .retriever import SimpleTfidfRetriever

app = FastAPI(title="RAG Incident Assistant (Simple)", version="1.0")

retriever = SimpleTfidfRetriever()

class IngestReq(BaseModel):
    docs: List[Dict[str, Any]]

class AskReq(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: int = 3


class AlertEvent(BaseModel):
    alert_id: str
    service: str = Field(..., min_length=1)
    alert_name: str = Field(..., min_length=1)
    severity: Literal["info", "warning", "critical"]
    timestamp: datetime
    message: str = ""


class AlertReductionReq(BaseModel):
    alerts: List[AlertEvent]
    cooldown_minutes: int = Field(default=15, ge=0, le=1440)
    minimum_severity: Literal["info", "warning", "critical"] = "warning"

@app.post("/ingest")
def ingest(req: IngestReq):
    retriever.ingest(req.docs)
    return {"status":"ok", "docs_ingested": len(req.docs)}

@app.post("/ask")
def ask(req: AskReq):
    hits = retriever.top_k(req.question, k=req.top_k)
    evidence = [{"id":h.id, "title":h.title, "score":score, "snippet":h.text[:240]} for h, score in hits]

    answer = {
        "summary": "Likely causes and next checks based on retrieved operational knowledge.",
        "suggested_checks": [
            "Check upstream LB/proxy timeouts and target health",
            "Check Tomcat thread pool / connection pool saturation",
            "Compare recent deploy/config changes",
            "Inspect dependency errors (DB/HTTP) and latency spikes"
        ],
        "evidence": evidence
    }
    return answer


@app.post("/reduce-alert-noise")
def reduce_noise(req: AlertReductionReq):
    """Return actionable alerts after severity filtering and cooldown deduplication."""
    return reduce_alert_noise(
        (alert.model_dump(mode="json") for alert in req.alerts),
        cooldown_minutes=req.cooldown_minutes,
        minimum_severity=req.minimum_severity,
    )
