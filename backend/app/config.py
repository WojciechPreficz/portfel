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


def _environment_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be set to true or false")


PORTFEL_ENV = os.environ.get("PORTFEL_ENV", "development").strip().lower()
PORTFEL_PASSWORD_HASH = os.environ.get("PORTFEL_PASSWORD_HASH", "").strip() or None
PORTFEL_SECRET_KEY = os.environ.get("PORTFEL_SECRET_KEY", "").strip() or None
PORTFEL_SESSION_HOURS = int(os.environ.get("PORTFEL_SESSION_HOURS", "12"))
if PORTFEL_SESSION_HOURS <= 0:
    raise ValueError("PORTFEL_SESSION_HOURS must be a positive integer")
PORTFEL_COOKIE_SECURE = _environment_bool(
    "PORTFEL_COOKIE_SECURE",
    PORTFEL_ENV in {"prod", "production"},
)
PORTFEL_AUTH_DISABLED = _environment_bool("PORTFEL_AUTH_DISABLED", False)
if PORTFEL_AUTH_DISABLED and PORTFEL_ENV in {"prod", "production"}:
    raise ValueError("PORTFEL_AUTH_DISABLED cannot be enabled in production.")
