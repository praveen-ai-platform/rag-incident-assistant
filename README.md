# RAG Incident Assistant (Simple)
A lightweight **RAG-style incident assistant** for SRE/Observability workflows.

✅ What it does
- Ingests runbooks / past incidents / notes (local text)
- Retrieves most relevant chunks using **TF‑IDF similarity**
- Returns an answer template with grounded evidence snippets

> This is a simple, interview-friendly project showing RAG concepts without heavy dependencies.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload
```

Open:
- http://127.0.0.1:8000/docs

## Example usage
1) Ingest documents
```bash
curl -X POST "http://127.0.0.1:8000/ingest" -H "Content-Type: application/json" -d @data/sample_docs.json
```

2) Ask a question
```bash
curl -X POST "http://127.0.0.1:8000/ask" -H "Content-Type: application/json" -d '{"question":"Tomcat 500 errors with no stacktrace. What should I check?"}'
```
