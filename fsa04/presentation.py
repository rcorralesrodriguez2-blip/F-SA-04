"""Contexto Jinja y enlaces relativos al montaje ASGI."""
from starlette.routing import NoMatchFound
from urllib.parse import urlencode

from .security import csrf_token


def module_url(request, name, **params):
    if "filename" in params:
        params["path"] = params.pop("filename")
    try:
        path = request.app.url_path_for(name, **params)
    except NoMatchFound:
        # La plantilla compartida también puede enlazar a rutas del portal.
        return str(request.url_for(name, **params))
    url = request.scope.get("root_path", "").rstrip("/") + str(path)
    if name == "interconsultas.static":
        version = request.app.state.static_files.versions.get(params.get("path"))
        if version:
            url += "?" + urlencode({"v": version})
    return url


def render(request, template, *, status_code=200, **context):
    settings = request.app.state.settings
    token = csrf_token(request, settings)
    response = request.app.state.templates.TemplateResponse(
        request=request, name="interconsultas/" + template,
        context={
            "config": {
                "FSA04_BASE_TEMPLATE": settings.base_template,
                "FSA04_LOAD_BOOTSTRAP": settings.load_bootstrap,
                "FSA04_SHOW_SIDEBAR": settings.show_sidebar,
                "FSA04_TITLE": settings.title,
            },
            "url_for": lambda name, **params: module_url(request, name, **params),
            "active_endpoint": getattr(request.scope.get("route"), "name", ""),
            "csrf_value": token,
            "mensajes": [],
            **context,
        }, status_code=status_code,
    )
    response.set_cookie(
        settings.csrf_cookie, token,
        path=request.scope.get("root_path", "").rstrip("/") + "/",
        httponly=True, secure=settings.cookie_secure, samesite="lax",
        max_age=settings.csrf_max_age,
    )
    return response
