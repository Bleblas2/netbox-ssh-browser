"""Regional view regression tests using synthetic inventory, without Docker."""
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from textual.widgets import ListView

from netbox_ssh.inventory import normalize_inventory
from netbox_ssh.cache import load_cache, save_cache
from netbox_ssh.config import Config
from netbox_ssh.manual import ManualDevice, load_manual_devices
from netbox_ssh.tui import AddDeviceScreen, NetBoxSSHApp, View


def regional_inventory():
    """Small synthetic fixture mirroring demo's continent/country/city/state shapes."""
    return {
        "regions": [
            {"id": 1, "name": "Europe", "parent": None},
            {"id": 2, "name": "Poland", "parent": 1},
            {"id": 3, "name": "Warsaw", "parent": 2},
            {"id": 4, "name": "Krakow", "parent": 2},
            {"id": 5, "name": "Asia", "parent": None},
            {"id": 6, "name": "Singapore", "parent": 5},
            {"id": 7, "name": "Singapore", "parent": 6},
            {"id": 8, "name": "North America", "parent": None},
            {"id": 9, "name": "United States", "parent": 8},
            {"id": 10, "name": "New York", "parent": 9},
            {"id": 11, "name": "Empty state", "parent": 9},
            {"id": 12, "name": "Africa", "parent": None},
        ],
        "sites": [
            {"id": 21, "name": "PL-WAW", "region": 3},
            {"id": 22, "name": "PL-KRK", "region": 4},
            {"id": 23, "name": "SG-SIN", "region": 7},
            {"id": 24, "name": "US-ALB", "region": 10},
            {"id": 25, "name": "US-BUF", "region": 10},
            {"id": 26, "name": "Empty site", "region": 11},
        ],
        "devices": [
            {"id": index, "name": f"switch-{index}", "site": site,
             "role": {"name": "Core" if index % 2 else "Access"},
             "primary_ip4": {"address": f"192.0.2.{index}/32"}}
            for index, site in enumerate((21, 21, 22, 23, 24, 25), start=1)
        ],
    }


def make_config(root, layout="auto"):
    return Config(
        netbox_url="https://netbox.example.invalid", api_token="test-token",
        verify_ssl=True, cache_path=root / "cache.json",
        manual_path=root / "manual.json", config_path=root / "config.toml",
        device_roles=(), device_statuses=(), ignored_manufacturers=(),
        tree_layout=layout,
    )


def visible_devices(app):
    """Visit every selectable UI route, including role submenus, not raw nodes."""
    original = app.views
    result = []
    paths = []

    def visit(views):
        app.views = views
        for entry in app._entries_for_view():
            if entry.kind == "device":
                result.append(entry.value)
                paths.append(views[-1].path)
            elif entry.kind == "node":
                visit([*views, View(entry.label, node=entry.value, path=entry.path)])
            elif entry.kind == "role":
                visit([*views, View(entry.label, role_devices=entry.value, path=views[-1].path)])

    try:
        visit([View(app._root_title())])
    finally:
        app.views = original
    return result, paths


class RegionalInventoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = make_config(self.root)
        self.inventory = regional_inventory()
        self.cache = save_cache(self.config.cache_path, normalize_inventory(**self.inventory))

    def test_all_devices_reachable_once_in_every_layout_after_cache_reload(self):
        expected = Counter(f"netbox:{device['id']}" for device in self.inventory["devices"])
        for layout in ("auto", "regions", "sites"):
            with self.subTest(layout=layout):
                app = NetBoxSSHApp(replace(self.config, tree_layout=layout), load_cache(self.config.cache_path))
                devices, paths = visible_devices(app)
                self.assertEqual(Counter(device.identifier for device in devices), expected)
                self.assertEqual(app.effective_layout, "sites" if layout == "sites" else "regions")
                self.assertTrue(all(len(path) == 1 if layout == "sites" else len(path) == 4 for path in paths))
                self.assertNotIn("Africa", [entry.label for entry in app._entries_for_view()])
                self.assertNotIn("Empty site", [entry.label for entry in app._entries_for_view()])

    async def open_entry(self, app, pilot, label):
        app.query_one(ListView).index = next(
            index for index, entry in enumerate(app.visible_entries)
            if entry.kind == "node" and entry.label == label
        )
        await pilot.press("enter")
        await pilot.pause()

    async def test_country_city_site_navigation_and_regional_manual_save(self):
        app = NetBoxSSHApp(self.config, self.cache)
        async with app.run_test() as pilot:
            self.assertEqual([(e.kind, e.label) for e in app.visible_entries], [
                ("heading", "Asia"), ("node", "Singapore"),
                ("heading", "Europe"), ("node", "Poland"),
                ("heading", "North America"), ("node", "United States"),
            ])
            await self.open_entry(app, pilot, "Poland")
            self.assertEqual([(e.kind, e.label) for e in app.visible_entries], [
                ("heading", "Krakow"), ("node", "PL-KRK"),
                ("heading", "Warsaw"), ("node", "PL-WAW"),
            ])
            await pilot.press("+")
            self.assertNotIsInstance(app.screen, AddDeviceScreen)
            await self.open_entry(app, pilot, "PL-WAW")
            self.assertEqual(app.views[-1].path, ("Europe", "Poland", "Warsaw", "PL-WAW"))
            self.assertEqual([(e.kind, e.label) for e in app.visible_entries], [
                ("heading", "Access"), ("device", "switch-2"),
                ("heading", "Core"), ("device", "switch-1"),
            ])
            await pilot.press("+")
            self.assertIsInstance(app.screen, AddDeviceScreen)
            await pilot.press(*list("manual-core"), "enter")
            await pilot.press(*list("192.0.2.50"), "enter", "enter")
            await pilot.pause()
            manual = load_manual_devices(self.config.manual_path)[0]
            self.assertEqual(manual.location_path, ("Europe", "Poland", "Warsaw", "PL-WAW"))
            await pilot.press("escape")
            self.assertEqual(app.visible_entries[app.query_one(ListView).index].label, "PL-WAW")

    async def test_layout_round_trip_keeps_manual_and_jump_state_offline(self):
        manual = ManualDevice("Europe", "Poland", "Warsaw", "PL-WAW", "Core", "manual", "192.0.2.50")
        marked = {"netbox:1", "manual:europe/poland/warsaw/pl-waw/manual"}
        app = NetBoxSSHApp(self.config, self.cache, [manual], marked)
        with patch("netbox_ssh.service.NetBoxClient", side_effect=AssertionError("Unexpected API call")):
            async with app.run_test() as pilot:
                for layout in ("sites", "regions", "auto"):
                    app.config = replace(app.config, tree_layout=layout)
                    app._rebuild_view()
                    await pilot.pause()
                    devices, _ = visible_devices(app)
                    self.assertEqual(len(devices), 7)
                    self.assertEqual({d.identifier for d in devices if d.use_jump_host}, marked)
                    if layout == "sites":
                        self.assertEqual([e.label for e in app.visible_entries],
                                         ["PL-KRK", "PL-WAW", "SG-SIN", "US-ALB", "US-BUF"])
                        await self.open_entry(app, pilot, "PL-WAW")
                        self.assertEqual(len([e for e in app.visible_entries if e.kind == "device"]), 3)
                    else:
                        self.assertEqual(app.views[0].title, "Countries")
                self.assertEqual(manual.region, "Europe")

if __name__ == "__main__":
    unittest.main()
