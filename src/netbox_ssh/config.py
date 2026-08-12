from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_cache_path, user_data_path

@dataclass(frozen=True)
class Config:
    """Efektywna konfiguracja po połączeniu pliku TOML i zmiennych powłoki."""

    netbox_url: str | None
    api_token: str | None
    verify_ssl: bool
    cache_path: Path
    manual_path: Path
    config_path: Path
    device_roles: tuple[str, ...]
    device_statuses: tuple[str, ...]
    ignored_manufacturers: tuple[str, ...]
    ignored_device_types: tuple[str, ...] = ()
    ignored_name_patterns: tuple[str, ...] = ()
    jump_host: str | None = None
    jump_state_path: Path | None = None

    @classmethod
    def from_env(cls) -> "Config":
        # platformdirs dobiera natywny katalog cache dla macOS, Linuxa i Windows.
        cache_home = user_cache_path("netbox-ssh-browser", appauthor=False)
        # Ręczne wpisy są danymi użytkownika, a nie cache i nie mogą znikać przy czyszczeniu cache.
        data_home = user_data_path("netbox-ssh-browser", appauthor=False)
        config_home = Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        )
        user_config_path = config_home / "netbox-ssh-browser" / "config.toml"
        local_config_path = Path.cwd() / "config.toml"
        configured_path = os.environ.get("NETBOX_SSH_CONFIG")
        # Jawnie wskazany plik ma pierwszeństwo, następnie konfiguracja użytkownika,
        # a na końcu config.toml z bieżącego katalogu projektu.
        if configured_path:
            config_path = Path(configured_path).expanduser()
        elif user_config_path.is_file():
            config_path = user_config_path
        elif local_config_path.is_file():
            config_path = local_config_path
        else:
            config_path = user_config_path
        file_config = _read_config(config_path)
        netbox = file_config.get("netbox", {})
        sync = file_config.get("sync", {})
        ssh = file_config.get("ssh", {})
        jump_host = _clean_ssh_value(ssh.get("jump_host"), "ssh.jump_host")
        return cls(
            # Zmienne powłoki celowo nadpisują ustawienia zapisane w TOML.
            netbox_url=_clean_url(os.environ.get("NETBOX_URL") or netbox.get("url")),
            # Token może być zapisany w prywatnym config.toml. Zmienna środowiskowa
            # pozostaje opcjonalnym nadpisaniem, przydatnym np. w automatyzacji.
            api_token=os.environ.get("NETBOX_API_TOKEN") or netbox.get("api_token"),
            verify_ssl=_as_bool(
                os.environ.get("NETBOX_VERIFY_SSL", str(netbox.get("verify_ssl", True)))
            ),
            cache_path=cache_home / "devices.json",
            manual_path=data_home / "manual.json",
            jump_state_path=data_home / "jump-host-devices.json",
            config_path=config_path,
            device_roles=tuple(str(role) for role in sync.get("device_roles", [])),
            device_statuses=tuple(
                str(status) for status in sync.get("device_statuses", [])
            ),
            ignored_manufacturers=tuple(
                str(manufacturer)
                for manufacturer in sync.get("ignored_manufacturers", [])
            ),
            ignored_device_types=tuple(
                str(value) for value in sync.get("ignored_device_types", [])
            ),
            ignored_name_patterns=tuple(
                str(value) for value in sync.get("ignored_name_patterns", [])
            ),
            jump_host=jump_host,
        )

    def validate_sync(self) -> None:
        """Sprawdza sekrety wymagane dopiero podczas ręcznej synchronizacji."""
        missing = []
        if not self.netbox_url:
            missing.append("NETBOX_URL")
        if not self.api_token:
            missing.append("NetBox API token (netbox.api_token or NETBOX_API_TOKEN)")
        if missing:
            raise ValueError("Missing environment variables: " + ", ".join(missing))


def _clean_url(value: str | None) -> str | None:
    if not value:
        return None
    value = value.rstrip("/")
    # Klient sam dodaje /api/, więc akceptujemy URL podany również z tym sufiksem.
    if value.endswith("/api"):
        value = value[:-4]
    return value


def _as_bool(value: str) -> bool:
    return value.lower() not in {"0", "false", "no", "off"}


def _clean_ssh_value(value: Any, setting: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    result = str(value).strip()
    if result.startswith("-") or any(character.isspace() for character in result):
        raise ValueError(
            f"{setting} must be a hostname, IP, or SSH alias without whitespace"
        )
    return result


def _read_config(path: Path) -> dict[str, Any]:
    """Czyta opcjonalny TOML; brak pliku jest prawidłową konfiguracją domyślną."""
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error
    return data
