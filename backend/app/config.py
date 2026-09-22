from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
DATABASE_PATH = DATA_DIR / "portfel.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"
API_HOST = "127.0.0.1"
API_PORT = 8000
