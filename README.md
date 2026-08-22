# RAG Incident Assistant (Simple)
A lightweight **RAG-style incident assistant** for SRE/Observability workflows, with
an alert-noise-reduction endpoint for grouping repeated events before escalation.

✅ What it does
- Ingests runbooks / past incidents / notes (local text)
- Retrieves most relevant chunks using **TF‑IDF similarity**
- Returns an answer template with grounded evidence snippets
- Suppresses low-severity alerts and duplicate alert signatures within a configurable cooldown

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

3) Reduce alert noise
```bash
curl -X POST "http://127.0.0.1:8000/reduce-alert-noise" -H "Content-Type: application/json" -d '{"cooldown_minutes":15,"minimum_severity":"warning","alerts":[{"alert_id":"a-1","service":"checkout","alert_name":"HighErrorRate","severity":"warning","timestamp":"2026-08-22T10:00:00Z"},{"alert_id":"a-2","service":"checkout","alert_name":"HighErrorRate","severity":"warning","timestamp":"2026-08-22T10:04:00Z"},{"alert_id":"a-3","service":"checkout","alert_name":"DebugSignal","severity":"info","timestamp":"2026-08-22T10:05:00Z"}]}'
```

The response keeps `a-1`, suppresses `a-2` as a cooldown duplicate, and suppresses
`a-3` because it is below the selected severity threshold. Alerts are grouped by
service, alert name, and severity, so different failure modes still reach responders.
