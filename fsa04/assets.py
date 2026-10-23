"""Caché de recursos públicos con versión de contenido por despliegue."""
from hashlib import sha256
from pathlib import Path

from fastapi.staticfiles import StaticFiles
from starlette.datastructures import QueryParams


class VersionedStaticFiles(StaticFiles):
    def __init__(self, directory):
        super().__init__(directory=str(directory))
        root = Path(directory)
        self.versions = {
            file.relative_to(root).as_posix(): sha256(file.read_bytes()).hexdigest()[:16]
            for file in root.rglob("*")
            if file.is_file() and file.suffix in {".css", ".js"}
        }

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        # Solo una URL con la versión vigente puede reutilizarse sin consultar.
        version = self.versions.get(path.replace("\\", "/"))
        if response.status_code in {200, 304}:
            current = version and QueryParams(scope.get("query_string", b"")).get("v") == version
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable" if current else "no-cache"
            )
        return response
