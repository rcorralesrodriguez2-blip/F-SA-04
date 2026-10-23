"""Regresión de clasificación, estados vacíos y lectura incremental."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from fsa04 import create_app, repositories, services
from fsa04.config import Settings
from fsa04.database import connect, init_db
from fsa04.domain import DataIntegrityError


class IndicadoresTests(unittest.TestCase):
    def fila(self, tipo, oportunidad=None, cumplimiento=None):
        return {"tipo_especialidad": tipo, "oportunidad": oportunidad, "cumplimiento": cumplimiento}

    def test_espacios_repetidos_y_categorias_desconocidas_no_pierden_subtotales(self):
        resultado = services.calcular_indicadores(iter([
            self.fila(" especialidad   CLÍNICA ", "02:00:00", "SI"),
            self.fila("ESPECIALIDAD\tQUIRURGICA", "48:00:00", "NO"),
            self.fila("Tipo histórico", "01:00:00", "SI"),
            self.fila(None),
        ]))
        general, quirurgica, clinica, sub, otros = resultado["metricas"]
        self.assertEqual(general["total_ordenes"], 4)
        self.assertEqual(clinica["total_ordenes"], 1)
        self.assertEqual(quirurgica["total_ordenes"], 1)
        self.assertEqual(sub["total_ordenes"], 0)
        self.assertEqual(otros["total_ordenes"], 2)
        self.assertEqual(otros["promedio"], "00:30:00")
        self.assertEqual(sum(m["total_ordenes"] for m in resultado["metricas"][1:]), 4)
        self.assertEqual(resultado["validadas"], 3)
        self.assertEqual(resultado["porcentaje_incumplimiento"], 25.0)

    def test_una_sola_pasada_sin_convertir_iterador_en_lista(self):
        class SoloUnaPasada:
            def __init__(self):
                self.usado = False

            def __iter__(self):
                if self.usado:
                    raise AssertionError("Se volvió a recorrer el origen.")
                self.usado = True
                yield {"tipo_especialidad": "Especialidad Clinica", "oportunidad": "24:00:00", "cumplimiento": "NO"}
                yield {"tipo_especialidad": "Especialidad Clinica", "oportunidad": None, "cumplimiento": None}

        resultado = services.calcular_indicadores(SoloUnaPasada())
        self.assertEqual(resultado["metricas"][0]["promedio"], "12:00:00")
        self.assertEqual(resultado["superan_24_horas"], 0)
        self.assertEqual(resultado["incumplen"], 1)

    def test_cierra_lectura_incluso_con_duracion_corrupta(self):
        for oportunidad in ("01:00:00", "corrupta"):
            cerrado = []

            def leer():
                try:
                    yield self.fila("Especialidad Clinica", oportunidad, "SI")
                finally:
                    cerrado.append(True)

            with patch("fsa04.repositories.listar_datos_indicadores", return_value=leer()):
                if oportunidad == "corrupta":
                    with self.assertRaises(DataIntegrityError):
                        services.obtener_indicadores("unused")
                else:
                    services.obtener_indicadores("unused")
            self.assertEqual(cerrado, [True])

    def test_cursor_real_no_materializa_y_se_cierra(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "cursor.db"
            init_db(database)
            with connect(database) as connection, connection:
                connection.execute("""INSERT INTO interconsultas
                    (paciente, identificacion, especialidad, tipo_especialidad, medico, fecha_solicitud)
                    VALUES ('Prueba', 'test', 'Ortopedia', 'Especialidad Clinica', 'Prueba', '2026-10-16T10:00')""")
            with patch("fsa04.database.sqlite3.connect", wraps=sqlite3.connect) as opened:
                filas = repositories.listar_datos_indicadores(database)
                self.assertEqual(opened.call_count, 0)
                self.assertEqual(next(filas)["oportunidad"], None)
                self.assertEqual(opened.call_count, 1)
                filas.close()
            # En Windows la limpieza del directorio también requiere cerrar SQLite.

    def test_estados_sin_ordenes_sin_validaciones_y_validacion_incompleta(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = Settings(database=Path(temporary) / "states.db", secret_key="test-only")
            with TestClient(create_app(settings)) as client:
                pagina = client.get("/indicadores")
                self.assertIn("Sin órdenes", pagina.text)
                self.assertNotIn('display-4 fw-bold text-success', pagina.text)
                for oportunidad, esperado in ((None, "Sin validaciones"), ("01:00:00", "no tienen validación")):
                    with patch("fsa04.repositories.listar_datos_indicadores", return_value=(fila for fila in [self.fila("Especialidad Clinica", oportunidad)])):
                        pagina = client.get("/indicadores")
                    self.assertEqual(pagina.status_code, 200)
                    self.assertIn(esperado, pagina.text)
                    self.assertNotIn('display-4 fw-bold text-success', pagina.text)

    def test_resultados_de_la_captura_se_conservan(self):
        resultado = services.calcular_indicadores([
            self.fila("Especialidad Quirurgica", "42:08:46", "SI"),
            self.fila("ESPECIALIDAD CLINICA", "23:59:53", "SI"),
        ])
        self.assertEqual(resultado["metricas"][0]["suma"], "66:08:39")
        self.assertEqual(resultado["metricas"][0]["promedio"], "33:04:20")
        self.assertEqual(resultado["porcentaje_incumplimiento"], 0)
        self.assertEqual(resultado["superan_24_horas"], 1)
