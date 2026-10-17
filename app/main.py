import os
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from .http_support import configure
from .retriever import SimpleTfidfRetriever

from .schemas import AskRequest, Answer, IngestRequest, IngestResult

def create_app(data_path=None, aws_backend=None):
    app = FastAPI(title='RAG Incident Assistant', version='3.0.0', description='Personal PoC: Bedrock Titan embeddings, S3 Vectors knowledge retrieval, Nova analysis, and an offline demo.')
    authenticate = configure(app)
    mode=os.getenv('RAG_BACKEND','demo')
    if mode not in {'demo','aws'}: raise ValueError('RAG_BACKEND must be demo or aws')
    if mode=='aws' and aws_backend is None:
        from .aws_backend import BedrockIncidentBackend
        aws_backend=BedrockIncidentBackend.from_env()
    app.state.backend_mode=mode
    retriever = SimpleTfidfRetriever(data_path if data_path is not None else os.getenv('RAG_DATA_PATH', 'data/documents.json')) if mode=='demo' else None
    app.state.retriever = retriever

    @app.get('/', include_in_schema=False)
    def demo_ui():
        return FileResponse(Path(__file__).parent/'static'/'index.html')

    @app.get('/demo-data',dependencies=[Depends(authenticate)])
    def demo_data():
        import json
        return json.loads((Path(__file__).parent/'demo_records.json').read_text())

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'rag-incident-assistant','backend':mode}

    @app.get('/ready')
    def ready():
        if mode=='aws':
            return {'status':'configured','backend':'aws','note':'Knowledge Base ingestion readiness is managed by Bedrock'}
        if not retriever.ready:
            raise HTTPException(503, 'Ingest operational documents first')
        return {'status': 'ready'}

    @app.post('/ingest', response_model=IngestResult, dependencies=[Depends(authenticate)])
    def ingest(request: IngestRequest):
        if mode=='aws':
            raise HTTPException(409,'Use scripts/seed_knowledge_base.py to upload records and run managed Titan ingestion')
        try:
            count = retriever.ingest([d.model_dump() for d in request.docs])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {'status': 'ok', 'docs_ingested': len(request.docs), 'chunks_indexed': count, 'mode': 'replace'}

    @app.post('/incidents', response_model=Answer, dependencies=[Depends(authenticate)])
    @app.post('/ask', response_model=Answer, dependencies=[Depends(authenticate)])
    def ask(request: AskRequest):
        if mode=='aws':
            try:
                return aws_backend.investigate(request.question,request.top_k,request.min_score,request.service,request.include_live_context)
            except Exception:
                raise HTTPException(503,'Incident analysis is unavailable; retry later') from None
        if not retriever.ready:
            raise HTTPException(409, 'Ingest operational documents first')
        hits = retriever.top_k(request.question, request.top_k, request.min_score)
        evidence = [{'document_id': c.document_id, 'chunk_id': c.chunk_id, 'title': c.title,
                     'score': round(score, 6), 'snippet': c.text} for c, score in hits]
        return {'status': 'evidence_found' if hits else 'insufficient_evidence',
                'answer_mode': 'offline_extracts',
                'summary': 'Relevant operational evidence follows.' if hits else 'No relevant evidence meets the similarity threshold.',
                'suggested_checks': [{'text': c.text, 'source_chunk_id': c.chunk_id} for c, _ in hits],
                'evidence': evidence,
                'potential_root_cause': None,
                'potential_resolution': [],
                'verification_steps': [],
                'citations':[item['chunk_id'] for item in evidence],
                'warnings':['Offline demo: results are retrieved sample extracts; no Bedrock models or AWS services were called.']}
    return app

app = create_app()
