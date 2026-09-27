"""Regression coverage for concurrent sync/manual saves and regional navigation."""

import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Input, ListView

from netbox_ssh.cache import Cache, load_cache, save_cache
from netbox_ssh.inventory import normalize_inventory
from netbox_ssh.manual import load_manual_devices
from netbox_ssh.service import synchronize
from netbox_ssh.tui import AddDeviceScreen, NetBoxSSHApp
from test_regional_inventory import make_config, visible_devices


def regional_inventory(*, country_site=False, country_device=False):
    """A country and city with one active branch, optionally a same-name Site."""
    inventory = {
        "regions": [
            {"id": 1, "name": "Europe", "parent": None},
            {"id": 2, "name": "Poland", "parent": 1},
            {"id": 3, "name": "Warsaw", "parent": 2},
        ],
        "sites": [{"id": 21, "name": "PL-WAW", "region": 3}],
        "devices": [device(1, 21, "branch-core")],
    }
    if country_site:
        inventory["sites"].append({"id": 22, "name": "Poland", "region": 2})
    if country_device:
        inventory["devices"].append(device(2, 22, "country-core"))
    return inventory


def device(identifier, site, name):
    return {
        "id": identifier, "site": site, "name": name,
        "role": {"name": "Core"},
        "primary_ip4": {"address": f"192.0.2.{identifier}/32"},
    }


class ReviewRegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    async def open_entry(self, app, pilot, label, kind="node"):
        app.query_one(ListView).index = next(
            index for index, entry in enumerate(app.visible_entries)
            if entry.kind == kind and entry.label == label
        )
        await pilot.press("enter")
        await pilot.pause()

    async def assert_manual_save_after_sync(self, layout, *, remove_site=False):
        config = make_config(self.root, layout)
        initial = regional_inventory()
        cache = save_cache(config.cache_path, normalize_inventory(**initial))
        app = NetBoxSSHApp(config, cache)
        async with app.run_test() as pilot:
            if layout == "regions":
                await self.open_entry(app, pilot, "Poland")
            await self.open_entry(app, pilot, "PL-WAW")
            original_path = app.views[-1].path
            await pilot.press("+")
            form = app.screen
            self.assertIsInstance(form, AddDeviceScreen)
            form.query_one("#manual-name", Input).value = "manual-core"
            form.query_one("#manual-target", Input).value = "192.0.2.50"
            form.query_one("#manual-role", Input).value = "Core"

            # Replace inventory while the real form/callback remains active.
            # The new branch also proves the save did not restore stale cache.
            refreshed = regional_inventory()
            if remove_site:
                refreshed["sites"].clear()
                refreshed["devices"].clear()
            refreshed["sites"].append({"id": 23, "name": "PL-NEW", "region": 3})
            refreshed["devices"].append(device(3, 23, "new-core"))
            latest = save_cache(config.cache_path, normalize_inventory(**refreshed))
            app.syncing = True
            app._sync_finished(latest, len(refreshed["devices"]))
            await pilot.pause()
            self.assertIs(app.screen, form)
            self.assertFalse(app.syncing)
            self.assertTrue(await pilot.click("#manual-save"))
            await pilot.pause()

            self.assertNotIsInstance(app.screen, AddDeviceScreen)
            manuals = load_manual_devices(config.manual_path)
            self.assertEqual(len(manuals), 1)
            self.assertEqual(manuals[0].location_path, original_path)
            self.assertEqual(manuals[0].name, "manual-core")
            self.assertEqual(app.manual_devices, manuals)
            self.assertIs(app.cache, latest)
            self.assertEqual(load_cache(config.cache_path), latest)
            self.assertEqual(app.views[-1].path, original_path)
            self.assertEqual(app.views[-1].title, "PL-WAW")
            self.assertEqual(
                [entry.label for entry in app.visible_entries if entry.kind == "device"],
                ["manual-core"] if remove_site else ["branch-core", "manual-core"],
            )
            reachable, _ = visible_devices(app)
            expected = Counter({"netbox:3": 1, manuals[0].as_device().identifier: 1})
            if not remove_site:
                expected["netbox:1"] = 1
            self.assertEqual(Counter(item.identifier for item in reachable), expected)

    async def test_sites_manual_save_after_sync_keeps_original_location_and_latest_cache(self):
        await self.assert_manual_save_after_sync("sites")

    async def test_regions_manual_save_after_sync_keeps_original_location_and_latest_cache(self):
        await self.assert_manual_save_after_sync("regions")

    async def test_manual_save_after_sync_removed_site_recreates_manual_location(self):
        for layout in ("sites", "regions"):
            with self.subTest(layout=layout):
                await self.assert_manual_save_after_sync(layout, remove_site=True)

    async def assert_regional_navigation(self, cache, *, country_device=False):
        app = NetBoxSSHApp(make_config(self.root, "regions"), cache)
        async with app.run_test() as pilot:
            self.assertEqual(
                [(entry.kind, entry.label, entry.detail) for entry in app.visible_entries],
                [("heading", "Europe", "Region"), ("node", "Poland", "Country")],
            )
            await self.open_entry(app, pilot, "Poland")
            expected = [("heading", "Warsaw", "City"), ("node", "PL-WAW", "Branch")]
            if country_device:
                expected.append(("role", "Core", "1 devices"))
            self.assertEqual(
                [(entry.kind, entry.label, entry.detail) for entry in app.visible_entries],
                expected,
            )
            await self.open_entry(app, pilot, "PL-WAW")
            self.assertEqual(app.views[-1].path, ("Europe", "Poland", "Warsaw", "PL-WAW"))
            self.assertEqual(
                [(entry.kind, entry.label) for entry in app.visible_entries],
                [("heading", "Core"), ("device", "branch-core")],
            )
            if country_device:
                await pilot.press("escape")
                await self.open_entry(app, pilot, "Core", kind="role")
                self.assertEqual(
                    [(entry.kind, entry.label) for entry in app.visible_entries],
                    [("device", "country-core")],
                )
            reachable, _ = visible_devices(app)
            expected_devices = Counter({"netbox:1": 1})
            if country_device:
                expected_devices["netbox:2"] = 1
            self.assertEqual(Counter(item.identifier for item in reachable), expected_devices)

    async def test_empty_same_name_site_preserves_country_city_branch_navigation(self):
        inventory = regional_inventory(country_site=True)
        cache = Cache("now", **normalize_inventory(**inventory))
        await self.assert_regional_navigation(cache)

    async def test_filtered_same_name_site_preserves_country_city_branch_navigation(self):
        inventory = regional_inventory(country_site=True, country_device=True)
        config = replace(make_config(self.root), ignored_name_patterns=("country-*",))
        with patch("netbox_ssh.service.NetBoxClient") as client:
            client.return_value.__enter__.return_value.fetch_inventory.return_value = (
                inventory["regions"], inventory["sites"], inventory["devices"],
            )
            cache, count = synchronize(config)
        self.assertEqual(count, 1)
        self.assertEqual(len(cache.sites), 2)
        await self.assert_regional_navigation(cache)

    async def test_populated_same_name_site_keeps_country_devices_and_descendants_reachable(self):
        inventory = regional_inventory(country_site=True, country_device=True)
        cache = Cache("now", **normalize_inventory(**inventory))
        await self.assert_regional_navigation(cache, country_device=True)


if __name__ == "__main__":
    unittest.main()
