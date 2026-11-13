"""Reject oversized JSON and cross-origin writes before validation or expensive hashing."""
from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from app.services.abuse import request_budget


class AbuseMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        original_send = send
        async def private_response(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "private, no-store"
            await original_send(message)
        send = private_response
        request = Request(scope)
        try:
            if request.method not in ("GET", "HEAD", "OPTIONS") or scope["path"] == "/api/auth/registration-form":
                origin = request.headers.get("origin")
                if (request.headers.get("sec-fetch-site") == "cross-site"
                    or origin and origin.rstrip("/") != str(request.base_url).rstrip("/")):
                    raise HTTPException(403, "Solicitud de origen no permitido")
            if scope["path"] in ("/api/auth/register", "/api/auth/login", "/api/auth/registration-form", "/api/auth/forgot-password", "/api/auth/reset-password"):
                await run_in_threadpool(request_budget, request)
            # Medical images have their own decoded-size validation and a 14 MB proxy cap.
            if request.method in ("POST", "PUT", "PATCH") and not scope["path"].endswith("/medical-orders"):
                cap = 16 * 1024 if scope["path"].startswith("/api/auth/") else 64 * 1024
                try:
                    length = int(request.headers.get("content-length", "0"))
                except ValueError:
                    raise HTTPException(400, "Tamaño de solicitud inválido")
                if length > cap:
                    raise HTTPException(413, "La solicitud supera el tamaño permitido")
                body = bytearray()
                more = True
                while more:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > cap:
                        raise HTTPException(413, "La solicitud supera el tamaño permitido")
                    more = message.get("more_body", False)
                delivered = False
                original_receive = receive
                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return await original_receive()
                receive = replay
            await self.app(scope, receive, send)
        except HTTPException as exc:
            await JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                               headers=exc.headers)(scope, receive, send)
