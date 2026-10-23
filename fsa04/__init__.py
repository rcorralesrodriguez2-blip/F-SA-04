"""Fábricas FastAPI y montaje aislado en el sistema principal."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .assets import VersionedStaticFiles
from .database import init_db
from .errors import register_error_handlers
from .presentation import render
from .routes import router
from .security import add_security_headers


def create_module(settings: Settings, *, access_dependency=None, templates=None):
    """Crea una subaplicación sin inicializar datos ni alterar el anfitrión.

    access_dependency es una dependencia FastAPI para autorizar las pantallas.
    El middleware y las dependencias globales del portal no son equivalentes:
    las dependencias del portal no se heredan por un montaje.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    root = Path(__file__).resolve().parent
    app.state.settings = settings
    app.state.templates = templates or Jinja2Templates(directory=str(root / "templates"))
    dependencies = [Depends(access_dependency)] if access_dependency else []
    app.include_router(router, dependencies=dependencies)
    app.state.static_files = VersionedStaticFiles(root / "static")
    app.mount("/static", app.state.static_files, name="interconsultas.static")
    register_error_handlers(app)

    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > settings.max_content_length:
                    return add_security_headers(render(request, "error.html", status_code=413, mensaje="El formulario supera el tamaño permitido."))
                chunks.append(chunk)
            # Starlette reutiliza el cuerpo cacheado al pasar al siguiente handler.
            request._body = b"".join(chunks)
        return add_security_headers(await call_next(request))

    return app


def init_app(app: FastAPI, settings: Settings, *, url_prefix="/interconsultas", access_dependency=None, templates=None):
    """Monta una vez el módulo; el esquema debe crearse explícitamente."""
    if hasattr(app.state, "fsa04"):
        raise RuntimeError("F-SA-04 ya está registrado.")
    if not url_prefix.startswith("/") or url_prefix == "/":
        raise ValueError("Use un prefijo como /interconsultas.")
    module = create_module(settings, access_dependency=access_dependency, templates=templates)
    app.mount(url_prefix.rstrip("/"), module, name="fsa04")
    app.state.fsa04 = module
    return module


def create_app(settings: Settings | None = None):
    """Aplicación independiente con inicialización durante su lifespan."""
    settings = settings or Settings.from_env()
    app = create_module(settings)

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(init_db, settings.database)
        yield

    app.router.lifespan_context = lifespan
    return app
