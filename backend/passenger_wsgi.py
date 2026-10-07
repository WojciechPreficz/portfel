# Tylko na produkcję (cPanel/Passenger); lokalnie używam uvicorn app.main:app.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from a2wsgi import ASGIMiddleware
from app.main import app, initialize

initialize()

application = ASGIMiddleware(app)
