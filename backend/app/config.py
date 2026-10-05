import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
_configured_database_path = Path(
    os.environ.get("PORTFEL_DB_PATH", str(ROOT_DIR / "data" / "portfel.db"))
)
DATABASE_PATH = (
    _configured_database_path
    if _configured_database_path.is_absolute()
    else ROOT_DIR / _configured_database_path
).resolve()
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"
API_HOST = "127.0.0.1"
API_PORT = 8000
