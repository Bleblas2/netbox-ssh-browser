import tempfile
import unittest
import stat
import json
from pathlib import Path

from netbox_ssh.inventory import normalize_inventory
from netbox_ssh.cache import load_cache, save_cache


class CacheTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            source = normalize_inventory(
                [], [{"id": 10, "name": "Office", "region": None}],
                [{"id": 42, "name": "router-1", "site": {"id": 10},
                  "role": {"name": "Router"}, "primary_ip4": {"address": "192.0.2.1/24"}}],
            )
            saved = save_cache(path, source)
            loaded = load_cache(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.synced_at, saved.synced_at)
            self.assertEqual(loaded.tree()[0].devices[0].ssh_target, "192.0.2.1")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_ignores_unsupported_cache_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            path.write_text(
                json.dumps({"version": 1, "synced_at": "old", "countries": []}),
                encoding="utf-8",
            )
            self.assertIsNone(load_cache(path))

    def test_layout_can_change_after_loading_without_api(self):
        inventory = normalize_inventory(
            [{"id": 1, "name": "Europe", "parent": None}],
            [{"id": 2, "name": "Office", "region": {"id": 1}}],
            [{"id": 3, "name": "core", "site": {"id": 2}, "role": {"name": "Core"}}],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            save_cache(path, inventory)
            cache = load_cache(path)
            self.assertEqual(cache.tree("regions")[0].name, "Europe")
            self.assertEqual(cache.tree("sites")[0].name, "Office")
            self.assertEqual(cache.tree("sites")[0].devices[0].identifier, "netbox:3")

    def test_old_or_malformed_cache_requires_sync(self):
        cases = [
            {"version": 2, "synced_at": "old", "regions": []},
            [],
            {"version": 3, "synced_at": "now", "regions": [], "sites": None, "devices": []},
            {"version": 3, "synced_at": "now", "regions": [], "sites": [], "devices": [{}]},
            {"version": 3, "synced_at": "now", "regions": [
                {"id": 1, "name": "Cycle", "parent_id": 1}], "sites": [], "devices": []},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            for payload in cases:
                with self.subTest(payload=payload):
                    path.write_text(json.dumps(payload))
                    self.assertIsNone(load_cache(path))


if __name__ == "__main__":
    unittest.main()
