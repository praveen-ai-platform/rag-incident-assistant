"""API Gateway HTTP API Lambda proxy entry point. Gateway enforces AWS IAM."""
import base64
from functools import lru_cache
import json
from pydantic import ValidationError
from .aws_backend import BedrockIncidentBackend

@lru_cache(maxsize=1)
def backend():
    return BedrockIncidentBackend.from_env()

def lambda_handler(event,context=None):
    from .schemas import AskRequest
    response_headers={'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
    def response(code,body):
        return {'statusCode':code,'headers':response_headers,'body':json.dumps(body)}
    request_context=event.get('requestContext',{})
    # No public unauthenticated Lambda/function URL path is supported.
    if not request_context.get('authorizer',{}).get('iam',{}).get('userArn'):
        return response(403,{'detail':'An IAM-authorized API Gateway request is required'})
    if request_context.get('http',{}).get('method')!='POST' or event.get('rawPath') not in {'/ask','/incidents'}:
        return response(404,{'detail':'Route not found'})
    try:
        raw=event.get('body','')
        if len(raw)>1_400_000:
            return response(413,{'detail':'Request body exceeds limit'})
        raw=base64.b64decode(raw,validate=True) if event.get('isBase64Encoded') else raw.encode('utf-8')
        if len(raw)>1_048_576:
            return response(413,{'detail':'Request body exceeds 1 MiB'})
        request=AskRequest.model_validate_json(raw)
    except (TypeError,ValueError,ValidationError):
        return response(422,{'detail':'Invalid incident request'})
    try:
        result=backend().investigate(request.question,request.top_k,request.min_score,request.service,request.include_live_context)
        return response(200,result)
    except Exception:
        return response(503,{'detail':'Incident analysis is unavailable; retry later'})
