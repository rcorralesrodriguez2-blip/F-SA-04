"""Inicialización explícita: python -m fsa04 init-db --database RUTA."""
import argparse

from .database import init_db


def main():
    parser = argparse.ArgumentParser(description="Administración de F-SA-04")
    parser.add_argument("command", choices=["init-db"])
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    init_db(args.database)
    print("Tablas de F-SA-04 inicializadas.")


if __name__ == "__main__":
    main()
