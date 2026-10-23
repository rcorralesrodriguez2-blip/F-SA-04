"""Consolidado anual con registros sintéticos en SQLite temporal."""
import re
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from fsa04 import create_app, init_app
from fsa04.config import Settings
from fsa04.consolidado import calcular_consolidado
from fsa04.domain import ESPECIALIDADES
from fsa04 import repositories, services


class ConsolidadoTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "consolidado.db"
        self.settings = Settings(database=self.database, secret_key="test-only")
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def insertar(self, solicitud, especialidad="Ortopedia", tipo="Especialidad Quirurgica", respuesta=""):
        return services.guardar_interconsulta({
            "paciente": "Prueba", "identificacion": "test", "medico": "Prueba",
            "especialidad": especialidad, "tipo_especialidad": tipo,
            "fecha_solicitud": solicitud, "fecha_respuesta": respuesta,
            "observaciones": "", "cumplimiento": "SI" if respuesta else "",
        }, self.database)

    def fila(self, reporte, categoria, nombre):
        return next(fila for fila in reporte[categoria] if fila["nombre"] == nombre)

    def test_meses_anio_pendientes_y_solicitudes_entre_anios(self):
        self.insertar("2026-01-01T00:00")
        self.insertar("2026-01-31T23:59", respuesta="2026-02-01T00:01")
        self.insertar("2026-12-31T23:59", "Medicina Interna", "Especialidad Clinica", "2027-01-01T00:01")
        self.insertar("2025-12-31T23:59", respuesta="2026-01-01T00:01")
        self.insertar("2027-01-01T00:00")
        reporte = services.obtener_consolidado(self.database, 2026)
        self.assertEqual(reporte["totales"]["meses"], [2] + [0] * 10 + [1])
        self.assertEqual(reporte["totales"]["total"], 3)
        self.assertEqual(self.fila(reporte, "por_especialidad", "Ortopedia")["total"], 2)
        self.assertEqual(self.fila(reporte, "por_tipo", "Especialidad Clinica")["meses"][11], 1)
        for categoria in ("por_especialidad", "por_tipo"):
            self.assertEqual(sum(fila["total"] for fila in reporte[categoria]), 3)
            for mes in range(12):
                self.assertEqual(sum(fila["meses"][mes] for fila in reporte[categoria]), reporte["totales"]["meses"][mes])
        grupos = repositories.listar_grupos_consolidado(self.database, 2026)
        self.assertEqual(set(grupos[0].keys()), {"mes", "especialidad", "tipo_especialidad", "cantidad"})

    def test_categorias_historicas_normalizadas_y_no_catalogadas(self):
        reporte = calcular_consolidado([
            {"mes": 8, "especialidad": "  Medicina   Interna ", "tipo_especialidad": "ESPECIALIDAD CLÍNICA ", "cantidad": 2},
            {"mes": 8, "especialidad": "medicina interna", "tipo_especialidad": "Especialidad Clinica", "cantidad": 1},
            {"mes": 2, "especialidad": "Anestesiologia", "tipo_especialidad": "Sub-Especialidades", "cantidad": 1},
            {"mes": 3, "especialidad": "Histórica", "tipo_especialidad": "Tipo anterior", "cantidad": 4},
            {"mes": 3, "especialidad": " ", "tipo_especialidad": " ", "cantidad": 1},
        ])
        self.assertEqual(self.fila(reporte, "por_especialidad", "Medicina interna")["total"], 3)
        self.assertEqual(self.fila(reporte, "por_especialidad", "Anestesiología")["total"], 1)
        self.assertEqual(self.fila(reporte, "por_especialidad", "Histórica")["total"], 4)
        self.assertEqual(self.fila(reporte, "por_tipo", "Sin especificar")["total"], 1)
        self.assertEqual(reporte["totales"]["total"], 9)

    def test_vacio_catalogo_y_totales_en_cero(self):
        reporte = services.obtener_consolidado(self.database, 2026)
        self.assertEqual(len(reporte["por_especialidad"]), len(ESPECIALIDADES))
        self.assertEqual(len(reporte["por_tipo"]), 3)
        self.assertEqual(reporte["totales"]["meses"], [0] * 12)
        response = self.client.get("/consolidado?anio=2026")
        self.assertEqual(response.status_code, 200)
        self.assertIn("No hay interconsultas", response.text)
        self.assertEqual(response.text.count("<table "), 2)
        self.assertIn('value="2026"', response.text)
        self.assertIn('aria-current="page">Consolidado', response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_validacion_de_anio_y_valor_por_defecto(self):
        for valor in ("0", "10000", "-1", "2026.5", "abc", "", "2026' OR 1=1--"):
            with self.subTest(valor=valor):
                self.assertEqual(self.client.get("/consolidado", params={"anio": valor}).status_code, 400)
        self.assertEqual(self.client.get("/consolidado").status_code, 200)
        self.assertEqual(self.client.get("/consolidado?anio=1").status_code, 200)
        self.assertEqual(self.client.get("/consolidado?anio=9999").status_code, 200)

    def test_catalogo_ampliado_disponible_en_formulario_y_guardado(self):
        pagina = self.client.get("/")
        for especialidad in ("Cirugía general", "Pediatría", "Urología", "Vascular periférico"):
            self.assertIn(especialidad, pagina.text)
        token = re.search(r'name="_csrf_token" value="([^"]+)"', pagina.text).group(1)
        response = self.client.post("/guardar", data={
            "_csrf_token": token, "paciente": "Prueba", "identificacion": "test",
            "medico": "Prueba", "especialidad": "Cirugía general",
            "tipo_especialidad": "Especialidad Quirurgica", "fecha_solicitud": "2026-03-01T10:00",
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        reporte = services.obtener_consolidado(self.database, 2026)
        self.assertEqual(self.fila(reporte, "por_especialidad", "Cirugía general")["meses"][2], 1)

    def test_historico_desconocido_se_escapa_y_fechas_invalidas_no_se_cuentan(self):
        from fsa04.database import connect
        with connect(self.database) as connection, connection:
            for fecha in ("2026-03-10T10:00:00", "fecha inválida"):
                connection.execute(
                    """INSERT INTO interconsultas (paciente, identificacion, especialidad,
                    tipo_especialidad, medico, fecha_solicitud) VALUES (?, ?, ?, ?, ?, ?)""",
                    ("Prueba", "test", "<script>histórica</script>", "Otro", "Prueba", fecha),
                )
        response = self.client.get("/consolidado?anio=2026")
        self.assertIn("&lt;script&gt;histórica&lt;/script&gt;", response.text)
        self.assertNotIn("<script>histórica</script>", response.text)
        self.assertEqual(services.obtener_consolidado(self.database, 2026)["totales"]["total"], 1)

    def test_montaje_y_autorizacion_incluyen_consolidado(self):
        host = FastAPI()
        init_app(host, self.settings, url_prefix="/hospital/interconsultas")
        with TestClient(host, root_path="/portal") as client:
            response = client.get("/portal/hospital/interconsultas/consolidado?anio=2026")
            self.assertEqual(response.status_code, 200)
            self.assertIn('action="/portal/hospital/interconsultas/consolidado"', response.text)

        def denegar():
            raise HTTPException(403, "Acceso denegado")

        protected = FastAPI()
        init_app(protected, self.settings, access_dependency=denegar)
        with TestClient(protected) as client:
            self.assertEqual(client.get("/interconsultas/consolidado").status_code, 403)
