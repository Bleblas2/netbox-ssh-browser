from fnmatch import fnmatchcase

import httpx

from .cache import Cache, save_cache
from .config import Config
from .model import build_tree
from .netbox import NetBoxClient


def synchronize(config: Config) -> tuple[Cache, int]:
    """Wykonuje cały sync; zapis następuje dopiero po poprawnym pobraniu danych."""
    # Token jest potrzebny wyłącznie w tym ręcznie uruchamianym przepływie.
    config.validate_sync()
    with NetBoxClient(config.netbox_url or "", config.api_token or "", config.verify_ssl) as client:
        client.check_status()
        regions, sites, devices = client.fetch_inventory(config.device_statuses)
    devices = filter_device_roles(devices, config.device_roles)
    devices = filter_ignored_manufacturers(devices, config.ignored_manufacturers)
    devices = filter_ignored_device_types(devices, config.ignored_device_types)
    devices = filter_ignored_name_patterns(devices, config.ignored_name_patterns)
    region_tree = build_tree(regions, sites, devices)
    return save_cache(config.cache_path, region_tree), len(devices)


def filter_device_roles(devices: list[dict], allowed_roles: tuple[str, ...]) -> list[dict]:
    """Pozostawia urządzenia z dozwolonych ról albo wszystkie dla pustej listy."""
    # Pusta allowlista świadomie oznacza brak filtrowania.
    if not allowed_roles:
        return devices
    allowed = {name.casefold() for name in allowed_roles}
    result = []
    for device in devices:
        role = device.get("role") or device.get("device_role") or {}
        role_name = role.get("name") or role.get("display") or ""
        if role_name.casefold() in allowed:
            result.append(device)
    return result


def filter_ignored_manufacturers(
    devices: list[dict], ignored_manufacturers: tuple[str, ...]
) -> list[dict]:
    """Usuwa producentów wskazanych nazwą, slugiem lub wartością display."""
    if not ignored_manufacturers:
        return devices
    # Akceptujemy zarówno czytelną nazwę, jak i stabilny slug z NetBoxa.
    ignored = {value.casefold() for value in ignored_manufacturers}
    result = []
    for device in devices:
        device_type = device.get("device_type") or {}
        manufacturer = device_type.get("manufacturer") or {}
        identifiers = {
            str(manufacturer.get(field, "")).casefold()
            for field in ("name", "slug", "display")
        }
        if not identifiers.intersection(ignored):
            result.append(device)
    return result


def _matches_any(value: object, patterns: tuple[str, ...]) -> bool:
    text = str(value or "").casefold()
    return bool(text) and any(
        fnmatchcase(text, pattern.casefold()) for pattern in patterns
    )


def filter_ignored_device_types(
    devices: list[dict], ignored_patterns: tuple[str, ...]
) -> list[dict]:
    """Removes devices whose model, slug, or display matches a glob pattern."""
    if not ignored_patterns:
        return devices
    result = []
    for device in devices:
        device_type = device.get("device_type") or {}
        values = (device_type.get(field) for field in ("model", "slug", "display"))
        if not any(_matches_any(value, ignored_patterns) for value in values):
            result.append(device)
    return result


def filter_ignored_name_patterns(
    devices: list[dict], ignored_patterns: tuple[str, ...]
) -> list[dict]:
    """Removes devices whose name (or display fallback) matches a glob pattern."""
    if not ignored_patterns:
        return devices
    return [
        device
        for device in devices
        if not _matches_any(
            device.get("name") or device.get("display"), ignored_patterns
        )
    ]


def describe_sync_error(error: Exception) -> str:
    """Zamienia techniczne wyjątki HTTP na komunikaty zrozumiałe w TUI."""
    if isinstance(error, ValueError):
        return f"Configuration error: {error}"
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        endpoint = error.request.url.path
        if status == 401:
            return (
                f"Token rejected on {endpoint} (HTTP 401). Check netbox.api_token "
                "in config.toml or NETBOX_API_TOKEN."
            )
        if status == 403:
            return (
                f"Permission denied on {endpoint} (HTTP 403). The token user needs "
                "view permissions for DCIM regions, sites, and devices."
            )
        return f"NetBox returned HTTP {status} on {endpoint}."
    if isinstance(error, httpx.ConnectError):
        if "CERTIFICATE_VERIFY_FAILED" in str(error):
            return (
                "SSL verification failed. Set verify_ssl = false for a trusted "
                "self-signed environment and ensure NETBOX_VERIFY_SSL is not true."
            )
        return f"Cannot connect to NetBox: {error}"
    if isinstance(error, httpx.TimeoutException):
        return "NetBox did not respond within 30 seconds."
    return f"Sync failed: {error}"
