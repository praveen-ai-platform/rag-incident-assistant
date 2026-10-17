import os
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .http_support import configure
from .retriever import SimpleTfidfRetriever

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Document(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(default='', max_length=256)
    text: str = Field(min_length=1, max_length=20000)

class IngestRequest(StrictModel):
    docs: list[Document] = Field(min_length=1, max_length=200)

class AskRequest(StrictModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=10)
    min_score: float = Field(default=0.1, gt=0, le=1)

class Evidence(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    score: float
    snippet: str

class SuggestedCheck(BaseModel):
    text: str
    source_chunk_id: str

class Answer(BaseModel):
    status: str
    answer_mode: str
    summary: str
    suggested_checks: list[SuggestedCheck]
    evidence: list[Evidence]

class IngestResult(BaseModel):
    status: str
    docs_ingested: int
    chunks_indexed: int
    mode: str

def create_app(data_path=None):
    app = FastAPI(title='RAG Incident Assistant', version='2.0.0', description='Evidence retrieval using TF-IDF. Responses are extractive; no LLM is used.')
    authenticate = configure(app)
    retriever = SimpleTfidfRetriever(data_path if data_path is not None else os.getenv('RAG_DATA_PATH', 'data/documents.json'))
    app.state.retriever = retriever

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'rag-incident-assistant'}

    @app.get('/ready')
    def ready():
        if not retriever.ready:
            raise HTTPException(503, 'Ingest operational documents first')
        return {'status': 'ready'}

    @app.post('/ingest', response_model=IngestResult, dependencies=[Depends(authenticate)])
    def ingest(request: IngestRequest):
        try:
            count = retriever.ingest([d.model_dump() for d in request.docs])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {'status': 'ok', 'docs_ingested': len(request.docs), 'chunks_indexed': count, 'mode': 'replace'}

    @app.post('/ask', response_model=Answer, dependencies=[Depends(authenticate)])
    def ask(request: AskRequest):
        if not retriever.ready:
            raise HTTPException(409, 'Ingest operational documents first')
        hits = retriever.top_k(request.question, request.top_k, request.min_score)
        evidence = [{'document_id': c.document_id, 'chunk_id': c.chunk_id, 'title': c.title,
                     'score': round(score, 6), 'snippet': c.text} for c, score in hits]
        return {'status': 'evidence_found' if hits else 'insufficient_evidence',
                'answer_mode': 'extractive',
                'summary': 'Relevant operational evidence follows.' if hits else 'No relevant evidence meets the similarity threshold.',
                'suggested_checks': [{'text': c.text, 'source_chunk_id': c.chunk_id} for c, _ in hits],
                'evidence': evidence}
    return app

app = create_app()
