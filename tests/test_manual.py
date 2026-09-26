import stat
import tempfile
import unittest
from pathlib import Path

from netbox_ssh.manual import (
    ManualDevice,
    load_manual_devices,
    merge_manual_devices,
    save_manual_devices,
    validate_manual_target,
)
from netbox_ssh.model import Node


class ManualInventoryTests(unittest.TestCase):
    def test_round_trip_and_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "manual.json"
            source = [
                ManualDevice(
                    "Region Group A",
                    "Country A",
                    "City A",
                    "branch-a-01",
                    "Access Switch",
                    "manual-sw-01",
                    "192.0.2.50",
                )
            ]
            save_manual_devices(path, source)
            self.assertEqual(load_manual_devices(path), source)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_merges_existing_and_missing_location_path(self) -> None:
        regions = [Node("Region Group A", children=[Node("Country A")])]
        manual = ManualDevice(
            "Region Group A",
            "Country A",
            "City A",
            "branch-a-01",
            "Access Switch",
            "manual-sw-01",
            "manual-sw-01.example.com",
        )
        merged = merge_manual_devices(regions, [manual])
        branch = merged[0].children[0].children[0].children[0]
        self.assertEqual(branch.name, "branch-a-01")
        self.assertEqual(branch.devices[0].source, "manual")
        self.assertEqual(branch.devices[0].ssh_target, "manual-sw-01.example.com")
        self.assertEqual(regions[0].children[0].children, [])

    def test_rejects_option_like_or_whitespace_target(self) -> None:
        for target in ("-oProxyCommand=bad", "host name"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_manual_target(target)

    def test_optional_location_fields_and_round_trip(self):
        base = {"branch": "Office", "role": "Core", "name": "manual", "target": "10.0.0.1"}
        for optional in ({}, {"region": "", "country": "", "city": ""},
                         {"region": None, "country": None, "city": None}):
            with self.subTest(optional=optional):
                manual = ManualDevice.from_dict({**base, **optional})
                self.assertEqual(manual.location_path, ("Office",))
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "manual.json"
                    save_manual_devices(path, [manual])
                    self.assertEqual(load_manual_devices(path), [manual])
        for field in base:
            for value in ("", None, 5):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    ManualDevice.from_dict({**base, field: value})

    def test_layout_changes_do_not_change_manual_identifier(self):
        manual = ManualDevice("Europe", "Poland", "Office", "Office", "Core", "extra", "10.0.0.2")
        regional = merge_manual_devices([], [manual])
        flat = merge_manual_devices([], [manual], layout="sites")
        regional_device = regional[0].children[0].children[0].devices[0]
        self.assertEqual(flat[0].name, "Office")
        self.assertEqual(flat[0].devices[0].identifier, regional_device.identifier)
        self.assertEqual(regional_device.identifier, "manual:europe/poland/office/extra")
        self.assertEqual(manual.region, "Europe")

    def test_missing_region_uses_group_without_empty_nodes(self):
        manual = ManualDevice("", "", "Town", "Office", "Core", "extra", "10.0.0.2")
        roots = merge_manual_devices([], [manual], unassigned_group="Unassigned")
        self.assertEqual(roots[0].kind, "group")
        self.assertEqual(roots[0].name, "Unassigned")
        self.assertEqual(roots[0].children[0].name, "Town")
        self.assertEqual(roots[0].children[0].children[0].name, "Office")


if __name__ == "__main__":
    unittest.main()
