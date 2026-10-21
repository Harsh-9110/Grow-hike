from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class UploadLimitMiddleware:
    """Bound the body before multipart parsing can spool a large file to disk."""
    def __init__(self, app: ASGIApp, max_bytes: int = 2 * 1024 * 1024 + 131072):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope['type'] != 'http' or scope['path'] != '/api/imports/preview':
            await self.app(scope, receive, send)
            return
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body = message.get('body', b'')
            size += len(body)
            if size > self.max_bytes:
                await JSONResponse({'detail':'Maximum file size is 2 MB'}, status_code=413)(scope, receive, send)
                return
            chunks.append(body)
            if not message.get('more_body', False):
                break
        sent = False
        async def bounded_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {'type':'http.request','body':b''.join(chunks),'more_body':False}
            return await receive()
        await self.app(scope, bounded_receive, send)
