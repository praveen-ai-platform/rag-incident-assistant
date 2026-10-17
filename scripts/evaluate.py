"""Small deterministic retrieval evaluation using only synthetic sample documents."""
import json
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from app.retriever import SimpleTfidfRetriever

cases=[('Tomcat 500 stacktrace','rbk-001'),('EKS readiness pod restarts','rbk-002'),
       ('Lambda duration cold starts','rbk-003'),('DB pool saturation slow queries','inc-024')]
retriever=SimpleTfidfRetriever()
retriever.ingest(json.loads((root/'sample_docs.json').read_text())['docs'])
reciprocal, correct = [], 0
for question, expected in cases:
    hits=retriever.top_k(question,k=10)
    ids=list(dict.fromkeys(c.document_id for c,_ in hits))
    rank=ids.index(expected)+1 if expected in ids else None
    reciprocal.append(1/rank if rank else 0)
    correct+=rank==1
print(json.dumps({'fixture':'four synthetic runbooks; lexical retrieval only','queries':len(cases),
                  'recall_at_1':correct/len(cases),'mrr':sum(reciprocal)/len(cases)},indent=2))
