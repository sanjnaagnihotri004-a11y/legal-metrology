
from pathlib import Path

from app.config import settings

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf"}


def root() -> Path:
    folder = Path(settings.storage_dir)
    return folder if folder.is_absolute() else BACKEND_DIR / folder


def save(kind: str, name: str, data: bytes) -> str:
    """Writes a file under storage/<kind>/ and returns the relative path kept in the database."""
    folder = root() / kind
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    return f"{kind}/{name}"


def read(relative_path: str) -> bytes:
    return (root() / relative_path).read_bytes()


def content_type(relative_path: str) -> str:
    return CONTENT_TYPES.get(Path(relative_path).suffix.lower(), "application/octet-stream")