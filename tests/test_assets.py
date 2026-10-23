"""Caché pública de estáticos sin almacenar páginas clínicas."""
import re
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fsa04 import create_app, init_app
from fsa04.assets import VersionedStaticFiles
from fsa04.config import Settings


class AssetTests(unittest.TestCase):
    def test_cache_versionada_y_revalidacion(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Settings(database=Path(directory) / "test.db", secret_key="test"))
            with TestClient(app) as client:
                page = client.get("/")
                urls = re.findall(r'(?:href|src)="([^"]*/static/[^"]+)"', page.text)
                self.assertEqual(len(urls), 3)
                self.assertNotIn("bootstrap.bundle.min.js", page.text)
                for url in urls:
                    self.assertRegex(url, r"\?v=[a-f0-9]{16}$")
                    response = client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["cache-control"], "public, max-age=31536000, immutable")
                    self.assertIn("Content-Security-Policy", response.headers)
                    self.assertNotIn("set-cookie", response.headers)
                    bare = url.split("?")[0]
                    for unversioned in (bare, bare + "?v=anterior"):
                        response = client.get(unversioned)
                        self.assertEqual(response.headers["cache-control"], "no-cache")
                        cached = client.get(unversioned, headers={"If-None-Match": response.headers["etag"]})
                        self.assertEqual(cached.status_code, 304)
                        self.assertEqual(cached.content, b"")
                        self.assertEqual(cached.headers["cache-control"], "no-cache")
                for path in ("/", "/tabla", "/indicadores", "/consolidado", "/ausente", "/static/ausente.css"):
                    self.assertEqual(client.get(path).headers["cache-control"], "no-store", path)
                self.assertEqual(client.post("/guardar").headers["cache-control"], "no-store")

    def test_version_cambia_solo_si_cambia_contenido(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "app.css"
            file.write_text("body {}", encoding="utf-8")
            first = VersionedStaticFiles(directory).versions["app.css"]
            self.assertEqual(first, VersionedStaticFiles(directory).versions["app.css"])
            file.write_text("body { color: red; }", encoding="utf-8")
            self.assertNotEqual(first, VersionedStaticFiles(directory).versions["app.css"])

    def test_cache_con_montaje_y_proxy(self):
        with tempfile.TemporaryDirectory() as directory:
            host = FastAPI()
            init_app(host, Settings(database=Path(directory) / "test.db", secret_key="test"))
            with TestClient(host, root_path="/portal") as client:
                page = client.get("/portal/interconsultas/")
                url = re.search(r'href="([^"]+/static/css/app.css\?v=[^"]+)"', page.text).group(1)
                self.assertTrue(url.startswith("/portal/interconsultas/static/"))
                response = client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("immutable", response.headers["cache-control"])
