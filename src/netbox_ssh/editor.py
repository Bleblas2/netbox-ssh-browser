from __future__ import annotations

import os
import platform
import shlex
from pathlib import Path

from .manual import save_manual_devices


DEFAULT_CONFIG = """[netbox]
# Paste only the token value, without the Bearer or Token prefix.
api_token = ""
verify_ssl = true

[sync]
device_statuses = ["active"]
ignored_manufacturers = []
device_roles = []
"""


def editor_command() -> list[str]:
    """Zwraca standardowy edytor użytkownika odpowiedni dla platformy."""
    fallback = "notepad" if platform.system() == "Windows" else "nano"
    configured = os.environ.get("VISUAL") or os.environ.get("EDITOR") or fallback
    command = shlex.split(configured)
    if not command:
        return [fallback]
    return command


def ensure_config_file(path: Path) -> None:
    """Tworzy bezpieczny minimalny config, jeśli użytkownik jeszcze go nie ma."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    os.chmod(path, 0o600)


def ensure_manual_file(path: Path) -> None:
    """Tworzy pusty manual.json v1 przed pierwszym otwarciem edytora."""
    if not path.exists():
        save_manual_devices(path, [])
