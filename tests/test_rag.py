import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.retriever import SimpleTfidfRetriever

DOCS=[{'id':'db','title':'Database saturation','text':'Inspect database connection pool exhaustion and slow queries.'},
      {'id':'pods','title':'Kubernetes restart','text':'Inspect pod restart counts and readiness probes.'}]

class RagTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'documents.json'
        with patch.dict(os.environ, {'API_KEY':'','ENVIRONMENT':'development'}):
            self.app=create_app(self.path)
        self.client=TestClient(self.app)

    def ingest(self):
        return self.client.post('/ingest',json={'docs':DOCS})

    def test_readiness_before_ingestion(self):
        self.assertEqual(self.client.get('/ready').status_code,503)
        self.assertEqual(self.client.post('/ask',json={'question':'database'}).status_code,409)

    def test_ranked_evidence_and_cited_checks(self):
        self.assertEqual(self.ingest().status_code,200)
        response=self.client.post('/ask',json={'question':'database connection pool exhaustion'}).json()
        self.assertEqual(response['evidence'][0]['document_id'],'db')
        self.assertEqual(response['suggested_checks'][0]['source_chunk_id'],'db:0')
        self.assertIn(response['suggested_checks'][0]['text'],DOCS[0]['text'])
        self.assertEqual(self.client.get('/ready').status_code,200)

    def test_unrelated_query_abstains(self):
        self.ingest()
        result=self.client.post('/ask',json={'question':'chocolate croissant recipe'}).json()
        self.assertEqual(result['status'],'insufficient_evidence')
        self.assertEqual(result['suggested_checks'],[])

    def test_persistence_and_replace_semantics(self):
        self.ingest()
        restored=SimpleTfidfRetriever(self.path)
        self.assertTrue(restored.ready)
        self.assertEqual(restored.top_k('database')[0][0].document_id,'db')
        self.client.post('/ingest',json={'docs':[DOCS[1]]})
        self.assertEqual(SimpleTfidfRetriever(self.path).top_k('database'),[])

    def test_failed_ingest_preserves_previous_index(self):
        self.ingest()
        before=self.path.read_bytes()
        response=self.client.post('/ingest',json={'docs':[{'id':'empty','text':'the and or'}]})
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertTrue(self.app.state.retriever.ready)

    def test_duplicate_ids_and_bounds(self):
        self.assertEqual(self.client.post('/ingest',json={'docs':[DOCS[0],DOCS[0]]}).status_code,422)
        for k in [0,11]:
            self.assertEqual(self.client.post('/ask',json={'question':'database','top_k':k}).status_code,422)
        self.assertEqual(self.client.post('/ingest',json={'docs':[]}).status_code,422)

    def test_chunking(self):
        retriever=SimpleTfidfRetriever()
        count=retriever.ingest([{'id':'long','text':' '.join(['database']*250)}])
        self.assertEqual(count,3)
        self.assertLessEqual(len(retriever.top_k('database')[0][0].text.split()),120)

    def test_alert_endpoint_removed(self):
        self.assertEqual(self.client.post('/reduce-alert-noise',json={}).status_code,404)

    def test_api_key_and_production_configuration(self):
        with patch.dict(os.environ, {'API_KEY':'x'*32,'ENVIRONMENT':'production'}):
            client=TestClient(create_app(self.path))
        self.assertEqual(client.post('/ingest',json={'docs':DOCS}).status_code,401)
        self.assertEqual(client.post('/ingest',json={'docs':DOCS},headers={'X-API-Key':'x'*32}).status_code,200)

    def test_sensitive_validation_input_not_echoed(self):
        result=self.client.post('/ask',json={'question':'database','top_k':'private-value'})
        self.assertEqual(result.status_code,422)
        self.assertNotIn('private-value',result.text)

    def test_openapi_documents_api_key(self):
        schema=self.client.get('/openapi.json').json()
        self.assertEqual(schema['components']['securitySchemes']['APIKeyHeader']['name'],'X-API-Key')
