"""Upload the bundled synthetic JSON fixture to S3 and request Titan/S3 Vectors indexing."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.ingestion import upload_records

def main():
    import boto3
    bucket=os.environ['RAG_SOURCE_BUCKET']
    knowledge_base=os.environ['BEDROCK_KNOWLEDGE_BASE_ID']
    data_source=os.environ['BEDROCK_DATA_SOURCE_ID']
    region=os.getenv('AWS_REGION','us-east-1')
    source=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/'app/demo_records.json'
    records=json.loads(source.read_text(encoding='utf-8'))['docs']
    result=upload_records(records,bucket,knowledge_base,data_source,boto3.client('s3',region_name=region),boto3.client('bedrock-agent',region_name=region))
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
