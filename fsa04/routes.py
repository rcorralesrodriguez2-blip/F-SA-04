"""Adaptadores HTTP FastAPI; SQLite se ejecuta fuera del bucle asíncrono."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from urllib.parse import urlencode

from . import services
from .domain import CAMPOS, ValidationError
from .presentation import module_url, render
from .security import require_csrf

router = APIRouter()


def render_formulario(request, datos=None, status_code=200, mensajes=None, registro_id=None):
    return render(
        request, "formulario.html", status_code=status_code,
        **services.preparar_formulario(datos), mensajes=mensajes or [],
        registro_id=registro_id,
        **({"active_endpoint": "interconsultas.tabla"} if registro_id else {}),
    )


@router.get("/", name="interconsultas.formulario")
def formulario(request: Request):
    return render_formulario(request)


@router.post("/vista-previa", name="interconsultas.vista_previa", dependencies=[Depends(require_csrf)])
async def vista_previa(request: Request):
    async with request.form(max_files=0, max_fields=20) as form:
        datos = {campo: form.get(campo, "") for campo in ("fecha_solicitud", "fecha_respuesta")}
    estado = services.preparar_formulario(datos)["estado"]
    return JSONResponse(estado)


@router.post("/guardar", name="interconsultas.guardar", dependencies=[Depends(require_csrf)])
async def guardar(request: Request):
    async with request.form(max_files=0, max_fields=20) as form:
        datos = {campo: form.get(campo, "") for campo in CAMPOS}
    try:
        await run_in_threadpool(services.guardar_interconsulta, datos, request.app.state.settings.database)
    except ValidationError as exc:
        return render_formulario(request, datos, 400, [("danger", str(exc))])
    # Mensaje sin datos de pacientes; no requiere compartir la sesión del portal.
    return RedirectResponse(module_url(request, "interconsultas.tabla") + "?guardado=1", status_code=303)


@router.get("/tabla", name="interconsultas.tabla")
def tabla(request: Request):
    busqueda = request.query_params.get("q", "").strip()
    if len(busqueda) > 250:
        raise HTTPException(400, "La búsqueda admite hasta 250 caracteres.")
    cursor = request.query_params.get("antes")
    antes = None
    if cursor is not None:
        try:
            antes = int(cursor) if len(cursor) <= 19 else 0
        except ValueError:
            antes = 0
        if not 0 < antes <= 9223372036854775807:
            raise HTTPException(400, "La página solicitada no es válida.")
    mensajes = [("success", "Interconsulta guardada correctamente.")] if request.query_params.get("guardado") == "1" else []
    if request.query_params.get("actualizado") == "1":
        mensajes = [("success", "Interconsulta actualizada correctamente.")]
    pagina = services.obtener_pagina_historial(
        request.app.state.settings.database, antes=antes, busqueda=busqueda,
    )
    base = module_url(request, "interconsultas.tabla")
    return render(
        request, "tabla.html", registros=pagina["registros"], mensajes=mensajes,
        busqueda=busqueda, antes=antes,
        primera_url=base + "?" + urlencode({"q": busqueda}),
        siguiente_url=(base + "?" + urlencode({"q": busqueda, "antes": pagina["siguiente"]}))
        if pagina["siguiente"] is not None else None,
    )


@router.get("/registros/{registro_id:int}/editar", name="interconsultas.editar")
def editar(request: Request, registro_id: int):
    datos = services.obtener_formulario_edicion(registro_id, request.app.state.settings.database)
    if datos is None:
        raise HTTPException(404, "La interconsulta solicitada no existe.")
    return render_formulario(request, datos, registro_id=registro_id)


@router.post(
    "/registros/{registro_id:int}/actualizar", name="interconsultas.actualizar",
    dependencies=[Depends(require_csrf)],
)
async def actualizar(request: Request, registro_id: int):
    database = request.app.state.settings.database
    async with request.form(max_files=0, max_fields=20) as form:
        datos = {campo: form.get(campo, "") for campo in CAMPOS}
    try:
        actualizado = await run_in_threadpool(services.actualizar_interconsulta, registro_id, datos, database)
    except ValidationError as exc:
        return render_formulario(request, datos, 400, [("danger", str(exc))], registro_id)
    if not actualizado:
        raise HTTPException(404, "La interconsulta solicitada ya no existe.")
    return RedirectResponse(module_url(request, "interconsultas.tabla") + "?actualizado=1", status_code=303)


@router.get("/indicadores", name="interconsultas.indicadores")
def indicadores(request: Request):
    return render(request, "indicadores.html", **services.obtener_indicadores(request.app.state.settings.database))


@router.get("/consolidado", name="interconsultas.consolidado")
def consolidado(request: Request):
    try:
        reporte = services.obtener_consolidado(request.app.state.settings.database, request.query_params.get("anio"))
    except ValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    return render(
        request, "consolidado.html", **reporte,
    )
