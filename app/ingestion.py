"""Convert synthetic JSON records into S3 documents and start managed Titan indexing."""
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class SourceRecord(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    id: str = Field(min_length=1,max_length=128)
    title: str = Field(default='',max_length=256)
    text: str = Field(min_length=1,max_length=20000)
    source_type: Literal['incident','deployment','runbook'] = 'incident'
    service: str = Field(default='demo',min_length=1,max_length=128)
    timestamp: str | None = Field(default=None,max_length=64)

def upload_records(records,bucket,knowledge_base_id,data_source_id,s3,agent):
    if not 1<=len(records)<=200:
        raise ValueError('Provide 1 to 200 synthetic records')
    records=[SourceRecord.model_validate(record).model_dump(exclude_none=True) for record in records]
    if len({r['id'] for r in records})!=len(records):
        raise ValueError('Record IDs must be unique')
    for record in records:
        if not record.get('id') or not record.get('text','').strip():
            raise ValueError('Every record requires an ID and text')
        if len(record['text'])>20000:
            raise ValueError('Record text exceeds 20000 characters')
    for record in records:
        key='knowledge/'+hashlib.sha256(record['id'].encode()).hexdigest()+'.txt'
        metadata={'metadataAttributes':{'document_id':record['id'],'title':record.get('title',record['id']),
            'source_type':record.get('source_type','incident'),'service':record.get('service','demo')}}
        if record.get('timestamp'):
            metadata['metadataAttributes']['timestamp']=record['timestamp']
        text=record.get('title','')+'\n'+record['text']
        s3.put_object(Bucket=bucket,Key=key,Body=text.encode('utf-8'),ContentType='text/plain',ServerSideEncryption='AES256')
        s3.put_object(Bucket=bucket,Key=key+'.metadata.json',Body=json.dumps(metadata).encode('utf-8'),ContentType='application/json',ServerSideEncryption='AES256')
    job=agent.start_ingestion_job(knowledgeBaseId=knowledge_base_id,dataSourceId=data_source_id)
    return {'status':'ingestion_started','docs_ingested':len(records),'mode':'upsert','job_id':job['ingestionJob']['ingestionJobId'],
            'message':'Wait for the Bedrock ingestion job to complete before querying. Existing unrelated records are retained.'}
