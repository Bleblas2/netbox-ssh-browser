import unittest

from netbox_ssh.inventory import normalize_inventory, resolve_layout


class InventoryTests(unittest.TestCase):
    def test_normalization_keeps_connection_fields_and_drops_unrelated_api_data(self):
        inventory = normalize_inventory(
            [{"id": 1, "name": "Europe", "parent": None, "custom_fields": {"private": "ignored"}}],
            [{"id": 2, "name": "Office", "region": {"id": 1}, "comments": "ignored"}],
            [{"id": 3, "name": None, "display": "unnamed-core", "site": {"id": 2},
              "role": None, "device_role": {"display": "Core"}, "primary_ip4": None,
              "primary_ip6": {"address": "2001:db8::3/128"}, "config_context": {"private": "ignored"}}],
        )
        self.assertEqual(inventory, {
            "regions": [{"id": 1, "name": "Europe", "parent_id": None}],
            "sites": [{"id": 2, "name": "Office", "region_id": 1}],
            "devices": [{"identifier": "netbox:3", "site_id": 2, "name": "unnamed-core",
                         "role": "Core", "primary_ip": "2001:db8::3/128"}],
        })

    def test_address_priority_and_excluded_sources(self):
        raw = {"id": 1, "name": "router.example.test",
               "primary_ip4": {"address": "192.0.2.1/24"},
               "primary_ip6": {"address": "2001:db8::1/64"},
               "oob_ip": {"address": "192.0.2.99/24"}}
        for order, expected in (
            (("oob_ip", "primary_ip4"), "192.0.2.99/24"),
            (("primary_ip6", "oob_ip"), "2001:db8::1/64"),
            (("fqdn", "primary_ip4"), "router.example.test"),
            (("primary_ip4",), "192.0.2.1/24"),
        ):
            with self.subTest(order=order):
                devices = normalize_inventory([], [], [raw], order)["devices"]
                self.assertEqual(devices[0]["primary_ip"], expected)
        self.assertEqual(normalize_inventory([], [], [raw], ())["devices"], [])

    def test_missing_selected_address_never_falls_back_to_name_or_display(self):
        for missing in (None, {}, {"address": ""}, " "):
            raw = {"name": "router.example.test", "oob_ip": missing,
                   "primary_ip4": {"address": "192.0.2.1/24"}}
            with self.subTest(missing=missing):
                self.assertEqual(normalize_inventory([], [], [raw], ("oob_ip",))["devices"], [])
                devices = normalize_inventory([], [], [raw], ("oob_ip", "primary_ip4"))["devices"]
                self.assertEqual(devices[0]["primary_ip"], "192.0.2.1/24")
        for raw in ({"id": 1}, {"name": None, "display": "label"}, {"name": " "}):
            self.assertEqual(normalize_inventory([], [], [raw], ("fqdn",))["devices"], [])

    def test_auto_uses_either_inventory_and_explicit_layout_overrides_both(self):
        for cached, manual in ((False, False), (False, True), (True, False), (True, True)):
            with self.subTest(cached=cached, manual=manual):
                self.assertEqual(
                    resolve_layout("auto", has_regions=cached, has_manual_regions=manual),
                    "regions" if cached or manual else "sites",
                )
                for layout in ("regions", "sites"):
                    self.assertEqual(
                        resolve_layout(layout, has_regions=cached, has_manual_regions=manual), layout,
                    )
        with self.assertRaises(ValueError):
            resolve_layout("invalid", has_regions=False)


if __name__ == "__main__":
    unittest.main()
