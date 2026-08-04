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


if __name__ == "__main__":
    unittest.main()
