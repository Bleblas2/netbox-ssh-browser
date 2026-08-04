import unittest

from netbox_ssh.model import build_tree


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
        regions = build_tree(self.regions, sites, devices)
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
        regions = build_tree(self.regions, sites, devices)
        branch = regions[0].children[0].children[0].children[0]
        self.assertEqual(branch.name, "Warehouse 1")
        self.assertEqual(branch.devices[0].ssh_target, "switch-a-01")

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
        trees = build_tree(regions, sites, devices)
        self.assertEqual(
            [region.name for region in trees], ["Region Group A", "Region Group B"]
        )
        self.assertEqual(
            [region.children[0].name for region in trees], ["Country A", "Country B"]
        )


if __name__ == "__main__":
    unittest.main()
