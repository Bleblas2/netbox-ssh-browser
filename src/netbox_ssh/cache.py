from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .model import Node


@dataclass
class Cache:
    """Migawka inwentaryzacji używana bez kontaktowania się z NetBoxem."""

    synced_at: str
    regions: list[Node]


def load_cache(path: Path) -> Cache | None:
    """Wczytuje cache v2 lub zwraca None dla braku/nieobsługiwanego pliku."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 2:
            return None
        return Cache(
            synced_at=data["synced_at"],
            regions=[Node.from_dict(item) for item in data["regions"]],
        )
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_cache(path: Path, regions: list[Node]) -> Cache:
    """Zapisuje kompletną migawkę atomowo i z prywatnymi uprawnieniami."""
    synced_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    payload: dict[str, Any] = {
        "version": 2,
        "synced_at": synced_at,
        "regions": [region.to_dict() for region in regions],
    }
    # Cache zawiera inwentaryzację sieci, dlatego ograniczamy dostęp do właściciela.
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(prefix="devices-", suffix=".json", dir=path.parent)
    try:
        # Najpierw zapisujemy kompletny plik tymczasowy. Dopiero os.replace podmienia
        # stary cache, więc przerwany sync nie pozostawi uszkodzonego JSON-a.
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return Cache(synced_at=synced_at, regions=regions)
