"""Configuración explícita del módulo; entorno solo para ejecución independiente."""
import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database: str | Path
    secret_key: str
    base_template: str = "interconsultas/shell.html"
    load_bootstrap: bool = True
    show_sidebar: bool = True
    title: str = "Control hospitalario"
    max_content_length: int = 64 * 1024
    cookie_secure: bool = False
    csrf_cookie: str = "fsa04_csrf"
    csrf_max_age: int = 3600

    def __post_init__(self):
        if not self.secret_key:
            raise ValueError("Configure un secreto estable para el módulo.")
        if self.max_content_length <= 0 or self.csrf_max_age <= 0:
            raise ValueError("Los límites de tamaño y tiempo deben ser positivos.")

    @classmethod
    def from_env(cls):
        return cls(
            database=os.environ.get("FSA04_DATABASE") or Path(__file__).resolve().parent.parent / "database.db",
            secret_key=os.environ.get("FSA04_SECRET_KEY") or secrets.token_hex(32),
        )
