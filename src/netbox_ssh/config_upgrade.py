"""Uzupełnianie nowych ustawień bez nadpisywania konfiguracji użytkownika."""

from __future__ import annotations

import os
import tempfile
import tomllib
import warnings
from pathlib import Path

import tomlkit
from tomlkit.items import InlineTable

from .inventory import DEFAULT_ADDRESS_ORDER


_DEFAULTS = {
    "sync": {
        "address_order": (
            list(DEFAULT_ADDRESS_ORDER),
            "First available source wins; fqdn uses device.name. Missing addresses are omitted. Press S after changes.",
        ),
    },
    "tree": {
        "layout": ("auto", "auto: regions when available, otherwise sites; or choose regions / sites."),
        "unassigned_group": ("Other sites", "Group for sites without an available region in the regions layout."),
    },
}


def upgrade_config_file(path: Path) -> None:
    """Dopisuje brakujące opcje atomowo; błąd zapisu nie blokuje odczytu ustawień."""
    temporary_name = None
    try:
        # Podmieniamy cel dowiązania, a nie samo dowiązanie do konfiguracji.
        target = path.resolve()
        try:
            original = target.read_bytes()
        except FileNotFoundError:
            return
        content = original.decode("utf-8")
        data = tomllib.loads(content)
        missing = {
            section: {key: value for key, value in options.items() if key not in data.get(section, {})}
            for section, options in _DEFAULTS.items()
            if isinstance(data.get(section, {}), dict)
        }
        if not any(missing.values()):
            return
        if not os.access(target, os.W_OK):
            raise PermissionError("Configuration is read-only")
        document = tomlkit.parse(content)
        for section, options in missing.items():
            if not options:
                continue
            if section not in document:
                document[section] = tomlkit.table()
            for key, (value, description) in options.items():
                setting = tomlkit.item(value)
                # Tabele inline nie dopuszczają komentarzy wewnątrz wartości.
                if not isinstance(document[section], InlineTable):
                    setting.comment(description)
                    if section == "sync" and key == "address_order":
                        setting.trivia.comment_ws = "\n"
                document[section][key] = setting
                data.setdefault(section, {})[key] = value
        updated = tomlkit.dumps(document)
        # Niezależny parser potwierdza, że zmieniły się wyłącznie brakujące opcje.
        if tomllib.loads(updated) != data:
            raise ValueError("Unexpected configuration changes")
        fd, temporary_name = tempfile.mkstemp(prefix=".config-", suffix=".toml", dir=target.parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(updated.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        # Nie zastępujemy zmian zapisanych w międzyczasie przez edytor.
        if target.read_bytes() != original:
            raise OSError("Configuration changed during upgrade")
        os.replace(temporary_name, target)
    except (OSError, ValueError):
        # Nie pokazujemy treści wyjątku parsera, która mogłaby zawierać sekret.
        warnings.warn(
            f"Could not add missing defaults to {path}; existing settings remain in use.",
            UserWarning,
            stacklevel=2,
        )
    finally:
        if temporary_name is not None and os.path.exists(temporary_name):
            os.unlink(temporary_name)
