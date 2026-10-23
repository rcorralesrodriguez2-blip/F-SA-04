"""Catálogos y reglas puras: no dependen del framework HTTP ni de SQLite."""
from datetime import datetime, timedelta, timezone
import re
import unicodedata

ESPECIALIDADES = (
    "Cirugía general", "Ginecológica", "Maxilofacial", "Ortopedia",
    "Hemodinamia", "Anestesiología", "Gastroenterología", "Medicina interna",
    "Pediatría", "Psicología", "Oftalmología", "Cardiología", "Cardiovascular",
    "Cirugía de tórax", "Cirugía pediátrica", "Cirugía plástica y estética",
    "Dermatológica", "Electrofisiología",
    "Endovascular neurocirugía (vascular y angiológica)", "Fisiatría",
    "Hematología", "Hepatología", "Infectología", "Medicina del dolor",
    "Nefrología", "Neumología", "Neurocirugía", "Neurología",
    "Otorrinolaringólogo", "Psiquiatría", "Radiología intervencionista",
    "Toxicología", "Urología", "Vascular periférico",
)
TIPO_DE_ESPECIALIDADES = (
    "Especialidad Clinica", "Especialidad Quirurgica", "Sub-Especialidades",
)
UMBRAL_SEGUNDOS = 24 * 60 * 60
CAMPOS = (
    "paciente", "identificacion", "especialidad", "tipo_especialidad",
    "medico", "fecha_solicitud", "fecha_respuesta", "observaciones", "cumplimiento",
)
OBLIGATORIOS = (
    "paciente", "identificacion", "especialidad", "tipo_especialidad",
    "medico", "fecha_solicitud",
)


class ValidationError(ValueError):
    """Entrada del usuario que no satisface las reglas de negocio."""


class DataIntegrityError(ValueError):
    """Registro almacenado que no puede utilizarse en los indicadores."""


def resolver_anio(valor=None):
    if valor is None:
        return datetime.now(timezone(timedelta(hours=-5))).year
    texto = str(valor)
    if not re.fullmatch(r"[0-9]{1,4}", texto) or not 1 <= int(texto) <= 9999:
        raise ValidationError("Seleccione un año válido entre 1 y 9999.")
    return int(texto)


def normalizar_entrada(datos):
    """Prepara la entrada de cualquier cliente sin aceptar campos derivados."""
    return {campo: str(datos.get(campo) or "").strip() for campo in CAMPOS}


def estado_formulario(datos):
    """Reglas de respuesta y vista previa compartidas con el guardado."""
    respondida = bool(datos.get("fecha_respuesta"))
    estado = {
        "cumplimiento_obligatorio": respondida,
        "cumplimiento_habilitado": respondida,
        "oportunidad": None,
        "mensaje": "Pendiente de respuesta o de fechas completas.",
        "valido": True,
    }
    try:
        inicio = interpretar_fecha(datos.get("fecha_solicitud", ""))
        fin = interpretar_fecha(datos.get("fecha_respuesta", ""))
        if inicio is not None and fin is not None:
            estado["oportunidad"] = calcular_oportunidad(inicio, fin)
            estado["mensaje"] = (
                f"Vista previa de oportunidad: {estado['oportunidad']}. "
                "El cumplimiento lo valida el usuario seleccionando Sí o No."
            )
    except ValidationError as exc:
        estado.update(valido=False, mensaje=str(exc))
    return estado


def normalizar_tipo(valor):
    texto = unicodedata.normalize("NFKD", valor.strip())
    return "".join(c for c in texto if not unicodedata.combining(c)).upper()


def normalizar_etiqueta(valor):
    """Unifica tildes, mayúsculas y espacios para catálogos e históricos."""
    return normalizar_tipo(" ".join((valor or "").split()))


def interpretar_fecha(valor):
    if not valor:
        return None
    try:
        fecha = datetime.fromisoformat(valor)
    except ValueError as exc:
        raise ValidationError("Formato de fecha y hora invalido.") from exc
    if fecha.tzinfo is not None:
        raise ValidationError("Ingrese fechas locales sin zona horaria.")
    return fecha


def segundos_a_hms(segundos):
    horas, resto = divmod(segundos, 3600)
    minutos, segundos_restantes = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{segundos_restantes:02d}"


def calcular_oportunidad(inicio, fin):
    if fin is None:
        return None
    delta = (fin - inicio).total_seconds()
    if delta < 0:
        raise ValidationError("La fecha de respuesta no puede ser anterior a la solicitud.")
    segundos = int(delta)
    return segundos_a_hms(segundos)


def segundos_desde_oportunidad(valor):
    try:
        partes = [int(parte) for parte in valor.split(":")]
    except (AttributeError, ValueError) as exc:
        raise DataIntegrityError("Duracion almacenada invalida.") from exc
    if len(partes) != 3 or partes[0] < 0 or not 0 <= partes[1] < 60 or not 0 <= partes[2] < 60:
        raise DataIntegrityError("Duracion almacenada invalida.")
    horas, minutos, segundos = partes
    return horas * 3600 + minutos * 60 + segundos


def validar_interconsulta(datos):
    """Devuelve un registro nuevo validado y con valores calculados en servidor."""
    datos = normalizar_entrada(datos)
    if any(not datos[c] for c in OBLIGATORIOS):
        raise ValidationError("Complete todos los campos obligatorios.")
    especialidades = {normalizar_etiqueta(nombre): nombre for nombre in ESPECIALIDADES}
    especialidad = especialidades.get(normalizar_etiqueta(datos["especialidad"]))
    if especialidad is None:
        raise ValidationError("Seleccione una especialidad valida.")
    tipos = {normalizar_etiqueta(tipo): tipo for tipo in TIPO_DE_ESPECIALIDADES}
    tipo = tipos.get(normalizar_etiqueta(datos["tipo_especialidad"]))
    if tipo is None:
        raise ValidationError("Seleccione un tipo de especialidad valido.")
    if any(len(datos[c]) > 250 for c in OBLIGATORIOS if c != "fecha_solicitud") or len(datos["observaciones"]) > 2000:
        raise ValidationError("Uno de los textos excede la longitud permitida.")
    inicio = interpretar_fecha(datos["fecha_solicitud"])
    fin = interpretar_fecha(datos["fecha_respuesta"])
    oportunidad = calcular_oportunidad(inicio, fin)
    cumplimiento = normalizar_tipo(datos.get("cumplimiento") or "")
    if cumplimiento not in {"", "SI", "NO"}:
        raise ValidationError("Seleccione Sí o No para el cumplimiento.")
    if fin is not None and not cumplimiento:
        raise ValidationError("Valide si el paciente cumplió: seleccione Sí o No.")
    if fin is None:
        cumplimiento = None
    return {
        **datos,
        "especialidad": especialidad,
        "tipo_especialidad": tipo,
        "fecha_solicitud": inicio.isoformat(timespec="seconds"),
        "fecha_respuesta": fin.isoformat(timespec="seconds") if fin else None,
        "oportunidad": oportunidad,
        "cumplimiento": cumplimiento,
    }
