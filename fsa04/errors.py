"""Errores HTML del módulo, sin exponer detalles técnicos."""
import logging
import sqlite3

from starlette.exceptions import HTTPException

from .domain import DataIntegrityError
from .presentation import render
from .security import add_security_headers

logger = logging.getLogger(__name__)


def register_error_handlers(app):
    @app.exception_handler(sqlite3.DatabaseError)
    async def database_error(request, error):
        logger.error("Error de acceso a SQLite (%s).", type(error).__name__)
        return render(request, "error.html", status_code=503, mensaje="No fue posible acceder a los registros. Contacte al administrador si persiste.")

    @app.exception_handler(DataIntegrityError)
    async def invalid_data(request, error):
        logger.error("Duración almacenada inválida para los indicadores.")
        return render(request, "error.html", status_code=500, mensaje="Hay registros con duraciones inválidas. Solicite una revisión al administrador.")

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        mensajes = {404: "La página solicitada no existe.", 405: "La operación no está permitida.", 413: "El formulario supera el tamaño permitido."}
        response = render(request, "error.html", status_code=error.status_code, mensaje=mensajes.get(error.status_code, error.detail))
        response.headers.update(error.headers or {})
        return response

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        logger.error("Error inesperado del módulo (%s).", type(error).__name__)
        return add_security_headers(render(request, "error.html", status_code=500, mensaje="Ocurrió un error inesperado. Contacte al administrador."))
