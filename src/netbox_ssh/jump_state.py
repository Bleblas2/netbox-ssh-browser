from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def load_jump_devices(path: Path) -> set[str]:
    """Loads stable device identifiers that should use the configured jump host."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("devices"), list):
            raise ValueError("Unsupported jump-host state format; expected version 1")
        if not all(isinstance(value, str) and value for value in data["devices"]):
            raise ValueError("Jump-host device identifiers must be non-empty strings")
        return set(data["devices"])
    except FileNotFoundError:
        return set()
    except (OSError, json.JSONDecodeError, AttributeError, TypeError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error


def save_jump_devices(path: Path, identifiers: set[str]) -> None:
    """Atomically persists jump-host choices as private user data."""
    payload = {"version": 1, "devices": sorted(identifiers)}
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(
        prefix="jump-host-", suffix=".json", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
