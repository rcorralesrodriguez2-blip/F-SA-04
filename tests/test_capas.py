"""Contratos entre presentación, negocio y persistencia con datos sintéticos."""
import re
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from fsa04 import create_app, init_app, repositories, services
from fsa04.config import Settings
from fsa04.domain import ValidationError


class CapasTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "capas.db"
        self.settings = Settings(database=self.database, secret_key="test-only")
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.token = re.search(r'name="_csrf_token" value="([^"]+)"', self.client.get("/").text).group(1)
        self.datos = {
            "paciente": "  Prueba  ", "identificacion": " test ",
            "medico": " Prueba ", "especialidad": " ortopedia ",
            "tipo_especialidad": " Especialidad Quirurgica ",
            "fecha_solicitud": " 2026-10-19T10:00:00 ",
            "fecha_respuesta": " 2026-10-19T11:00:00 ",
            "cumplimiento": " no ", "oportunidad": "999:00:00",
            "_csrf_token": "no debe persistirse",
        }

    def test_servicio_valida_sin_depender_de_http(self):
        original = self.datos.copy()
        registro_id = services.guardar_interconsulta(self.datos, self.database)
        registro = repositories.obtener_interconsulta(registro_id, self.database)
        self.assertEqual(registro["paciente"], "Prueba")
        self.assertEqual(registro["oportunidad"], "01:00:00")
        self.assertEqual(registro["cumplimiento"], "NO")
        self.assertNotIn("_csrf_token", registro)
        self.assertEqual(self.datos, original)
        for datos in ({}, {**self.datos, "paciente": "   "}):
            with self.assertRaises(ValidationError):
                services.guardar_interconsulta(datos, self.database)
        self.assertEqual(len(repositories.listar_interconsultas(self.database)), 1)

    def test_persistencia_entrega_diccionarios_incluso_incrementalmente(self):
        registro_id = services.guardar_interconsulta(self.datos, self.database)
        self.assertIsInstance(repositories.obtener_interconsulta(registro_id, self.database), dict)
        self.assertIsNone(repositories.obtener_interconsulta(registro_id + 1, self.database))
        for filas in (
            repositories.listar_interconsultas(self.database),
            repositories.listar_grupos_consolidado(self.database, 2026),
            repositories.listar_datos_indicadores(self.database),
        ):
            self.assertTrue(all(isinstance(fila, dict) for fila in filas))

    def test_vista_previa_calcula_en_servidor_sin_guardar(self):
        for cambios, oportunidad, valido, obligatorio in (
            ({}, "01:00:00", True, True),
            ({"fecha_respuesta": ""}, None, True, False),
            ({"fecha_respuesta": "2026-10-18T10:00"}, None, False, True),
            ({"fecha_solicitud": "invalida"}, None, False, True),
        ):
            with self.subTest(cambios=cambios):
                response = self.client.post("/vista-previa", data={
                    **self.datos, **cambios, "_csrf_token": self.token,
                })
                self.assertEqual(response.status_code, 200)
                estado = response.json()
                self.assertEqual(estado["oportunidad"], oportunidad)
                self.assertEqual(estado["valido"], valido)
                self.assertEqual(estado["cumplimiento_obligatorio"], obligatorio)
                self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(repositories.listar_interconsultas(self.database), [])
        self.assertEqual(self.client.post("/vista-previa", data=self.datos).status_code, 400)

    def test_vista_previa_respeta_prefijo_proxy_y_acceso(self):
        host = FastAPI()
        init_app(host, self.settings)
        with TestClient(host, root_path="/portal") as client:
            page = client.get("/portal/interconsultas/")
            url = "/portal/interconsultas/vista-previa"
            self.assertIn(f'data-vista-previa="{url}"', page.text)
            token = re.search(r'name="_csrf_token" value="([^"]+)"', page.text).group(1)
            self.assertEqual(client.post(url, data={"_csrf_token": token}).status_code, 200)

        def denegar():
            raise HTTPException(403, "Acceso denegado")

        protegido = FastAPI()
        init_app(protegido, self.settings, access_dependency=denegar)
        with TestClient(protegido) as client:
            self.assertEqual(client.post("/interconsultas/vista-previa").status_code, 403)
