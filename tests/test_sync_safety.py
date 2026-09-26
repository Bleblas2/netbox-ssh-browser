import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx

from netbox_ssh.cache import load_cache, save_cache
from netbox_ssh.inventory import normalize_inventory
from netbox_ssh.service import describe_sync_error, synchronize
from test_regional_inventory import make_config


class SyncSafetyTests(unittest.TestCase):
    def test_address_selection_is_applied_before_cache_write(self):
        devices = [
            {"id": 1, "name": "oob", "site": 1, "oob_ip": {"address": "192.0.2.1/32"}},
            {"id": 2, "name": "primary", "site": 1, "primary_ip4": {"address": "192.0.2.2/32"}},
            {"id": 3, "name": "dns.example.test", "site": 1},
        ]
        with tempfile.TemporaryDirectory() as directory:
            config = replace(make_config(Path(directory)), address_order=("oob_ip",))
            with patch("netbox_ssh.service.NetBoxClient") as client:
                client.return_value.__enter__.return_value.fetch_inventory.return_value = (
                    [], [{"id": 1, "name": "Office"}], devices,
                )
                cache, count = synchronize(config)
            self.assertEqual(count, 3)
            self.assertEqual([d["identifier"] for d in cache.devices], ["netbox:1"])
            self.assertEqual(load_cache(config.cache_path), cache)
            self.assertNotIn("dns.example.test", config.cache_path.read_text())



if __name__ == "__main__":
    unittest.main()
