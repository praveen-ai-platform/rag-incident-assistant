"""HTTP safeguards shared in design, but owned independently by this service."""
import hmac
import json
import logging
import os
import time
import uuid
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("service.requests")

class BodyLimitMiddleware:
    def __init__(self, app, max_bytes=1_048_576):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > self.max_bytes:
                response = JSONResponse(status_code=413, content={'detail': 'Request body exceeds 1 MiB'})
                return await response(scope, receive, send)
            if not message.get('more_body', False):
                break
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.app(scope, replay, send)

def configure(app):
    api_key = os.getenv('API_KEY', '')
    if os.getenv('ENVIRONMENT', 'development') == 'production' and len(api_key) < 32:
        raise RuntimeError('Production requires API_KEY with at least 32 characters')
    app.add_middleware(BodyLimitMiddleware)

    async def authenticate(request: Request):
        if api_key and not hmac.compare_digest(request.headers.get('X-API-Key', '').encode('utf-8'), api_key.encode('utf-8')):
            raise HTTPException(status_code=401, detail='Invalid or missing API key')

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic errors may contain submitted text; never echo that input.
        errors = [{'loc': e['loc'], 'type': e['type'], 'msg': e['msg']} for e in exc.errors()]
        return JSONResponse(status_code=422, content={'detail': errors})

    @app.middleware('http')
    async def request_metadata(request, call_next):
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        logger.info(json.dumps({'request_id': request_id, 'method': request.method,
            'status': response.status_code, 'duration_ms': round((time.perf_counter()-started)*1000, 2)}))
        return response
    return authenticate
