from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import Device, Node


@dataclass(frozen=True)
class ManualDevice:
    """Trwały wpis urządzenia utrzymywany niezależnie od NetBoxa."""

    region: str
    country: str
    city: str
    branch: str
    role: str
    name: str
    target: str

    @property
    def location_path(self) -> tuple[str, ...]:
        # Miasto może być jednocześnie oddziałem; nie tworzymy wtedy duplikatu poziomu.
        values = (self.region, self.country, self.city, self.branch)
        path: list[str] = []
        for value in values:
            if value and (not path or value != path[-1]):
                path.append(value)
        return tuple(path)

    def display_path(self, layout: str, unassigned_group: str) -> tuple[str, ...]:
        # Spłaszczamy tylko widok. Pełna lokalizacja pozostaje w manual.json
        # i nadal służy do wyznaczania identyfikatora oraz ustawień jump hosta.
        if layout == "sites":
            return (self.branch,)
        if not self.region:
            return (unassigned_group, *self.location_path)
        return self.location_path

    def as_device(self) -> Device:
        """Zachowuje identyfikator ręcznego hosta niezależnie od wybranego widoku."""
        return Device(
            self.name, self.role, self.target, source="manual",
            identifier="manual:" + "/".join((*self.location_path, self.name)).casefold(),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "region": self.region,
            "country": self.country,
            "city": self.city,
            "branch": self.branch,
            "role": self.role,
            "name": self.name,
            "target": self.target,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManualDevice":
        if not isinstance(data, dict):
            raise ValueError("Manual device must be an object")
        # Starsze kompletne wpisy i nowe wpisy z samym Site mają format v1.
        # Brakujące poziomy nie wymagają tworzenia fikcyjnych regionów lub krajów.
        optional = {"region", "country", "city"}
        values = {}
        for field in cls.__dataclass_fields__:
            value = data.get(field, "")
            if value is None and field in optional:
                value = ""
            if not isinstance(value, str):
                raise ValueError(f"Manual device field '{field}' must be text")
            values[field] = value.strip()
            if field not in optional and not values[field]:
                raise ValueError(f"Manual device field '{field}' cannot be empty")
        _validate_target(values["target"])
        return cls(**values)


def load_manual_devices(path: Path) -> list[ManualDevice]:
    """Czyta ręczne wpisy; brak pliku oznacza pustą listę."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("devices"), list):
            raise ValueError("Unsupported manual.json format; expected version 1")
        return [ManualDevice.from_dict(item) for item in data["devices"]]
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error


def save_manual_devices(path: Path, devices: list[ManualDevice]) -> None:
    """Zapisuje manual.json atomowo i ogranicza dostęp do właściciela."""
    payload = {"version": 1, "devices": [device.to_dict() for device in devices]}
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(prefix="manual-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def merge_manual_devices(
    regions: list[Node], devices: list[ManualDevice], *,
    layout: str = "regions", unassigned_group: str = "Other sites",
) -> list[Node]:
    """Zwraca kopię drzewa NetBoxa uzupełnioną urządzeniami ręcznymi."""
    merged = [Node.from_dict(region.to_dict()) for region in regions]
    for manual in devices:
        nodes = merged
        current: Node | None = None
        path = manual.display_path(layout, unassigned_group)
        for index, name in enumerate(path):
            kind = "site" if index == len(path) - 1 else "region"
            if layout == "regions" and not manual.region and index == 0:
                kind = "group"
            current = _find_or_create(nodes, name, kind)
            nodes = current.children
        assert current is not None
        current.manual_location = (manual.region, manual.country, manual.city, manual.branch)
        current.devices.append(manual.as_device())
    _sort_tree(merged)
    return merged


def validate_manual_target(target: str) -> None:
    """Publiczna walidacja używana także przez formularz TUI."""
    _validate_target(target.strip())


def _validate_target(target: str) -> None:
    if not target or target.startswith("-") or any(character.isspace() for character in target):
        raise ValueError("Target must be an IP address or hostname without whitespace")


def _find_or_create(nodes: list[Node], name: str, kind: str) -> Node:
    for node in nodes:
        if node.name.casefold() == name.casefold() and (node.kind == "group") == (kind == "group"):
            return node
    node = Node(name, kind=kind)
    nodes.append(node)
    return node


def _sort_tree(nodes: list[Node]) -> None:
    nodes.sort(key=lambda node: node.name.casefold())
    for node in nodes:
        node.devices.sort(key=lambda device: (device.role.casefold(), device.name.casefold()))
        _sort_tree(node.children)
