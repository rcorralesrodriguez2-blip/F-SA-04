"""Validación manual de cumplimiento independiente de la duración."""
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from fsa04 import create_app, repositories, services
from fsa04.config import Settings


class CumplimientoTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "manual.db"
        self.client = TestClient(create_app(Settings(database=self.database, secret_key="test-only")), follow_redirects=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        page = self.client.get("/")
        self.token = re.search(r'name="_csrf_token" value="([^"]+)"', page.text).group(1)
        self.datos = {
            "_csrf_token": self.token, "paciente": "Prueba", "identificacion": "test",
            "medico": "Prueba", "especialidad": "Ortopedia",
            "tipo_especialidad": "Especialidad Quirurgica", "observaciones": "",
            "fecha_solicitud": "2026-10-15T10:00:00",
            "fecha_respuesta": "2026-10-17T10:00:00", "cumplimiento": "SI",
        }

    def test_si_en_48_horas_y_no_en_una_hora(self):
        for cambios in ({}, {"fecha_respuesta": "2026-10-15T11:00", "cumplimiento": "NO"}):
            self.assertEqual(self.client.post("/guardar", data={**self.datos, **cambios}).status_code, 303)
        filas = repositories.listar_interconsultas(self.database)
        self.assertEqual((filas[0]["oportunidad"], filas[0]["cumplimiento"]), ("01:00:00", "NO"))
        self.assertEqual((filas[1]["oportunidad"], filas[1]["cumplimiento"]), ("48:00:00", "SI"))
        indicadores = services.obtener_indicadores(self.database)
        self.assertEqual(indicadores["incumplen"], 1)
        self.assertEqual(indicadores["superan_24_horas"], 1)
        self.assertEqual(indicadores["porcentaje_incumplimiento"], 50.0)

    def test_respuesta_exige_eleccion_valida_y_conserva_datos(self):
        for valor in ("", "OTRO", "1", "<script>"):
            with self.subTest(valor=valor):
                response = self.client.post("/guardar", data={**self.datos, "cumplimiento": valor})
                self.assertEqual(response.status_code, 400)
                self.assertIn('value="Prueba"', response.text)
        self.assertEqual(repositories.listar_interconsultas(self.database), [])

    def test_edicion_conserva_eleccion_al_cambiar_fechas(self):
        self.client.post("/guardar", data=self.datos)
        registro_id = repositories.listar_interconsultas(self.database)[0]["id"]
        page = self.client.get(f"/registros/{registro_id}/editar")
        self.assertIn('value="SI" selected', page.text)
        url = f"/registros/{registro_id}/actualizar"
        original = dict(repositories.obtener_interconsulta(registro_id, self.database))
        self.assertEqual(self.client.post(url, data={**self.datos, "cumplimiento": ""}).status_code, 400)
        self.assertEqual(dict(repositories.obtener_interconsulta(registro_id, self.database)), original)
        self.assertEqual(self.client.post(url, data={**self.datos, "fecha_respuesta": "2026-10-18T10:00"}).status_code, 303)
        registro = repositories.obtener_interconsulta(registro_id, self.database)
        self.assertEqual((registro["oportunidad"], registro["cumplimiento"]), ("72:00:00", "SI"))
        self.assertEqual(services.obtener_indicadores(self.database)["incumplen"], 0)
        self.assertEqual(self.client.post(url, data={**self.datos, "cumplimiento": "NO"}).status_code, 303)
        self.assertEqual(services.obtener_indicadores(self.database)["incumplen"], 1)

    def test_pendiente_no_adquiere_cumplimiento(self):
        response = self.client.post("/guardar", data={**self.datos, "fecha_respuesta": ""})
        self.assertEqual(response.status_code, 303)
        registro = repositories.listar_interconsultas(self.database)[0]
        self.assertIsNone(registro["oportunidad"])
        self.assertIsNone(registro["cumplimiento"])
        self.assertEqual(services.obtener_indicadores(self.database)["incumplen"], 0)

    def test_html_explica_la_validacion_manual(self):
        page = self.client.get("/")
        self.assertIn('name="cumplimiento"', page.text)
        self.assertIn("¿El paciente cumplió?", page.text)
        self.assertIn("El usuario valida el cumplimiento", page.text)
        indicators = self.client.get("/indicadores")
        self.assertIn("Incumplimiento registrado", indicators.text)
        self.assertIn("independiente del cumplimiento registrado", indicators.text)
