"""CSRF con cookie firmada; no modifica las sesiones del anfitrión."""
import secrets

from fastapi import HTTPException, Request
from itsdangerous import BadData, URLSafeTimedSerializer


def signer(settings):
    return URLSafeTimedSerializer(settings.secret_key, salt="fsa04-csrf-v1")


def valid_token(token, settings):
    try:
        signer(settings).loads(token, max_age=settings.csrf_max_age)
        return True
    except BadData:
        return False


def csrf_token(request, settings):
    token = request.cookies.get(settings.csrf_cookie, "")
    if not token or not valid_token(token, settings):
        token = signer(settings).dumps(secrets.token_hex(32))
    return token


async def require_csrf(request: Request):
    settings = request.app.state.settings
    async with request.form(max_files=0, max_fields=20) as form:
        received = form.get("_csrf_token", "")
    expected = request.cookies.get(settings.csrf_cookie, "")
    if (not isinstance(received, str) or not expected
            or not secrets.compare_digest(expected.encode(), received.encode())
            or not valid_token(expected, settings)):
        raise HTTPException(400, "El formulario expiró o no es válido. Vuelva a abrirlo.")


def add_security_headers(response):
    for key, value in {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "same-origin",
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        ),
    }.items():
        response.headers.setdefault(key, value)
    response.headers.setdefault("Cache-Control", "no-store")
    return response
