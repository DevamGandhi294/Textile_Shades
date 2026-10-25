"""Run the database routes on their own (for testing):  uvicorn magic_db.standalone:app --port 8001"""
from fastapi import FastAPI

from . import setup

app = FastAPI(title="Magic Outline database API")
setup(app)
