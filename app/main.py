from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from .retriever import SimpleTfidfRetriever

app = FastAPI(title="RAG Incident Assistant (Simple)", version="1.0")

retriever = SimpleTfidfRetriever()

class IngestReq(BaseModel):
    docs: List[Dict[str, Any]]

class AskReq(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: int = 3

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
