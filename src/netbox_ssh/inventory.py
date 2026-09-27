"""Wspólny format inwentaryzacji używany przez cache i widoki drzewa."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


DEFAULT_ADDRESS_ORDER = ("primary_ip4", "primary_ip6", "oob_ip", "fqdn")


EffectiveLayout = Literal["regions", "sites"]


class RegionRecord(TypedDict):
    id: int
    name: str
    parent_id: int | None


class SiteRecord(TypedDict):
    id: int
    name: str
    region_id: int | None


class DeviceRecord(TypedDict):
    identifier: str | None
    site_id: int | None
    name: str
    role: str
    primary_ip: str | None


class Inventory(TypedDict):
    regions: list[RegionRecord]
    sites: list[SiteRecord]
    devices: list[DeviceRecord]


def resolve_layout(
    layout: str, *, has_regions: bool, has_manual_regions: bool = False,
) -> EffectiveLayout:
    # Ręczne wpisy mogą zawierać hierarchię, nawet gdy cache nie ma regionów.
    # Jawny wybór użytkownika ma pierwszeństwo przed automatycznym dopasowaniem.
    if layout == "auto":
        return "regions" if has_regions or has_manual_regions else "sites"
    if layout in ("regions", "sites"):
        return layout
    raise ValueError("tree.layout must be auto, regions, or sites")


def _object_id(value: Any) -> int | None:
    if isinstance(value, dict):
        value = value.get("id")
    return value if type(value) is int else None


def normalize_inventory(
    regions: list[dict[str, Any]],
    sites: list[dict[str, Any]],
    devices: list[dict[str, Any]],
    address_order: tuple[str, ...] = DEFAULT_ADDRESS_ORDER,
) -> Inventory:
    """Normalizuje odpowiedzi API, zachowując tylko dane lokalizacji i połączeń."""
    # Nie zapisujemy całych odpowiedzi API: dodatkowe pola i kontekst urządzeń
    # nie są potrzebne do przeglądania drzewa ani do nawiązywania połączeń SSH.
    inventory: Inventory = {
        "regions": [
            {"id": item["id"], "name": item["name"],
             "parent_id": _object_id(item.get("parent"))}
            for item in regions
        ],
        "sites": [
            {"id": item["id"],
             "name": item.get("name") or item.get("display") or f"Site {item['id']}",
             "region_id": _object_id(item.get("region"))}
            for item in sites
        ],
        "devices": [],
    }
    for raw in devices:
        device_id = raw.get("id")
        role = raw.get("role") or raw.get("device_role") or {}
        ip = None
        # Wybieramy pierwszy niepusty adres wyłącznie ze wskazanych pól.
        for field in address_order:
            candidate = raw.get("name" if field == "fqdn" else field)
            if isinstance(candidate, dict):
                candidate = candidate.get("address") or candidate.get("display")
            if isinstance(candidate, str) and candidate.strip():
                ip = candidate.strip()
                break
        if ip is None:
            continue
        inventory["devices"].append({
            "identifier": f"netbox:{device_id}" if device_id is not None else None,
            "site_id": _object_id(raw.get("site")),
            "name": raw.get("name") or raw.get("display") or (
                f"Device {device_id}" if device_id is not None else "Unnamed device"
            ),
            "role": role.get("name") or role.get("display") or "Other",
            "primary_ip": ip,
        })
    return inventory
