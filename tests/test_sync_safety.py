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

    def test_rejected_pagination_keeps_previous_cache_unchanged(self):
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == "/api/status/":
                return httpx.Response(200, json={})
            return httpx.Response(200, json={
                "results": [{"id": 99, "name": "New region", "parent": None}],
                "next": "https://other.example/collect",
            })

        with tempfile.TemporaryDirectory() as directory:
            config = replace(make_config(Path(directory)), netbox_url="https://netbox.example")
            previous = save_cache(config.cache_path, normalize_inventory(
                [], [{"id": 1, "name": "Office", "region": None}],
                [{"id": 2, "name": "core", "site": 1}],
            ))
            before = config.cache_path.read_bytes()
            client_class = httpx.Client
            with patch("netbox_ssh.netbox.httpx.Client", side_effect=lambda **kwargs: client_class(
                transport=httpx.MockTransport(handler), **kwargs,
            )):
                with self.assertRaises(httpx.RequestError) as error:
                    synchronize(config)
            self.assertEqual(config.cache_path.read_bytes(), before)
            self.assertEqual(load_cache(config.cache_path), previous)
            self.assertEqual(len(requests), 2)
            self.assertTrue(all(request.url.host == "netbox.example" for request in requests))
            self.assertIn("configured NetBox origin", describe_sync_error(error.exception))
            self.assertNotIn(config.api_token, describe_sync_error(error.exception))


if __name__ == "__main__":
    unittest.main()
