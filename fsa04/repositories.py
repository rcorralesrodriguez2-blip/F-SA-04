"""Acceso a datos: SQL parametrizado y transacciones expl?citas."""
from .database import connect


def insertar_interconsulta(registro, database):
    with connect(database) as connection, connection:
        cursor = connection.execute(
            """INSERT INTO interconsultas
            (paciente, identificacion, especialidad, tipo_especialidad, medico,
             fecha_solicitud, fecha_respuesta, oportunidad, cumplimiento, observaciones)
            VALUES (:paciente, :identificacion, :especialidad, :tipo_especialidad,
                    :medico, :fecha_solicitud, :fecha_respuesta, :oportunidad,
                    :cumplimiento, :observaciones)""",
            registro,
        )
    return cursor.lastrowid


def listar_interconsultas(database, *, limite=None, antes=None, busqueda=""):
    with connect(database) as connection:
        condiciones, parametros = [], []
        if antes is not None:
            condiciones.append("id < ?")
            parametros.append(antes)
        if busqueda:
            connection.create_function("casefold", 1, str.casefold, deterministic=True)
            condiciones.append("(instr(casefold(paciente), ?) > 0 OR instr(casefold(identificacion), ?) > 0)")
            parametros.extend([busqueda.casefold()] * 2)
        consulta = "SELECT * FROM interconsultas"
        if condiciones:
            consulta += " WHERE " + " AND ".join(condiciones)
        consulta += " ORDER BY id DESC"
        if limite is not None:
            consulta += " LIMIT ?"
            parametros.append(limite)
        filas = connection.execute(
            consulta, parametros,
        ).fetchall()
        return [dict(fila) for fila in filas]


def obtener_interconsulta(registro_id, database):
    with connect(database) as connection:
        fila = connection.execute(
            "SELECT * FROM interconsultas WHERE id = ?", (registro_id,),
        ).fetchone()
        return dict(fila) if fila is not None else None


def actualizar_interconsulta(registro_id, registro, database):
    """Actualiza una sola orden existente; nunca inserta una copia."""
    with connect(database) as connection, connection:
        cursor = connection.execute(
            """UPDATE interconsultas SET
                paciente = :paciente, identificacion = :identificacion,
                especialidad = :especialidad, tipo_especialidad = :tipo_especialidad,
                medico = :medico, fecha_solicitud = :fecha_solicitud,
                fecha_respuesta = :fecha_respuesta, oportunidad = :oportunidad,
                cumplimiento = :cumplimiento, observaciones = :observaciones
               WHERE id = :registro_id""",
            {**registro, "registro_id": registro_id},
        )
        return cursor.rowcount == 1


def listar_datos_indicadores(database):
    """Itera campos de indicadores sin materializar todo el historial en memoria."""
    with connect(database) as connection:
        cursor = connection.execute(
            "SELECT tipo_especialidad, oportunidad, cumplimiento FROM interconsultas"
        )
        try:
            for fila in cursor:
                yield dict(fila)
        finally:
            cursor.close()


def listar_grupos_consolidado(database, anio):
    """Agrupa órdenes por solicitud, sin leer campos de pacientes.

    Las fechas históricas que SQLite no reconoce no pertenecen a un mes válido.
    """
    with connect(database) as connection:
        filas = connection.execute(
            """SELECT CAST(strftime('%m', fecha_solicitud) AS INTEGER) AS mes,
                      especialidad, tipo_especialidad, COUNT(*) AS cantidad
               FROM interconsultas
               WHERE strftime('%Y', fecha_solicitud) = ?
               GROUP BY mes, especialidad, tipo_especialidad
               ORDER BY mes, especialidad, tipo_especialidad""",
            (f"{anio:04d}",),
        ).fetchall()
        return [dict(fila) for fila in filas]
