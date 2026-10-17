import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import boto3
from botocore.stub import Stubber
from fastapi.testclient import TestClient
from app.aws_backend import BedrockIncidentBackend
from app.ingestion import upload_records
from app.lambda_handler import lambda_handler
from app.main import create_app

ANALYSIS={'summary':'A deployment-related configuration regression is a hypothesis.',
 'potential_root_cause':'A reduced connection pool may explain the symptoms.',
 'potential_resolution':['Review pool settings and rollback options with the responder.'],
 'verification_steps':['Compare deployment configuration and active database connections.'],
 'citations':['KB-1']}
HIT={'content':{'type':'TEXT','text':'Synthetic deployment changed pool size from 40 to 5.'},
     'score':0.8,'metadata':{'document_id':'DEP-141','title':'Jenkins sample deployment','source_type':'deployment'},
     'location':{'type':'S3','s3Location':{'uri':'s3://synthetic-demo/knowledge/141.txt'}}}

def backend():
    agent=Mock();runtime=Mock()
    agent.retrieve.return_value={'retrievalResults':[HIT]}
    runtime.converse.return_value={'stopReason':'end_turn','output':{'message':{'content':[{'text':json.dumps(ANALYSIS)}]}}}
    return BedrockIncidentBackend('KBDEMO1234','amazon.nova-lite-v1:0','us-east-1',agent=agent,runtime=runtime)

def gateway_event(body=None):
    return {'version':'2.0','rawPath':'/ask','requestContext':{'http':{'method':'POST'},'authorizer':{'iam':{'userArn':'arn:aws:iam::123456789012:user/demo'}}},
            'body':json.dumps(body or {'question':'Checkout 5xx after deployment'})}

class AwsRagTests(unittest.TestCase):
    def test_retrieve_then_nova_and_service_filter(self):
        service=backend();result=service.investigate('checkout errors',service='checkout')
        self.assertEqual(result['potential_root_cause'],ANALYSIS['potential_root_cause'])
        self.assertEqual(result['evidence'][0]['source_type'],'deployment')
        call=service.agent.retrieve.call_args.kwargs
        self.assertEqual(call['retrievalConfiguration']['vectorSearchConfiguration']['filter'],{'equals':{'key':'service','value':'checkout'}})
        request=service.runtime.converse.call_args.kwargs
        self.assertEqual(request['modelId'],'amazon.nova-lite-v1:0')
        self.assertIn('untrusted evidence',request['system'][0]['text'])

    def test_sdk_retrieve_request_contract(self):
        agent=boto3.client('bedrock-agent-runtime',region_name='us-east-1',aws_access_key_id='testing',aws_secret_access_key='testing')
        with Stubber(agent) as stub:
            stub.add_response('retrieve',{'retrievalResults':[HIT]},{'knowledgeBaseId':'KBDEMO1234','retrievalQuery':{'text':'checkout errors'},'retrievalConfiguration':{'vectorSearchConfiguration':{'numberOfResults':3}}})
            service=BedrockIncidentBackend('KBDEMO1234','amazon.nova-lite-v1:0','us-east-1',agent=agent,runtime=Mock())
            self.assertEqual(service.retrieve('checkout errors')[0].document_id,'DEP-141')
            stub.assert_no_pending_responses()

    def test_no_evidence_skips_generation(self):
        service=backend();service.agent.retrieve.return_value={'retrievalResults':[]}
        self.assertEqual(service.investigate('unknown')['status'],'insufficient_evidence')
        service.runtime.converse.assert_not_called()

    def test_guardrail_intervention_skips_generation(self):
        service=backend();service.agent.retrieve.return_value={'guardrailAction':'INTERVENED','retrievalResults':[HIT]}
        self.assertEqual(service.investigate('unknown')['status'],'insufficient_evidence')
        service.runtime.converse.assert_not_called()

    def test_weak_results_are_filtered(self):
        service=backend()
        self.assertEqual(service.investigate('checkout errors',min_score=0.9)['status'],'insufficient_evidence')
        service.runtime.converse.assert_not_called()

    def test_unsupported_citations_are_rejected(self):
        service=backend()
        service.runtime.converse.return_value['output']['message']['content'][0]['text']=json.dumps({**ANALYSIS,'citations':['invented']})
        with self.assertRaises(ValueError):service.investigate('checkout errors')

    def test_truncated_generation_is_rejected(self):
        service=backend();service.runtime.converse.return_value['stopReason']='max_tokens'
        with self.assertRaises(ValueError):service.investigate('checkout errors')

    def test_live_context_disabled_by_default(self):
        service=backend();service.logs=Mock();service.log_groups=['demo-logs']
        service.investigate('checkout errors')
        service.logs.filter_log_events.assert_not_called()

    def test_missing_live_context_is_explicit(self):
        service=backend();service.logs=Mock();service.log_groups=['demo-logs']
        service.logs.filter_log_events.side_effect=RuntimeError('sensitive error data')
        result=service.investigate('checkout errors',include_live_context=True)
        self.assertEqual(len(result['warnings']),1)
        self.assertNotIn('sensitive error data',json.dumps(result))

    def test_validates_whole_ingestion_batch_before_upload(self):
        s3=Mock();agent=Mock()
        with self.assertRaises(ValueError):
            upload_records([{'id':'ok','text':'demo'},{'id':'bad','text':''}],'demo','kb','ds',s3,agent)
        s3.put_object.assert_not_called()

    def test_s3_source_and_metadata_then_ingestion(self):
        s3=Mock();agent=Mock();agent.start_ingestion_job.return_value={'ingestionJob':{'ingestionJobId':'JOB123'}}
        result=upload_records([{'id':'DEP-141','text':'synthetic deployment','source_type':'deployment','service':'checkout'}],'demo','kb','ds',s3,agent)
        self.assertEqual(result['job_id'],'JOB123')
        self.assertEqual(s3.put_object.call_count,2)
        meta=json.loads(s3.put_object.call_args_list[1].kwargs['Body'])
        self.assertEqual(meta['metadataAttributes']['source_type'],'deployment')
        self.assertTrue(s3.put_object.call_args_list[1].kwargs['Key'].endswith('.txt.metadata.json'))
        agent.start_ingestion_job.assert_called_once_with(knowledgeBaseId='kb',dataSourceId='ds')

    def test_lambda_requires_iam_context(self):
        self.assertEqual(lambda_handler({'body':'{}'})['statusCode'],403)

    def test_lambda_success_and_base64(self):
        event=gateway_event();event['body']=base64.b64encode(event['body'].encode()).decode();event['isBase64Encoded']=True
        with patch('app.lambda_handler.backend',return_value=backend()):
            result=lambda_handler(event)
        self.assertEqual(result['statusCode'],200)
        self.assertEqual(json.loads(result['body'])['answer_mode'],'bedrock_nova')

    def test_lambda_errors_do_not_echo_input(self):
        event=gateway_event({'question':'private-value','top_k':20})
        result=lambda_handler(event)
        self.assertEqual(result['statusCode'],422)
        self.assertNotIn('private-value',result['body'])
        service=Mock();service.investigate.side_effect=RuntimeError('sensitive provider details')
        with patch('app.lambda_handler.backend',return_value=service):result=lambda_handler(gateway_event())
        self.assertEqual(result['statusCode'],503)
        self.assertNotIn('sensitive provider details',result['body'])

    def test_ui_and_aws_mode_routes(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'RAG_BACKEND':'aws','ENVIRONMENT':'development','API_KEY':''}):
            client=TestClient(create_app(Path(directory)/'unused.json',aws_backend=backend()))
            self.assertEqual(client.get('/').status_code,200)
            self.assertIn('Personal proof of concept',client.get('/').text)
            self.assertEqual(client.post('/ask',json={'question':'checkout deployment'}).json()['answer_mode'],'bedrock_nova')
            self.assertEqual(client.post('/ingest',json={'docs':[{'id':'one','text':'demo'}]}).status_code,409)

    def test_demo_fixture_contains_incidents_and_deployments(self):
        records=json.loads((Path(__file__).resolve().parents[1]/'app/demo_records.json').read_text())['docs']
        self.assertEqual({r['source_type'] for r in records},{'incident','deployment'})
        self.assertTrue(all('Synthetic' in r['text'] for r in records))
