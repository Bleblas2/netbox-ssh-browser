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
        return tuple(value for index, value in enumerate(values) if not index or value != values[index - 1])

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
        values = {field: str(data[field]).strip() for field in cls.__dataclass_fields__}
        if not all(values.values()):
            raise ValueError("Manual device fields cannot be empty")
        _validate_target(values["target"])
        return cls(**values)


def load_manual_devices(path: Path) -> list[ManualDevice]:
    """Czyta ręczne wpisy; brak pliku oznacza pustą listę."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("devices"), list):
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


def merge_manual_devices(regions: list[Node], devices: list[ManualDevice]) -> list[Node]:
    """Zwraca kopię drzewa NetBoxa uzupełnioną urządzeniami ręcznymi."""
    merged = [Node.from_dict(region.to_dict()) for region in regions]
    for manual in devices:
        nodes = merged
        current: Node | None = None
        for name in manual.location_path:
            current = _find_or_create(nodes, name)
            nodes = current.children
        assert current is not None
        current.devices.append(
            Device(manual.name, manual.role, manual.target, source="manual")
        )
    _sort_tree(merged)
    return merged


def validate_manual_target(target: str) -> None:
    """Publiczna walidacja używana także przez formularz TUI."""
    _validate_target(target.strip())


def _validate_target(target: str) -> None:
    if not target or target.startswith("-") or any(character.isspace() for character in target):
        raise ValueError("Target must be an IP address or hostname without whitespace")


def _find_or_create(nodes: list[Node], name: str) -> Node:
    for node in nodes:
        if node.name.casefold() == name.casefold():
            return node
    node = Node(name)
    nodes.append(node)
    return node


def _sort_tree(nodes: list[Node]) -> None:
    nodes.sort(key=lambda node: node.name.casefold())
    for node in nodes:
        node.devices.sort(key=lambda device: (device.role.casefold(), device.name.casefold()))
        _sort_tree(node.children)
