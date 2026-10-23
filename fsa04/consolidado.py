"""Conteos mensuales por especialidad y tipo; sin datos personales."""
from .domain import ESPECIALIDADES, normalizar_etiqueta

MESES = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")
TIPOS_CONSOLIDADO = (
    "Especialidad Quirurgica", "Especialidad Clinica", "Sub-Especialidades",
)


def nueva_fila(nombre):
    return {"nombre": nombre, "meses": [0] * 12, "total": 0}


def acumular(filas, nombre, mes, cantidad):
    etiqueta = " ".join((nombre or "").split()) or "Sin especificar"
    clave = normalizar_etiqueta(etiqueta)
    fila = filas.setdefault(clave, nueva_fila(etiqueta))
    fila["meses"][mes - 1] += cantidad
    fila["total"] += cantidad


def calcular_consolidado(grupos):
    """Cada grupo contiene mes, especialidad, tipo y cantidad del año elegido.

    Conserva categorías históricas ajenas al catálogo para no perder conteos.
    Las categorías del catálogo se muestran incluso cuando tienen cero órdenes.
    """
    especialidades = {normalizar_etiqueta(nombre): nueva_fila(nombre) for nombre in ESPECIALIDADES}
    tipos = {normalizar_etiqueta(nombre): nueva_fila(nombre) for nombre in TIPOS_CONSOLIDADO}
    total = nueva_fila("TOTAL")
    for grupo in grupos:
        mes, cantidad = grupo["mes"], grupo["cantidad"]
        acumular(especialidades, grupo["especialidad"], mes, cantidad)
        acumular(tipos, grupo["tipo_especialidad"], mes, cantidad)
        total["meses"][mes - 1] += cantidad
        total["total"] += cantidad
    return {
        "meses": MESES,
        "por_especialidad": list(especialidades.values()),
        "por_tipo": list(tipos.values()),
        "totales": total,
    }
