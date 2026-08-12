import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import ListView

from netbox_ssh.cache import Cache
from netbox_ssh.config import Config
from netbox_ssh.model import Device, Node
from netbox_ssh.tui import NetBoxSSHApp


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
        app = self.make_app(Cache("2026-08-02T00:00:00+02:00", [region]))
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
            Cache(
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
                Cache("2026-08-02T00:00:00+02:00", [region]), Path(directory)
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
            Cache(
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
                Cache(
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
            Cache(
                "2026-08-02T00:00:00+02:00",
                [Node("Region Group A", children=[country])],
            )
        )
        async with app.run_test() as pilot:
            # Space jest zapasowym skrótem zaznaczania na klawiaturach MacBooka.
            await pilot.press("enter", "enter", "space", "ctrl+u")
            await pilot.pause()
            self.assertEqual(app.selected_devices, {})


if __name__ == "__main__":
    unittest.main()
