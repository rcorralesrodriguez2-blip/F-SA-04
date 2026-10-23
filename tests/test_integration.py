"""Integración ASGI, acceso delegado y separación respecto al portal."""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader
from starlette.middleware.sessions import SessionMiddleware

from fsa04 import create_module, init_app
from fsa04.config import Settings
from fsa04.database import init_db


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "module.db"
        self.settings = Settings(database=self.database, secret_key="test-only")
        self.host = FastAPI()
        self.host.add_middleware(SessionMiddleware, secret_key="host-secret")

        @self.host.post("/host")
        def host(request: Request):
            request.session["host"] = "preserved"
            return {"host": True}

        self.module = init_app(self.host, self.settings, url_prefix="/hospital/interconsultas")
        self.client = TestClient(self.host, follow_redirects=False)
        self.addCleanup(self.client.close)
        self.prefix = "/hospital/interconsultas"

    def test_registro_no_crea_base_y_esquema_idempotente(self):
        self.assertFalse(self.database.exists())
        init_db(self.database)
        init_db(self.database)
        self.assertTrue(self.database.exists())

    def test_host_conserva_sesion_y_sus_respuestas(self):
        response = self.client.post("/host")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Content-Security-Policy", response.headers)
        self.assertEqual(self.client.get("/ausente").json(), {"detail": "Not Found"})
        cookie = self.client.cookies.get("session")
        page = self.client.get(self.prefix + "/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.client.cookies.get("session"), cookie)
        self.assertIn("fsa04_csrf", self.client.cookies)

    def test_prefijo_recursos_guardado_y_redireccion(self):
        init_db(self.database)
        page = self.client.get(self.prefix + "/")
        token = re.search(r'name="_csrf_token" value="([^"]+)"', page.text).group(1)
        self.assertIn(self.prefix + "/guardar", page.text)
        for resource in ("css/app.css", "js/formulario.js", "js/tabla.js", "vendor/bootstrap.min.css"):
            self.assertEqual(self.client.get(self.prefix + "/static/" + resource).status_code, 200)
        response = self.client.post(self.prefix + "/guardar", data={
            "_csrf_token": token, "paciente": "Prueba", "identificacion": "test",
            "especialidad": "Ortopedia", "tipo_especialidad": "Especialidad Quirurgica",
            "medico": "Prueba", "fecha_solicitud": "2026-10-16T08:00",
        })
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], self.prefix + "/tabla?guardado=1")
        self.assertEqual(self.client.get(response.headers["location"]).status_code, 200)
        self.assertEqual(self.client.get(self.prefix + "/indicadores").status_code, 200)
        self.assertEqual(self.client.post(self.prefix + "/guardar").status_code, 400)
        self.assertIn(self.prefix + "/", self.client.get(self.prefix + "/ausente").text)

    def test_plantilla_padre_y_recursos_del_host(self):
        loader = ChoiceLoader([
            DictLoader({"host.html": "<head>{% block fsa04_styles %}{% endblock %}</head>PORTAL{% block fsa04_content %}{% endblock %}{% block fsa04_scripts %}{% endblock %}"}),
            FileSystemLoader(str(Path(__file__).resolve().parents[1] / "fsa04/templates")),
        ])
        from jinja2 import Environment, select_autoescape
        templates = Jinja2Templates(env=Environment(loader=loader, autoescape=select_autoescape()))
        module = create_module(Settings(database=self.database, secret_key="test", base_template="host.html", show_sidebar=False, load_bootstrap=False), templates=templates)
        with TestClient(module) as client:
            page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("PORTAL", page.text)
        self.assertIn("css/app.css", page.text)
        self.assertIn("js/formulario.js", page.text)
        self.assertNotIn("vendor/bootstrap", page.text)
        self.assertNotIn('<aside class="sidebar">', page.text)

    def test_acceso_depende_de_sesion_del_host(self):
        def require_host(request: Request):
            if not request.session.get("host"):
                raise HTTPException(403, "Acceso denegado")

        host = FastAPI()
        host.add_middleware(SessionMiddleware, secret_key="host-secret")

        @host.post("/login")
        def login(request: Request):
            request.session["host"] = True
            return {"ok": True}

        init_app(host, self.settings, access_dependency=require_host)
        with TestClient(host) as client:
            self.assertEqual(client.get("/interconsultas/").status_code, 403)
            self.assertEqual(client.post("/login").status_code, 200)
            self.assertEqual(client.get("/interconsultas/").status_code, 200)

    def test_csrf_firmado_expirado_y_otra_cookie(self):
        from itsdangerous import TimestampSigner
        self.client.get(self.prefix + "/")
        token = self.client.cookies.get("fsa04_csrf")
        self.assertEqual(self.client.post(self.prefix + "/guardar", data={"_csrf_token": "inventado"}).status_code, 400)
        with patch.object(TimestampSigner, "get_timestamp", return_value=9999999999):
            self.assertEqual(self.client.post(self.prefix + "/guardar", data={"_csrf_token": token}).status_code, 400)
        another = TestClient(self.host)
        self.addCleanup(another.close)
        self.assertEqual(another.post(self.prefix + "/guardar", data={"_csrf_token": token}).status_code, 400)

    def test_limite_stream_sin_content_length(self):
        def body():
            yield b"a="
            yield b"x" * 70000

        response = self.client.post(self.prefix + "/guardar", content=body(), headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(response.status_code, 413)

    def test_prefijo_proxy(self):
        with TestClient(self.host, root_path="/portal") as client:
            response = client.get("/portal" + self.prefix + "/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("/portal" + self.prefix + "/guardar", response.text)

    def test_error_inesperado_controlado(self):
        with TestClient(self.host, raise_server_exceptions=False) as client:
            with patch("fsa04.repositories.listar_interconsultas", side_effect=RuntimeError("detalle privado")):
                response = client.get(self.prefix + "/tabla")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("detalle privado", response.text)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_enlaces_del_portal_en_plantilla_compartida(self):
        from jinja2 import Environment, select_autoescape
        loader = ChoiceLoader([
            DictLoader({"host.html": '<a href="{{ url_for("host") }}">PORTAL</a>{% block fsa04_styles %}{% endblock %}{% block fsa04_content %}{% endblock %}{% block fsa04_scripts %}{% endblock %}'}),
            FileSystemLoader(str(Path(__file__).resolve().parents[1] / "fsa04/templates")),
        ])
        self.module.state.templates = Jinja2Templates(env=Environment(loader=loader, autoescape=select_autoescape()))
        self.module.state.settings = Settings(database=self.database, secret_key="test-only", base_template="host.html")
        response = self.client.get(self.prefix + "/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="http://testserver/host"', response.text)

    def test_configuracion_y_duplicados(self):
        with self.assertRaises(RuntimeError):
            init_app(self.host, self.settings)
        with self.assertRaises(ValueError):
            Settings(database=self.database, secret_key="")
        with self.assertRaises(ValueError):
            init_app(FastAPI(), self.settings, url_prefix="/")
