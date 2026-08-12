from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Device:
    """Minimalny zestaw danych urządzenia wymagany do menu i połączenia SSH."""

    name: str
    role: str
    primary_ip: str | None = None
    source: str = "netbox"
    identifier: str | None = None
    use_jump_host: bool = False

    @property
    def ssh_target(self) -> str:
        # NetBox zapisuje IP wraz z maską, której klient ssh nie przyjmuje.
        return self.primary_ip.split("/", 1)[0] if self.primary_ip else self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "primary_ip": self.primary_ip,
            "source": self.source,
            "identifier": self.identifier,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Device":
        return cls(
            data["name"],
            data["role"],
            data.get("primary_ip"),
            data.get("source", "netbox"),
            data.get("identifier"),
        )


@dataclass
class Node:
    """Uniwersalny węzeł drzewa: region, kraj, miasto albo oddział."""

    name: str
    children: list["Node"] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "children": [child.to_dict() for child in self.children],
            "devices": [device.to_dict() for device in self.devices],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Node":
        return cls(
            name=data["name"],
            children=[cls.from_dict(item) for item in data.get("children", [])],
            devices=[Device.from_dict(item) for item in data.get("devices", [])],
        )


def build_tree(
    regions: list[dict[str, Any]],
    sites: list[dict[str, Any]],
    devices: list[dict[str, Any]],
) -> list[Node]:
    """Łączy płaskie odpowiedzi API w drzewo lokalizacji z urządzeniami."""
    nodes = {item["id"]: Node(item["name"]) for item in regions}
    region_parent: dict[int, int | None] = {}
    roots: list[Node] = []

    for item in regions:
        # Odtwarzamy dowolnie głębokie drzewo na podstawie relacji parent.
        parent_id = _object_id(item.get("parent"))
        region_parent[item["id"]] = parent_id
        if parent_id in nodes:
            nodes[parent_id].children.append(nodes[item["id"]])
        else:
            roots.append(nodes[item["id"]])

    sites_by_id = {item["id"]: item for item in sites}
    for raw in devices:
        # Standardowy NetBox przypisuje urządzenie do site, a site do regionu.
        site_id = _object_id(raw.get("site"))
        site = sites_by_id.get(site_id)
        if not site:
            continue
        region_id = _object_id(site.get("region"))
        if region_id not in nodes:
            continue
        region_node = nodes[region_id]
        target_node = region_node
        site_name = site.get("name") or site.get("display")
        if site_name and site_name.casefold() != region_node.name.casefold():
            # Nie dublujemy poziomu, gdy site i końcowy region mają tę samą nazwę.
            target_node = _child_named(region_node, site_name)
        role = raw.get("role") or raw.get("device_role") or {}
        role_name = role.get("name") or role.get("display") or "Other"
        # NetBox zezwala na urządzenia bez nazwy. W takim przypadku odpowiedź
        # API zawiera zwykle czytelne `display`; ID pozostaje ostatnim,
        # stabilnym fallbackiem i gwarantuje tekst wymagany przez TUI.
        device_name = raw.get("name") or raw.get("display")
        if not device_name:
            device_id = raw.get("id")
            device_name = (
                f"Device {device_id}" if device_id is not None else "Unnamed device"
            )
        ip = raw.get("primary_ip4") or raw.get("primary_ip6")
        if isinstance(ip, dict):
            ip = ip.get("address") or ip.get("display")
        device_id = raw.get("id")
        identifier = f"netbox:{device_id}" if device_id is not None else None
        target_node.devices.append(
            Device(str(device_name), str(role_name), ip, identifier=identifier)
        )

    _prune_and_sort(roots)
    return roots


def _child_named(parent: Node, name: str) -> Node:
    """Zwraca istniejący węzeł site albo tworzy go bez dublowania nazwy."""
    for child in parent.children:
        if child.name.casefold() == name.casefold():
            return child
    child = Node(name)
    parent.children.append(child)
    return child


def _object_id(value: Any) -> int | None:
    if isinstance(value, dict):
        return value.get("id")
    return value if isinstance(value, int) else None


def _prune_and_sort(nodes: list[Node]) -> None:
    # Puste gałęzie nie pomagają w nawigacji, więc nie zapisujemy ich w cache.
    # Najpierw czyścimy potomków, bo rodzic zawierający wyłącznie puste gałęzie
    # również powinien zostać usunięty.
    for node in nodes:
        _prune_and_sort(node.children)
        node.devices.sort(key=lambda item: (item.role.casefold(), item.name.casefold()))
    nodes[:] = [node for node in nodes if node.children or node.devices]
    nodes.sort(key=lambda item: item.name.casefold())
