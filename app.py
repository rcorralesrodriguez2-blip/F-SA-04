"""Entrada ASGI: python app.py o uvicorn app:app."""
import uvicorn

from fsa04 import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)
