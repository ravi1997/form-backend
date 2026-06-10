from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config.settings import settings


@dataclass
class LocalStorageBackend:
    root: Optional[Path] = None

    @property
    def base_root(self) -> Path:
        return self.root or Path(settings.EXPORT_STORAGE_ROOT)

    def resolve(self, *parts: str) -> Path:
        path = self.base_root.joinpath(*[str(part) for part in parts if part is not None])
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def exists(self, path: str | Path) -> bool:
        return Path(path).exists()

    def delete(self, path: str | Path) -> bool:
        target = Path(path)
        if target.exists():
            target.unlink()
            return True
        return False


class S3StorageBackend:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("S3 storage backend is not configured in this repository")


def get_export_storage_backend() -> LocalStorageBackend:
    backend = (settings.EXPORT_STORAGE_BACKEND or "local").lower()
    if backend != "local":
        raise NotImplementedError(f"Unsupported export storage backend: {backend}")
    return LocalStorageBackend()


export_storage_backend = get_export_storage_backend()
