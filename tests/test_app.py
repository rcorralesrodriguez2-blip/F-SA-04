"""Regresion funcional con SQLite temporal; nunca usa database.db del proyecto."""
import re
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fsa04 import create_app
from fsa04.database import connect
from fsa04.config import Settings
from fastapi.testclient import TestClient
from fsa04.domain import ValidationError, calcular_oportunidad, interpretar_fecha
from fsa04.services import calcular_indicadores


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = str(Path(self.tmp.name) / "test.db")
        self.app = create_app(Settings(database=self.db_path, secret_key="test-only"))
        self.client = TestClient(self.app, follow_redirects=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def datos(self, **cambios):
        pagina = self.client.get("/")
        token = re.search(rb'name="_csrf_token" value="([^"]+)"', pagina.content).group(1).decode()
        datos = {
            "_csrf_token": token,
            "paciente": "Paciente de prueba", "identificacion": "123",
            "especialidad": "Ortopedia", "tipo_especialidad": "Especialidad Quirurgica  ",
            "medico": "Medico de prueba", "fecha_solicitud": "2026-10-15T10:00:00",
            "fecha_respuesta": "2026-10-16T10:00:00", "observaciones": "", "cumplimiento": "SI",
        }
        datos.update(cambios)
        return datos

    def contar(self):
        with closing(sqlite3.connect(self.db_path)) as connection:
            return connection.execute("SELECT count(*) FROM interconsultas").fetchone()[0]

    def test_paginas_y_recursos(self):
        for ruta in ("/", "/tabla", "/indicadores", "/static/css/app.css", "/static/js/formulario.js", "/static/js/tabla.js"):
            response = self.client.get(ruta)
            self.assertEqual(response.status_code, 200, ruta)
            response.close()
        self.assertEqual(self.client.get("/ausente").status_code, 404)

    def test_guardar_y_mostrar_con_sql_y_html_seguros(self):
        nombre = "<script>alert(1)</script>'; DROP TABLE interconsultas;--"
        response = self.client.post("/guardar", data=self.datos(paciente=nombre), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"&lt;script&gt;", response.content)
        self.assertNotIn(nombre.encode(), response.content)
        self.assertEqual(self.contar(), 1)
        with closing(sqlite3.connect(self.db_path)) as connection:
            fila = connection.execute("SELECT paciente, tipo_especialidad, oportunidad, cumplimiento FROM interconsultas").fetchone()
        self.assertEqual(fila, (nombre, "Especialidad Quirurgica", "24:00:00", "SI"))
        self.assertEqual(self.client.get("/indicadores").status_code, 200)

    def test_pendiente(self):
        self.assertEqual(self.client.post("/guardar", data=self.datos(fecha_respuesta="")).status_code, 303)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT oportunidad, cumplimiento FROM interconsultas").fetchone(), (None, None))

    def test_validaciones_no_insertan_y_conservan_formulario(self):
        casos = (
            {"paciente": ""}, {"especialidad": "Desconocida"}, {"tipo_especialidad": "Otra"},
            {"fecha_solicitud": "invalida"}, {"fecha_respuesta": "2026-10-14T10:00"},
            {"fecha_respuesta": "2026-10-16T10:00+01:00"},
            {"observaciones": "a" * 2001},
        )
        for cambios in casos:
            with self.subTest(cambios=cambios):
                response = self.client.post("/guardar", data=self.datos(**cambios))
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"123", response.content)
        self.assertEqual(self.contar(), 0)

    def test_csrf_rechaza_token_ausente_incorrecto_y_otra_sesion(self):
        datos = self.datos()
        for token in ("", "incorrecto", "inv?lido"):
            self.assertEqual(self.client.post("/guardar", data={**datos, "_csrf_token": token}).status_code, 400)
        otro = TestClient(self.app, follow_redirects=False)
        self.assertEqual(otro.post("/guardar", data=datos).status_code, 400)
        self.assertEqual(self.contar(), 0)

    def test_limite_y_cabeceras(self):
        response = self.client.get("/")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(self.client.post("/guardar", data={"campo": "x" * 70000}).status_code, 413)

    def test_error_sql_controlado_y_sin_detalles(self):
        with patch("fsa04.repositories.listar_interconsultas", side_effect=sqlite3.OperationalError("detalle privado")):
            response = self.client.get("/tabla")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"detalle privado", response.content)

    def test_duracion_corrupta_muestra_error_controlado(self):
        with patch("fsa04.repositories.listar_datos_indicadores", return_value=(fila for fila in [
            {"tipo_especialidad": "ESPECIALIDAD CLINICA", "oportunidad": "mal"},
        ])):
            response = self.client.get("/indicadores")
        self.assertEqual(response.status_code, 500)

    def test_conexion_se_cierra_al_salir_del_contexto(self):
        with connect(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")

    def test_reiniciar_no_borra_registros(self):
        self.client.post("/guardar", data=self.datos())
        otra = create_app(Settings(database=self.db_path, secret_key="otro"))
        with TestClient(otra) as client:
            self.assertEqual(client.get("/tabla").status_code, 200)
        self.assertEqual(self.contar(), 1)

    def poblar_historial(self, cantidad=123):
        with connect(self.db_path) as connection, connection:
            connection.executemany(
                """INSERT INTO interconsultas
                (paciente, identificacion, especialidad, tipo_especialidad, medico, fecha_solicitud)
                VALUES (?, ?, 'Ortopedia', 'Especialidad Quirurgica', 'Sintético', '2026-10-21T10:00:00')""",
                [(f"Sintético {i}", f"S-{i}") for i in range(cantidad)],
            )

    def test_historial_paginado_sin_perdidas_ni_duplicados(self):
        self.poblar_historial()
        url, ids, tamanos = "/tabla", [], []
        while url:
            pagina = self.client.get(url)
            self.assertEqual(pagina.status_code, 200)
            encontrados = re.findall(r"/registros/(\d+)/editar", pagina.text)
            ids.extend(map(int, encontrados))
            tamanos.append(len(encontrados))
            siguiente = re.search(r'href="([^"]+)">Siguientes 50', pagina.text)
            url = siguiente.group(1).replace("&amp;", "&") if siguiente else None
        self.assertEqual(tamanos, [50, 50, 23])
        self.assertEqual(ids, list(range(123, 0, -1)))

    def test_busqueda_global_unicode_y_caracteres_literales(self):
        self.poblar_historial()
        pagina = self.client.get("/tabla", params={"q": "SINTÉTICO 0"})
        self.assertIn("/registros/1/editar", pagina.text)
        self.assertEqual(len(re.findall(r"/registros/(\d+)/editar", pagina.text)), 1)
        for consulta in ("%", "_", "' OR 1=1 --"):
            pagina = self.client.get("/tabla", params={"q": consulta})
            self.assertNotIn("/editar", pagina.text)
        self.assertEqual(self.contar(), 123)

    def test_historial_rechaza_parametros_invalidos(self):
        for cursor in ("0", "-1", "abc", "9223372036854775808", "9" * 5000):
            self.assertEqual(self.client.get("/tabla", params={"antes": cursor}).status_code, 400)
        self.assertEqual(self.client.get("/tabla", params={"q": "a" * 251}).status_code, 400)

    def test_paginacion_conserva_busqueda_y_prefijo_proxy(self):
        self.poblar_historial()
        with TestClient(self.app, root_path="/portal") as client:
            pagina = client.get("/portal/tabla", params={"q": "SINTÉTICO"})
            enlace = re.search(r'href="([^"]+)">Siguientes 50', pagina.text).group(1)
            self.assertTrue(enlace.startswith("/portal/tabla?q="))
            self.assertIn("SINT%C3%89TICO", enlace)
            siguiente = client.get(enlace.replace("&amp;", "&"))
            self.assertEqual(siguiente.status_code, 200)
            self.assertNotIn("/registros/123/editar", siguiente.text)
            self.assertIn("/registros/73/editar", siguiente.text)

    def test_guardado_redirige_a_historial_acotado(self):
        self.poblar_historial()
        pagina = self.client.post("/guardar", data=self.datos(), follow_redirects=True)
        self.assertEqual(pagina.status_code, 200)
        self.assertIn("/registros/124/editar", pagina.text)
        self.assertEqual(len(re.findall(r"/registros/(\d+)/editar", pagina.text)), 50)
        self.assertEqual(self.contar(), 124)


class DomainTests(unittest.TestCase):
    def test_umbral_y_duracion_larga(self):
        inicio = interpretar_fecha("2026-10-15T10:00:00")
        for fin, esperado in (
            ("2026-10-16T10:00:00", "24:00:00"),
            ("2026-10-16T10:00:01", "24:00:01"),
            ("2026-10-20T10:00:00", "120:00:00"),
        ):
            self.assertEqual(calcular_oportunidad(inicio, interpretar_fecha(fin)), esperado)
        with self.assertRaises(ValidationError):
            calcular_oportunidad(inicio, interpretar_fecha("2026-10-15T09:59:59.999999"))

    def test_indicadores_categorias_historicas_y_pendientes(self):
        filas = [
            {"tipo_especialidad": "ESPECIALIDAD CLINICA", "oportunidad": "24:00:00", "cumplimiento": "SI"},
            {"tipo_especialidad": "Especialidad Clinica ", "oportunidad": None, "cumplimiento": None},
            {"tipo_especialidad": "Especialidad Quirurgica  ", "oportunidad": "24:00:01", "cumplimiento": "NO"},
            {"tipo_especialidad": "Sub-Especialidades", "oportunidad": "00:00:00", "cumplimiento": "SI"},
        ]
        resultado = calcular_indicadores(filas)
        self.assertEqual(resultado["incumplen"], 1)
        self.assertEqual(resultado["porcentaje_incumplimiento"], 25.0)
        global_, quirurgica, clinica, sub = resultado["metricas"]
        self.assertEqual(global_["total_ordenes"], 4)
        self.assertEqual(clinica["promedio"], "12:00:00")
        self.assertEqual(clinica["ordenes_respondidas"], 1)
        self.assertEqual(quirurgica["total_ordenes"], 1)
        self.assertEqual(sub["promedio"], "00:00:00")

    def test_indicadores_vacios(self):
        resultado = calcular_indicadores([])
        self.assertEqual(resultado["porcentaje_incumplimiento"], 0)
        self.assertTrue(all(m["promedio"] is None for m in resultado["metricas"]))


if __name__ == "__main__":
    unittest.main()
