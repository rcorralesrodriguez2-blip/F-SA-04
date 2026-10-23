"""SQLite explícito, sin contexto global ni dependencia del framework."""
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS interconsultas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente TEXT NOT NULL,
    identificacion TEXT NOT NULL,
    especialidad TEXT NOT NULL,
    tipo_especialidad TEXT NOT NULL,
    medico TEXT NOT NULL,
    fecha_solicitud TEXT NOT NULL,
    fecha_respuesta TEXT,
    oportunidad TEXT,
    cumplimiento TEXT CHECK (cumplimiento IN ('SI','NO') OR cumplimiento IS NULL),
    observaciones TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_identificacion ON interconsultas(identificacion);
"""


@contextmanager
def connect(database):
    """Abre una conexión local a la operación y la cierra también ante errores."""
    connection = sqlite3.connect(str(database), timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def init_db(database):
    """Crea el esquema ausente; no borra ni transforma registros."""
    with connect(database) as connection:
        connection.executescript(SCHEMA)
        connection.commit()
