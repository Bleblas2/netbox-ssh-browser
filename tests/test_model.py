import unittest

from netbox_ssh.model import build_tree
from netbox_ssh.inventory import normalize_inventory


def tree_from_api(regions, sites, devices, **options):
    return build_tree(**normalize_inventory(regions, sites, devices), **options)


class BuildTreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.regions = [
            {"id": 1, "name": "Region Group A", "parent": None},
            {"id": 2, "name": "Country A", "parent": {"id": 1}},
            {"id": 354, "name": "City A", "parent": {"id": 2}},
        ]

    def test_skips_configured_root_and_avoids_duplicate_site(self) -> None:
        sites = [{"id": 10, "name": "City A", "region": {"id": 354}}]
        devices = [{
            "name": "switch-a-01",
            "site": {"id": 10},
            "role": {"name": "Switch"},
            "primary_ip4": {"address": "192.0.2.3/24"},
        }]
        regions = tree_from_api(self.regions, sites, devices)
        self.assertEqual([item.name for item in regions], ["Region Group A"])
        country = regions[0].children[0]
        self.assertEqual(country.name, "Country A")
        city = country.children[0]
        self.assertEqual(city.name, "City A")
        self.assertEqual(city.devices[0].ssh_target, "192.0.2.3")
        self.assertEqual(city.children, [])

    def test_adds_differently_named_site_and_falls_back_to_hostname(self) -> None:
        sites = [{"id": 10, "name": "Warehouse 1", "region": {"id": 354}}]
        devices = [{
            "name": "switch-a-01",
            "site": {"id": 10},
            "device_role": {"name": "Switch"},
            "primary_ip4": None,
            "primary_ip6": None,
        }]
        regions = tree_from_api(self.regions, sites, devices)
        branch = regions[0].children[0].children[0].children[0]
        self.assertEqual(branch.name, "Warehouse 1")
        self.assertEqual(branch.devices[0].ssh_target, "switch-a-01")

    def test_uses_display_for_device_without_a_name(self) -> None:
        sites = [{"id": 10, "name": "City A", "region": {"id": 354}}]
        devices = [
            {
                "id": 74,
                "name": None,
                "display": "unnamed-device-74",
                "site": {"id": 10},
                "role": {"name": "Switch"},
                "primary_ip4": {"address": "192.0.2.74/24"},
            }
        ]

        regions = tree_from_api(self.regions, sites, devices)

        device = regions[0].children[0].children[0].devices[0]
        self.assertEqual(device.name, "unnamed-device-74")
        self.assertEqual(device.ssh_target, "192.0.2.74")

    def test_uses_device_id_when_name_and_display_are_missing(self) -> None:
        sites = [{"id": 10, "name": "City A", "region": {"id": 354}}]
        devices = [
            {
                "id": 75,
                "oob_ip": {"address": "192.0.2.75/32"},
                "name": None,
                "display": None,
                "site": {"id": 10},
                "role": None,
            }
        ]

        regions = tree_from_api(self.regions, sites, devices)

        device = regions[0].children[0].children[0].devices[0]
        self.assertEqual(device.name, "Device 75")
        self.assertEqual(device.role, "Other")

    def test_ignores_first_level_of_every_region_tree(self) -> None:
        regions = self.regions + [
            {"id": 500, "name": "Region Group B", "parent": None},
            {"id": 501, "name": "Country B", "parent": {"id": 500}},
            {"id": 502, "name": "City B", "parent": {"id": 501}},
        ]
        sites = [
            {"id": 10, "name": "City A", "region": {"id": 354}},
            {"id": 11, "name": "City B", "region": {"id": 502}},
        ]
        devices = [
            {"name": "switch-a", "site": {"id": 10}, "role": {"name": "Switch"}},
            {"name": "switch-b", "site": {"id": 11}, "role": {"name": "Switch"}},
        ]
        trees = tree_from_api(regions, sites, devices)
        self.assertEqual(
            [region.name for region in trees], ["Region Group A", "Region Group B"]
        )
        self.assertEqual(
            [region.children[0].name for region in trees], ["Country A", "Country B"]
        )

    def test_removes_regions_containing_only_empty_descendants(self) -> None:
        regions = [
            {"id": 1, "name": "Asia", "parent": None},
            {"id": 2, "name": "Empty Country", "parent": {"id": 1}},
            {"id": 3, "name": "Europe", "parent": None},
            {"id": 4, "name": "Empty City", "parent": {"id": 3}},
            {"id": 5, "name": "North America", "parent": None},
            {"id": 6, "name": "United States", "parent": {"id": 5}},
        ]
        sites = [{"id": 10, "name": "United States", "region": {"id": 6}}]
        devices = [
            {
                "name": "router-one",
                "site": {"id": 10},
                "role": {"name": "Router"},
            }
        ]

        trees = tree_from_api(regions, sites, devices)

        self.assertEqual([region.name for region in trees], ["North America"])

    def test_site_only_and_mixed_layouts(self):
        sites = [
            {"id": 10, "name": "Assigned", "region": {"id": 354}},
            {"id": 11, "name": "Unassigned", "region": None},
        ]
        devices = [
            {"id": i, "name": f"core-{i}", "site": {"id": site_id}, "role": {"name": "Core"}}
            for i, site_id in ((1, 10), (2, 11))
        ]
        flat = tree_from_api(self.regions, sites, devices, layout="sites")
        self.assertEqual([node.name for node in flat], ["Assigned", "Unassigned"])
        self.assertEqual([node.devices[0].identifier for node in flat], ["netbox:1", "netbox:2"])
        no_regions = tree_from_api([], sites, devices)
        self.assertEqual([node.name for node in no_regions], ["Assigned", "Unassigned"])
        mixed = tree_from_api(self.regions, sites, devices)
        group = next(node for node in mixed if node.kind == "group")
        self.assertEqual(group.name, "Other sites")
        self.assertEqual(group.children[0].devices[0].identifier, "netbox:2")
        explicit = tree_from_api([], sites, devices, layout="regions", unassigned_group="Unassigned")
        self.assertEqual(explicit[0].name, "Unassigned")
        self.assertEqual(len(explicit[0].children), 2)

    def test_sites_with_same_name_keep_separate_devices(self):
        sites = [{"id": i, "name": "Office", "region": None} for i in (1, 2)]
        devices = [{"id": i, "name": f"core-{i}", "site": i} for i in (1, 2)]
        roots = tree_from_api([], sites, devices)
        self.assertEqual(len(roots), 2)
        self.assertEqual([node.devices[0].identifier for node in roots], ["netbox:1", "netbox:2"])


if __name__ == "__main__":
    unittest.main()
