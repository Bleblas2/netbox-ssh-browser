from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .inventory import DeviceRecord, RegionRecord, SiteRecord, resolve_layout


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
    kind: str = "region"
    manual_location: tuple[str, str, str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "manual_location": self.manual_location,
            "children": [child.to_dict() for child in self.children],
            "devices": [device.to_dict() for device in self.devices],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Node":
        return cls(
            name=data["name"],
            children=[cls.from_dict(item) for item in data.get("children", [])],
            devices=[Device.from_dict(item) for item in data.get("devices", [])],
            kind=data.get("kind", "region"),
            manual_location=tuple(data["manual_location"]) if data.get("manual_location") else None,
        )


def build_tree(
    regions: list[RegionRecord],
    sites: list[SiteRecord],
    devices: list[DeviceRecord],
    *, layout: str = "auto", unassigned_group: str = "Other sites",
) -> list[Node]:
    """Buduje widok ze znormalizowanej inwentaryzacji, bez interpretowania API."""
    layout = resolve_layout(layout, has_regions=bool(regions))
    nodes = {item["id"]: Node(item["name"]) for item in regions}
    roots: list[Node] = []

    if layout == "regions":
        for item in regions:
            parent_id = item["parent_id"]
            if parent_id in nodes:
                nodes[parent_id].children.append(nodes[item["id"]])
            else:
                roots.append(nodes[item["id"]])

    site_nodes: dict[int, Node] = {}
    other_sites: Node | None = None
    for site in sites:
        name = site["name"]
        site_node = Node(name, kind="site")
        region_id = site["region_id"]
        if layout == "sites":
            roots.append(site_node)
        elif region_id in nodes:
            parent = nodes[region_id]
            if name.casefold() == parent.name.casefold():
                # Wspólna nazwa pozwala pominąć dodatkowy poziom, ale węzeł nadal
                # jest regionem. Nawet pusty Site nie może zmieniać nawigacji kraju.
                site_node = parent
            else:
                parent.children.append(site_node)
        else:
            if other_sites is None:
                other_sites = Node(unassigned_group, kind="group")
                roots.append(other_sites)
            other_sites.children.append(site_node)
            site_node.manual_location = ("", "", "", name)
        site_nodes[site["id"]] = site_node

    for record in devices:
        target_node = site_nodes.get(record["site_id"])
        if target_node is None:
            continue
        target_node.devices.append(
            Device(record["name"], record["role"], record["primary_ip"],
                   identifier=record["identifier"])
        )

    _prune_and_sort(roots)
    return roots


def _prune_and_sort(nodes: list[Node]) -> None:
    # Puste gałęzie nie pomagają w nawigacji, więc pomijamy je w widoku.
    # Najpierw czyścimy potomków, bo rodzic zawierający wyłącznie puste gałęzie
    # również powinien zostać usunięty.
    for node in nodes:
        _prune_and_sort(node.children)
        node.devices.sort(key=lambda item: (item.role.casefold(), item.name.casefold()))
    nodes[:] = [node for node in nodes if node.children or node.devices]
    nodes.sort(key=lambda item: item.name.casefold())
