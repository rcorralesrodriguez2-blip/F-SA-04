"""Casos de uso: coordina reglas de negocio y persistencia."""
from contextlib import closing

from . import repositories
from .consolidado import calcular_consolidado
from .domain import (
    UMBRAL_SEGUNDOS, normalizar_etiqueta, segundos_a_hms,
    segundos_desde_oportunidad, validar_interconsulta,
    CAMPOS, ESPECIALIDADES, TIPO_DE_ESPECIALIDADES, estado_formulario,
    resolver_anio, normalizar_entrada,
)

CATEGORIAS = (
    (None, "Promedio de espera para valoracion de medico especialista en hospitalizacion"),
    ("ESPECIALIDAD QUIRURGICA", "Promedio de espera por especialidad quirurgica"),
    ("ESPECIALIDAD CLINICA", "Promedio de espera por especialidad clinica"),
    ("SUB-ESPECIALIDADES", "Promedio de espera por sub-especialidades"),
)


def preparar_formulario(datos=None):
    datos = normalizar_entrada(datos or {})
    return {
        "datos": datos,
        "especialidades": ESPECIALIDADES,
        "tipos_de_especialidades": TIPO_DE_ESPECIALIDADES,
        "estado": estado_formulario(datos),
    }


def obtener_historial(database):
    return repositories.listar_interconsultas(database)


def obtener_pagina_historial(database, *, antes=None, busqueda=""):
    """Lee como máximo 51 filas, sin contar ni materializar todo el historial."""
    filas = repositories.listar_interconsultas(
        database, limite=51, antes=antes, busqueda=busqueda,
    )
    return {
        "registros": filas[:50],
        "siguiente": filas[49]["id"] if len(filas) > 50 else None,
    }


def obtener_formulario_edicion(registro_id, database):
    registro = repositories.obtener_interconsulta(registro_id, database)
    if registro is None:
        return None
    datos = {campo: registro[campo] or "" for campo in CAMPOS}
    for campo, catalogo in (("especialidad", ESPECIALIDADES), ("tipo_especialidad", TIPO_DE_ESPECIALIDADES)):
        nombres = {normalizar_etiqueta(nombre): nombre for nombre in catalogo}
        datos[campo] = nombres.get(normalizar_etiqueta(datos[campo]), datos[campo])
    return datos


def guardar_interconsulta(datos, database):
    return repositories.insertar_interconsulta(validar_interconsulta(datos), database)


def actualizar_interconsulta(registro_id, datos, database):
    """Revalida fechas y recalcula los campos derivados antes de actualizar."""
    if repositories.obtener_interconsulta(registro_id, database) is None:
        return False
    return repositories.actualizar_interconsulta(
        registro_id, validar_interconsulta(datos), database,
    )


def obtener_indicadores(database):
    # Cierra el cursor y la conexión incluso si un dato impide el cálculo.
    with closing(repositories.listar_datos_indicadores(database)) as filas:
        return calcular_indicadores(filas)


def obtener_consolidado(database, anio=None):
    anio = resolver_anio(anio)
    return {"anio": anio, **calcular_consolidado(repositories.listar_grupos_consolidado(database, anio))}


def calcular_indicadores(filas):
    """Acumula una sola vez; mantiene pendientes en el denominador."""
    acumulados = {tipo: [0, 0, 0] for tipo, _ in CATEGORIAS}
    otros = [0, 0, 0]
    incumplen = superan_24_horas = validadas = 0
    for fila in filas:
        tipo = normalizar_etiqueta(fila["tipo_especialidad"])
        duracion = (
            segundos_desde_oportunidad(fila["oportunidad"])
            if fila["oportunidad"] is not None else None
        )
        # No se descartan del desglose los tipos históricos no catalogados.
        grupo = acumulados.get(tipo, otros)
        for acumulado in (acumulados[None], grupo):
            acumulado[0] += 1
            if duracion is not None:
                acumulado[1] += 1
                acumulado[2] += duracion
        if duracion is not None:
            cumplimiento = fila["cumplimiento"]
            validadas += cumplimiento in {"SI", "NO"}
            incumplen += cumplimiento == "NO"
            superan_24_horas += duracion > UMBRAL_SEGUNDOS

    metricas = []
    grupos = [(titulo, acumulados[tipo]) for tipo, titulo in CATEGORIAS]
    if otros[0]:
        grupos.append(("Promedio de espera por otros tipos de especialidad", otros))
    for titulo, (total, respondidas, suma) in grupos:
        promedio = round(suma / total) if total else None
        metricas.append({
            "titulo": titulo,
            "total_ordenes": total,
            "ordenes_respondidas": respondidas,
            "suma": segundos_a_hms(suma),
            "promedio": segundos_a_hms(promedio) if promedio is not None else None,
        })
    total, respondidas, _ = acumulados[None]
    return {
        "metricas": metricas,
        "total_ordenes": total,
        "incumplen": incumplen,
        "superan_24_horas": superan_24_horas,
        "validadas": validadas,
        "sin_validar": respondidas - validadas,
        "porcentaje_incumplimiento": round(100 * incumplen / total, 1) if total else 0,
    }
