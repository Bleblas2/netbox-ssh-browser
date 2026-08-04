import tempfile
import unittest
import stat
import json
from pathlib import Path

from netbox_ssh.cache import load_cache, save_cache
from netbox_ssh.model import Device, Node


class CacheTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            source = [
                Node(
                    "Country A",
                    devices=[Device("router-1", "Router", "192.0.2.1/24")],
                )
            ]
            saved = save_cache(path, source)
            loaded = load_cache(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.synced_at, saved.synced_at)
            self.assertEqual(loaded.regions[0].devices[0].ssh_target, "192.0.2.1")
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


if __name__ == "__main__":
    unittest.main()
