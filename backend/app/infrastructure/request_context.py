"""Request correlation and response headers shared by normal and error paths."""
from contextvars import ContextVar
import json
import logging
import secrets
import time

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from .metrics import request_observed

request_id = ContextVar('request_id', default='')
logger = logging.getLogger('gduf.requests')


class RequestContext:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        identifier = secrets.token_hex(12)
        token = request_id.set(identifier)
        start = time.monotonic()
        status = 500
        sent = False

        async def with_headers(message):
            nonlocal status, sent
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                headers['X-Request-ID'] = identifier
                headers['X-Content-Type-Options'] = 'nosniff'
                if '/admin/' in scope['path'] or '/results' in scope['path']:
                    headers['Cache-Control'] = 'no-store'
                status = message['status']
                sent = True
            await send(message)

        try:
            await self.app(scope, receive, with_headers)
        except Exception as exc:
            # Keep source locations without logging exception values (SQL, input, credentials).
            frames = []
            trace = exc.__traceback__
            while trace:
                code = trace.tb_frame.f_code
                frames.append(f'{code.co_filename}:{trace.tb_lineno}:{code.co_name}')
                trace = trace.tb_next
            logger.error(json.dumps({'request_id': identifier, 'exception': type(exc).__name__,
                                     'stack': frames}))
            if sent:
                raise
            response = JSONResponse({'error': {'code': 'INTERNAL', 'message': '服务暂不可用',
                                               'details': {}, 'request_id': identifier}}, status_code=500)
            await response(scope, receive, with_headers)
        finally:
            route = getattr(scope.get('route'), 'path', 'unmatched')
            duration = time.monotonic() - start
            request_observed(route, status, duration)
            logger.info(json.dumps({'request_id': identifier, 'route': route, 'method': scope['method'],
                                    'status': status, 'duration_ms': round(duration*1000, 2)}))
            request_id.reset(token)
