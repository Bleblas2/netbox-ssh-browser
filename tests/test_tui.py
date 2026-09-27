import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

from textual.widgets import ListView, Static

from netbox_ssh.cache import Cache
from netbox_ssh.config import Config
from netbox_ssh.model import Device, Node
from netbox_ssh.tui import NetBoxSSHApp, AddDeviceScreen
from netbox_ssh.manual import ManualDevice, load_manual_devices


def tree_cache(timestamp, roots):
    """Represent the existing hierarchical test fixtures as v3 inventory."""
    regions, sites, devices = [], [], []

    def visit(node, parent=None):
        region_id = len(regions) + 1
        regions.append({"id": region_id, "name": node.name, "parent_id": parent})
        if node.devices:
            sites.append({"id": region_id, "name": node.name, "region_id": region_id})
            for device in node.devices:
                devices.append({**device.to_dict(), "site_id": region_id})
        for child in node.children:
            visit(child, region_id)

    for node in roots:
        visit(node)
    return Cache(timestamp, regions, sites, devices)


class TUITests(unittest.IsolatedAsyncioTestCase):
    def make_app(self, cache: Cache | None, root: Path | None = None) -> NetBoxSSHApp:
        root = root or Path(tempfile.gettempdir()) / "netbox-ssh-browser-tui-test"
        config = Config(
            netbox_url="https://netbox.example.com",
            api_token="test",
            verify_ssl=True,
            cache_path=root / "cache.json",
            manual_path=root / "manual.json",
            config_path=root / "config.toml",
            device_roles=(),
            device_statuses=(),
            ignored_manufacturers=(),
        )
        return NetBoxSSHApp(config, cache)

    async def test_empty_cache_shows_empty_country_list(self) -> None:
        app = self.make_app(None)
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(app.visible_entries, [])

    async def test_navigates_country_and_searches_devices_by_ip(self) -> None:
        device = Device("switch-one", "Access Switch", "192.0.2.1/24")
        branch = Node("branch-a-01", devices=[device])
        country = Node("Country A", children=[Node("City A", children=[branch])])
        region = Node("Region Group A", children=[country])
        app = self.make_app(tree_cache("2026-08-02T00:00:00+02:00", [region]))
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(
                [(entry.kind, entry.label) for entry in app.visible_entries],
                [("heading", "Region Group A"), ("node", "Country A")],
            )
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual([view.title for view in app.views], ["Countries", "Country A"])
            self.assertEqual(
                [(entry.kind, entry.label) for entry in app.visible_entries],
                [("heading", "City A"), ("node", "branch-a-01")],
            )
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(app.views[-1].title, "branch-a-01")
            self.assertEqual(
                [(entry.kind, entry.label) for entry in app.visible_entries],
                [("heading", "Access Switch"), ("device", "switch-one")],
            )
            await pilot.press("/")
            await pilot.press("1", "9", "2", ".", "0", ".", "2")
            await pilot.pause()
            self.assertEqual([entry.label for entry in app.visible_entries], ["switch-one"])
            self.assertEqual(app.views[-1].title, "Device search")

    async def test_back_restores_last_selected_branch(self) -> None:
        first = Node("branch-a-01", devices=[Device("switch-one", "Switch")])
        second = Node("branch-b-01", devices=[Device("switch-two", "Switch")])
        country = Node(
            "Country A",
            children=[
                Node("City A", children=[first]),
                Node("City B", children=[second]),
            ],
        )
        app = self.make_app(
            tree_cache(
                "2026-08-02T00:00:00+02:00",
                [Node("Region Group A", children=[country])],
            )
        )
        async with app.run_test() as pilot:
            await pilot.press("enter", "down", "enter")
            await pilot.pause()
            self.assertEqual(app.views[-1].title, "branch-b-01")
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(app.query_one(ListView).index, 3)
            self.assertEqual(app.visible_entries[3].label, "branch-b-01")

    async def test_adds_manual_device_in_current_branch(self) -> None:
        device = Device("switch-one", "Access Switch", "192.0.2.1/24")
        branch = Node("branch-a-01", devices=[device])
        country = Node("Country A", children=[Node("City A", children=[branch])])
        region = Node("Region Group A", children=[country])
        with tempfile.TemporaryDirectory() as directory:
            app = self.make_app(
                tree_cache("2026-08-02T00:00:00+02:00", [region]), Path(directory)
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("enter", "enter", "+")
                await pilot.pause()
                await pilot.press(*list("manual-switch"), "enter")
                await pilot.press(*list("192.0.2.50"), "enter", "enter")
                await pilot.pause()
                self.assertEqual(len(app.manual_devices), 1)
                self.assertEqual(app.manual_devices[0].name, "manual-switch")
                self.assertEqual(app.views[-1].title, "branch-a-01")
                self.assertEqual(
                    [entry.label for entry in app.visible_entries],
                    ["Access Switch", "manual-switch", "switch-one"],
                )
                self.assertTrue(app.config.manual_path.is_file())

    async def test_selects_devices_and_opens_them_as_batch(self) -> None:
        first = Device("switch-one", "Access Switch", "192.0.2.1/24")
        second = Device("switch-two", "Access Switch", "192.0.2.2/24")
        branch = Node("branch-a-01", devices=[first, second])
        country = Node("Country A", children=[Node("City A", children=[branch])])
        app = self.make_app(
            tree_cache(
                "2026-08-02T00:00:00+02:00",
                [Node("Region Group A", children=[country])],
            )
        )
        with patch("netbox_ssh.tui.is_iterm2", return_value=True), patch(
            "netbox_ssh.tui.open_iterm_tabs"
        ) as open_tabs:
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "ctrl+t", "down", "ctrl+t")
                await pilot.pause()
                self.assertEqual(list(app.selected_devices.values()), [first, second])
                await pilot.press("enter")
                await pilot.pause()
                open_tabs.assert_called_once_with([first, second], None)
                self.assertEqual(app.selected_devices, {})

    async def test_toggles_and_persists_jump_host_for_device(self) -> None:
        device = Device(
            "switch-one", "Access Switch", "192.0.2.1/24", identifier="netbox:42"
        )
        branch = Node("branch-a-01", devices=[device])
        country = Node("Country A", children=[Node("City A", children=[branch])])
        with tempfile.TemporaryDirectory() as directory:
            app = self.make_app(
                tree_cache(
                    "2026-08-02T00:00:00+02:00",
                    [Node("Region Group A", children=[country])],
                ),
                Path(directory),
            )
            app.config = Config(
                **{
                    **app.config.__dict__,
                    "jump_host": "jump-alias",
                    "jump_state_path": Path(directory) / "jump.json",
                }
            )
            async with app.run_test() as pilot:
                await pilot.press("enter", "enter", "j")
                await pilot.pause()
                visible_device = next(
                    entry.value for entry in app.visible_entries if entry.kind == "device"
                )
                self.assertTrue(visible_device.use_jump_host)
                self.assertEqual(app.jump_devices, {"netbox:42"})
                self.assertTrue(app.config.jump_state_path.is_file())
                await pilot.press("j")
                await pilot.pause()
                self.assertFalse(visible_device.use_jump_host)
                self.assertEqual(app.jump_devices, set())

    async def test_clears_selected_devices(self) -> None:
        device = Device("switch-one", "Access Switch", "192.0.2.1/24")
        branch = Node("branch-a-01", devices=[device])
        country = Node("Country A", children=[Node("City A", children=[branch])])
        app = self.make_app(
            tree_cache(
                "2026-08-02T00:00:00+02:00",
                [Node("Region Group A", children=[country])],
            )
        )
        async with app.run_test() as pilot:
            # Space jest zapasowym skrótem zaznaczania na klawiaturach MacBooka.
            await pilot.press("enter", "enter", "space", "ctrl+u")
            await pilot.pause()
            self.assertEqual(app.selected_devices, {})

    def site_cache(self, with_regions=False):
        return Cache(
            "now",
            [{"id": 1, "name": "Europe", "parent_id": None}] if with_regions else [],
            [{"id": 2, "name": "Office", "region_id": None}],
            [{"identifier": "netbox:42", "site_id": 2, "name": "core-01",
              "role": "Core", "primary_ip": "10.0.0.1/32"}],
        )

    async def test_site_only_navigation_and_manual_form(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.make_app(self.site_cache(), Path(directory))
            async with app.run_test() as pilot:
                self.assertEqual(app.views[0].title, "Sites")
                await pilot.press("+")
                self.assertNotIsInstance(app.screen, AddDeviceScreen)
                await pilot.press("enter", "+")
                self.assertIsInstance(app.screen, AddDeviceScreen)
                await pilot.press(*list("manual-core"), "enter")
                await pilot.press(*list("10.0.0.2"), "enter", "enter")
                await pilot.pause()
                manual = load_manual_devices(app.config.manual_path)[0]
                self.assertEqual(manual.location_path, ("Office",))
                self.assertEqual(manual.region, "")
                self.assertEqual([e.label for e in app.visible_entries],
                                 ["Core", "core-01", "manual-core"])

    async def test_unassigned_site_form_does_not_save_synthetic_region(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.make_app(self.site_cache(with_regions=True), Path(directory))
            async with app.run_test() as pilot:
                self.assertEqual(app.views[0].title, "Locations")
                await pilot.press("enter", "+")
                self.assertIsInstance(app.screen, AddDeviceScreen)
                await pilot.press(*list("manual-core"), "enter")
                await pilot.press(*list("10.0.0.2"), "enter", "enter")
                await pilot.pause()
                self.assertEqual(app.manual_devices[0].region, "")
                self.assertEqual(app.manual_devices[0].branch, "Office")

    async def test_layout_reload_offline_preserves_jump_selections(self):
        cache = tree_cache("now", [Node("Europe", children=[Node("Poland", children=[
            Node("Office", devices=[Device("core", "Core", identifier="netbox:42")])
        ])])])
        app = self.make_app(cache)
        manual = ManualDevice("Europe", "Poland", "Office", "Office", "Core", "extra", "10.0.0.2")
        app.manual_devices = [manual]
        app.jump_devices = {"netbox:42", "manual:europe/poland/office/extra"}
        async with app.run_test() as pilot:
            changed = replace(app.config, tree_layout="sites")
            with patch("netbox_ssh.tui.ensure_config_file"), patch.object(app, "_edit_file", return_value=True), patch("netbox_ssh.tui.Config.from_env", return_value=changed):
                app.action_edit_config()
            await pilot.pause()
            self.assertEqual(app.views[0].title, "Sites")
            self.assertEqual([e.label for e in app.visible_entries], ["Office"])
            await pilot.press("enter")
            self.assertTrue(all(e.value.use_jump_host for e in app.visible_entries if e.kind == "device"))
            self.assertEqual(len([e for e in app.visible_entries if e.kind == "device"]), 2)

    async def test_region_layout_blocks_shallow_manual_creation(self):
        app = self.make_app(tree_cache("now", [Node("Europe", children=[
            Node("Poland", children=[Node("Office", devices=[Device("core", "Core")])])
        ])]))
        async with app.run_test() as pilot:
            await pilot.press("enter", "+")
            self.assertNotIsInstance(app.screen, AddDeviceScreen)
            await pilot.press("enter", "+")
            self.assertIsInstance(app.screen, AddDeviceScreen)

    async def test_sync_reports_visible_sites_and_omitted_devices(self):
        cache = self.site_cache()
        cache.devices.append({"identifier": "netbox:99", "site_id": None,
                              "name": "unplaced", "role": "Core", "primary_ip": None})
        app = self.make_app(None)
        async with app.run_test() as pilot:
            app._sync_finished(cache, 2)
            await pilot.pause()
            status = str(app.query_one("#status", Static).render())
            self.assertIn("1 devices, 1 sites", status)
            self.assertIn("1 devices without an available site omitted", status)
            self.assertEqual(app.views[0].title, "Sites")

    async def test_sync_reports_devices_without_selected_address(self):
        app = self.make_app(None)
        async with app.run_test() as pilot:
            app._sync_finished(self.site_cache(), 3)
            await pilot.pause()
            status = str(app.query_one("#status", Static).render())
            self.assertIn("1 devices, 1 sites", status)
            self.assertIn("2 devices without a selected address omitted", status)
            self.assertNotIn("without an available site", status)

    async def test_old_cache_refresh_keeps_manual_inventory_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.make_app(None, Path(directory))
            app.config.cache_path.write_text('{"version": 2, "regions": []}')
            app.manual_devices = [ManualDevice("", "", "", "Office", "Core", "extra", "10.0.0.2")]
            app.regions = app._merged_regions()
            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertIn("Cache needs refreshing", str(app.query_one("#status", Static).render()))
                self.assertEqual([e.label for e in app.visible_entries], ["Office"])


if __name__ == "__main__":
    unittest.main()
