import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ustawienia w kodzie, bo panel cPanel nie przekazuje hasha wiernie ($ w wartości).
os.environ["PORTFEL_PASSWORD_HASH"] = "$argon2id$v=19$m=65536,t=3,p=4$kKF2DAdrAEKdSSHPtT+EQw$ZoAWtfpKLt0Rgycrwlgoxh/6U2dbnZsfYJsgC8OT7OE"
os.environ["PORTFEL_DATABASE_PATH"] = "/home/vh14224/portfel_app/data/portfel.db"

_lock = threading.Lock()
_app = None


def application(environ, start_response):
    global _app
    if _app is None:
        with _lock:
            if _app is None:
                from a2wsgi import ASGIMiddleware
                from app.main import app, initialize

                initialize()
                _app = ASGIMiddleware(app)
    return _app(environ, start_response)