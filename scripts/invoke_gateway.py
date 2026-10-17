"""Sign one investigation request to your IAM-protected API Gateway endpoint."""
import json
import os
import sys
import urllib.parse
import urllib.request
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

def main():
    if len(sys.argv)!=3:
        raise SystemExit('Usage: python scripts/invoke_gateway.py API_ENDPOINT QUESTION')
    endpoint,question=sys.argv[1:]
    parsed=urllib.parse.urlparse(endpoint)
    # Avoid signing credentials for arbitrary or non-AWS endpoints.
    if parsed.scheme!='https' or not parsed.hostname or '.execute-api.' not in parsed.hostname or not parsed.hostname.endswith('.amazonaws.com') or parsed.username or parsed.password:
        raise SystemExit('Use an HTTPS execute-api endpoint in your own AWS account')
    session=boto3.Session()
    credentials=session.get_credentials()
    if credentials is None:raise SystemExit('Configure your sandbox AWS identity first')
    body=json.dumps({'question':question}).encode()
    request=AWSRequest(method='POST',url=endpoint,data=body,headers={'Content-Type':'application/json'})
    SigV4Auth(credentials.get_frozen_credentials(),'execute-api',os.getenv('AWS_REGION','us-east-1')).add_auth(request)
    prepared=request.prepare()
    with urllib.request.urlopen(urllib.request.Request(endpoint,data=body,headers=dict(prepared.headers),method='POST'),timeout=35) as response:
        print(json.dumps(json.load(response),indent=2))
if __name__=='__main__':main()
