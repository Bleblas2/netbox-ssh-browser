from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .inventory import DeviceRecord, Inventory, RegionRecord, SiteRecord
from .model import Node, build_tree


@dataclass
class Cache:
    """Inwentaryzacja niezależna od widoku; ręczne hosty pozostają w manual.json."""

    synced_at: str
    regions: list[RegionRecord]
    sites: list[SiteRecord] = field(default_factory=list)
    devices: list[DeviceRecord] = field(default_factory=list)

    def tree(
        self, layout: str = "auto", unassigned_group: str = "Other sites",
    ) -> list[Node]:
        return build_tree(
            self.regions, self.sites, self.devices,
            layout=layout, unassigned_group=unassigned_group,
        )


def _validate_inventory(data: dict) -> None:
    def text(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def reference(value: Any) -> bool:
        return value is None or type(value) is int

    if not text(data["synced_at"]):
        raise ValueError("Missing cache timestamp")
    for key, relation in (("regions", "parent_id"), ("sites", "region_id")):
        if not isinstance(data[key], list):
            raise ValueError(f"Invalid cache {key}")
        ids = set()
        for item in data[key]:
            if (not isinstance(item, dict) or type(item["id"]) is not int
                    or item["id"] in ids or not text(item["name"])
                    or not reference(item[relation])):
                raise ValueError(f"Invalid cache {key} record")
            ids.add(item["id"])
    # Cykle odrzucamy przed rekurencyjnym budowaniem i przycinaniem drzewa,
    # aby błędne relacje rodziców nie uniemożliwiły uruchomienia aplikacji.
    parents = {item["id"]: item["parent_id"] for item in data["regions"]}
    visited = set()
    for region_id in parents:
        path = set()
        current = region_id
        while current in parents and current not in visited:
            if current in path:
                raise ValueError("Cyclic cache region hierarchy")
            path.add(current)
            current = parents[current]
        visited.update(path)
    if not isinstance(data["devices"], list):
        raise ValueError("Invalid cache devices")
    for item in data["devices"]:
        if (not isinstance(item, dict) or not text(item["name"])
                or not text(item["role"]) or not reference(item["site_id"])
                or (item["identifier"] is not None and not text(item["identifier"]))
                or (item["primary_ip"] is not None and not text(item["primary_ip"]))):
            raise ValueError("Invalid cache device")


def load_cache(path: Path) -> Cache | None:
    """Wczytuje cache v3; starszy zapis drzewa wymaga ponownej synchronizacji."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 3:
            return None
        _validate_inventory(data)
        return Cache(data["synced_at"], data["regions"], data["sites"], data["devices"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_cache(path: Path, inventory: Inventory) -> Cache:
    """Zapisuje atomowo inwentaryzację, niezależnie od wybranego widoku."""
    synced_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    payload: dict[str, Any] = {
        "version": 3,
        "synced_at": synced_at,
        "regions": inventory["regions"],
        "sites": inventory["sites"],
        "devices": inventory["devices"],
    }
    _validate_inventory(payload)
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
    return Cache(synced_at, payload["regions"], payload["sites"], payload["devices"])
