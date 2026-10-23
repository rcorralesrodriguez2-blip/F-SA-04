"""Edición y registro de respuesta sobre órdenes existentes; SQLite temporal."""
import re
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from fsa04 import create_app, init_app, repositories, services
from fsa04.config import Settings
from fsa04.database import connect


class EdicionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "edit.db"
        self.settings = Settings(database=self.database, secret_key="test-only")
        self.client = TestClient(create_app(self.settings), follow_redirects=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.datos = {
            "paciente": "Paciente de prueba", "identificacion": "test", "medico": "Prueba",
            "especialidad": "Ortopedia", "tipo_especialidad": "Especialidad Quirurgica",
            "fecha_solicitud": "2026-10-15T10:00:00", "fecha_respuesta": "",
            "observaciones": "Pendiente de valoración", "cumplimiento": "SI",
        }
        self.registro_id = services.guardar_interconsulta(self.datos, self.database)
        self.edit_url = f"/registros/{self.registro_id}/editar"
        self.update_url = f"/registros/{self.registro_id}/actualizar"

    def formulario(self, client=None, prefix=""):
        page = (client or self.client).get(prefix + self.edit_url)
        self.assertEqual(page.status_code, 200)
        token = re.search(r'name="_csrf_token" value="([^"]+)"', page.text).group(1)
        return {**self.datos, "_csrf_token": token}

    def registro(self):
        return dict(repositories.obtener_interconsulta(self.registro_id, self.database))

    def test_carga_formulario_y_accion_desde_historial(self):
        page = self.client.get(self.edit_url)
        self.assertIn('value="Paciente de prueba"', page.text)
        self.assertIn('value="2026-10-15T10:00:00"', page.text)
        self.assertIn('value=""', page.text)
        self.assertIn(f'action="{self.update_url}"', page.text)
        self.assertIn("Guardar cambios", page.text)
        self.assertIn("Cancelar", page.text)
        self.assertIn('aria-current="page">Historial de registros', page.text)
        history = self.client.get("/tabla")
        self.assertIn(f'href="{self.edit_url}"', history.text)
        self.assertIn("Registrar respuesta", history.text)

    def test_responder_actualiza_mismo_id_y_recalcula_indicadores(self):
        response = self.client.post(self.update_url, data={
            **self.formulario(), "fecha_respuesta": "2026-10-16T10:00:01",
            "observaciones": "Valoración realizada", "cumplimiento": "NO", "oportunidad": "00:00:00",
        })
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/tabla?actualizado=1")
        registro = self.registro()
        self.assertEqual(registro["id"], self.registro_id)
        self.assertEqual(registro["cumplimiento"], "NO")
        self.assertEqual(registro["oportunidad"], "24:00:01")
        self.assertEqual(len(repositories.listar_interconsultas(self.database)), 1)
        self.assertEqual(services.obtener_indicadores(self.database)["incumplen"], 1)
        self.assertEqual(services.obtener_consolidado(self.database, 2026)["totales"]["total"], 1)
        history = self.client.get(response.headers["location"])
        self.assertIn("Interconsulta actualizada correctamente", history.text)
        self.assertNotIn("Registrar respuesta", history.text)

    def test_corregir_solicitud_mueve_consolidado_y_respeta_umbral(self):
        response = self.client.post(self.update_url, data={
            **self.formulario(), "fecha_solicitud": "2025-12-31T10:00:00",
            "fecha_respuesta": "2026-01-01T10:00:00",
        })
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.registro()["cumplimiento"], "SI")
        self.assertEqual(services.obtener_consolidado(self.database, 2026)["totales"]["total"], 0)
        self.assertEqual(services.obtener_consolidado(self.database, 2025)["totales"]["meses"][11], 1)

    def test_validacion_conserva_formulario_y_base_sin_cambios(self):
        original = self.registro()
        for cambios in (
            {"fecha_respuesta": "2026-10-14T10:00"}, {"fecha_solicitud": "inválida"},
            {"paciente": ""}, {"especialidad": "Desconocida"}, {"observaciones": "x" * 2001},
        ):
            with self.subTest(cambios=cambios):
                response = self.client.post(self.update_url, data={**self.formulario(), **cambios})
                self.assertEqual(response.status_code, 400)
                self.assertIn(f'action="{self.update_url}"', response.text)
                self.assertIn("Guardar cambios", response.text)
                self.assertEqual(self.registro(), original)

    def test_csrf_y_registro_inexistente(self):
        original = self.registro()
        for token in ("", "incorrecto"):
            self.assertEqual(self.client.post(self.update_url, data={**self.datos, "_csrf_token": token}).status_code, 400)
        self.assertEqual(self.registro(), original)
        self.assertEqual(self.client.get("/registros/999/editar").status_code, 404)
        self.assertEqual(self.client.post("/registros/999/actualizar", data=self.formulario()).status_code, 404)
        self.assertEqual(len(repositories.listar_interconsultas(self.database)), 1)

    def test_historicos_precargan_catalogos_y_escape_html(self):
        with connect(self.database) as connection, connection:
            connection.execute(
                "UPDATE interconsultas SET especialidad=?, tipo_especialidad=?, paciente=? WHERE id=?",
                ("Infectologia", "ESPECIALIDAD CLINICA", '<script>prueba</script>', self.registro_id),
            )
        page = self.client.get(self.edit_url)
        self.assertIn('value="Infectología" selected', page.text)
        self.assertIn('value="Especialidad Clinica" selected', page.text)
        self.assertIn("&lt;script&gt;prueba&lt;/script&gt;", page.text)
        self.assertNotIn("<script>prueba</script>", page.text)

    def test_editar_respondida_y_volver_a_pendiente(self):
        data = self.formulario()
        self.client.post(self.update_url, data={**data, "fecha_respuesta": "2026-10-15T11:00"})
        self.assertEqual(self.registro()["oportunidad"], "01:00:00")
        self.client.post(self.update_url, data={**self.formulario(), "fecha_respuesta": ""})
        registro = self.registro()
        for campo in ("fecha_respuesta", "oportunidad", "cumplimiento"):
            self.assertIsNone(registro[campo])

    def test_prefijo_y_autorizacion_tambien_en_edicion(self):
        host = FastAPI()
        init_app(host, self.settings, url_prefix="/hospital")
        with TestClient(host, follow_redirects=False) as client:
            data = self.formulario(client, "/hospital")
            self.assertIn(f'action="/hospital{self.update_url}"', client.get("/hospital" + self.edit_url).text)
            response = client.post("/hospital" + self.update_url, data={**data, "fecha_respuesta": "2026-10-15T11:00"})
            self.assertEqual(response.headers["location"], "/hospital/tabla?actualizado=1")

        def denegar():
            raise HTTPException(403, "Acceso denegado")

        protected = FastAPI()
        init_app(protected, self.settings, access_dependency=denegar)
        with TestClient(protected) as client:
            self.assertEqual(client.get("/interconsultas" + self.edit_url).status_code, 403)
            self.assertEqual(client.post("/interconsultas" + self.update_url, data=data).status_code, 403)
