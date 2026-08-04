from __future__ import annotations

import os
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Static

from .cache import Cache
from .config import Config
from .editor import editor_command, ensure_config_file, ensure_manual_file
from .manual import (
    ManualDevice,
    load_manual_devices,
    save_manual_devices,
    validate_manual_target,
)
from .model import Device, Node
from .service import describe_sync_error, synchronize
from .terminal import open_iterm_tabs


@dataclass(frozen=True)
class Entry:
    """Jeden wiersz widoku: nagłówek grupy albo aktywna pozycja."""

    kind: str
    label: str
    value: Any = None
    detail: str = ""
    path: tuple[str, ...] = ()


@dataclass
class View:
    """Stan pojedynczego poziomu na stosie nawigacji."""

    title: str
    node: Node | None = None
    role_devices: list[Device] | None = None
    search_entries: list[Entry] | None = None
    path: tuple[str, ...] = ()


class AddDeviceScreen(ModalScreen[ManualDevice | None]):
    """Modalny formularz dodawania urządzenia do aktualnego oddziału."""

    CSS = """
    AddDeviceScreen { align: center middle; background: $background 70%; }
    #manual-dialog { width: 68; height: auto; padding: 1 2; border: round $primary; background: $surface; }
    #manual-dialog Input { margin-bottom: 1; }
    #manual-title { text-style: bold; margin-bottom: 1; }
    #manual-location { color: $text-muted; margin-bottom: 1; }
    #manual-error { color: $error; height: 2; }
    #manual-buttons { height: 3; align-horizontal: right; }
    #manual-buttons Button { margin-left: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, path: tuple[str, ...], roles: list[str]) -> None:
        super().__init__()
        self.location_path = path
        self.default_role = roles[0] if roles else "Manual"

    def compose(self) -> ComposeResult:
        with Vertical(id="manual-dialog"):
            yield Static("Add manual device", id="manual-title")
            yield Static(" / ".join(self.location_path), id="manual-location")
            yield Input(placeholder="Device name", id="manual-name")
            yield Input(placeholder="IP address or hostname", id="manual-target")
            yield Input(value=self.default_role, placeholder="Device Role", id="manual-role")
            yield Static("", id="manual-error")
            with Horizontal(id="manual-buttons"):
                yield Button("Cancel", id="manual-cancel")
                yield Button("Save", id="manual-save", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#manual-name", Input).focus()

    @on(Input.Submitted)
    def _submitted(self, event: Input.Submitted) -> None:
        order = ["manual-name", "manual-target", "manual-role"]
        current = order.index(event.input.id or "manual-name")
        if current < len(order) - 1:
            self.query_one(f"#{order[current + 1]}", Input).focus()
        else:
            self._save()

    @on(Button.Pressed)
    def _button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "manual-save":
            self._save()
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        name = self.query_one("#manual-name", Input).value.strip()
        target = self.query_one("#manual-target", Input).value.strip()
        role = self.query_one("#manual-role", Input).value.strip()
        if not name or not role:
            self.query_one("#manual-error", Static).update("Name and Device Role are required.")
            return
        try:
            validate_manual_target(target)
        except ValueError as error:
            self.query_one("#manual-error", Static).update(str(error))
            return
        region, country = self.location_path[:2]
        city = self.location_path[-2] if len(self.location_path) >= 4 else self.location_path[-1]
        branch = self.location_path[-1]
        self.dismiss(ManualDevice(region, country, city, branch, role, name, target))


class NetBoxSSHApp(App[None]):
    """Pełnoekranowa aplikacja terminalowa zarządzająca menu, syncem i SSH."""

    TITLE = "NetBox SSH Browser"
    SUB_TITLE = "Device browser"
    CSS = """
    Screen { background: $surface; }
    #content { margin: 1 2; height: 1fr; }
    #breadcrumb { height: 3; padding: 1 2; background: $boost; text-style: bold; }
    #search { margin: 0 1 1 1; display: none; }
    #search.visible { display: block; }
    #device-list { height: 1fr; border: round $primary; }
    ListItem { padding: 0 2; }
    ListItem.--highlight { background: $accent 35%; text-style: bold; }
    ListItem.city-heading { color: $primary; text-style: bold; padding-top: 1; }
    .entry-detail { color: $text-muted; }
    #status { height: 3; padding: 1 2; background: $boost; color: $text-muted; }
    #status.error { color: $error; }
    #status.success { color: $success; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "back", "Back"),
        Binding("s", "sync", "Sync from NetBox"),
        Binding("slash", "search", "Device search"),
        Binding("plus", "add_device", "Add manual device"),
        Binding("c", "edit_config", "Edit config"),
        Binding("m", "edit_manual", "Edit manual"),
        Binding("ctrl+t", "toggle_selection", "Select device"),
        Binding("space", "toggle_selection", "Select device", show=False),
        Binding("ctrl+u", "clear_selection", "Clear selection"),
    ]

    def __init__(
        self,
        config: Config,
        cache: Cache | None,
        manual_devices: list[ManualDevice] | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.cache = cache
        self.manual_devices = list(manual_devices or [])
        self.regions = self._merged_regions()
        self.views: list[View] = [View("Countries", path=())]
        self.visible_entries: list[Entry] = []
        self.item_entries: dict[int, Entry] = {}
        self.syncing = False
        # Obiekty Device są współdzielone między drzewem i wynikami wyszukiwania,
        # więc ich id pozwala zachować zaznaczenie podczas nawigacji.
        self.selected_devices: dict[int, Device] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="content"):
            yield Static(id="breadcrumb")
            yield Input(placeholder="Search devices by name or IP…", id="search")
            yield ListView(id="device-list")
            yield Static(id="status")
        yield Footer()

    async def on_mount(self) -> None:
        await self._render_entries()
        self.query_one(ListView).focus()
        if self.cache is None:
            self._set_status("No local data. Press S to sync with NetBox.")
        else:
            self._set_status(f"Last sync: {self.cache.synced_at}")

    def _entries_for_view(self) -> list[Entry]:
        """Buduje wiersze odpowiednie dla aktualnego poziomu nawigacji."""
        view = self.views[-1]
        if view.search_entries is not None:
            return view.search_entries
        if view.role_devices is not None:
            return [
                Entry("device", device.name, device, device.ssh_target)
                for device in view.role_devices
            ]
        if view.node is not None:
            if len(self.views) == 2:
                return self._country_entries(view.node)
            return self._location_entries(view.node)
        return self._region_entries()

    def _region_entries(self) -> list[Entry]:
        entries: list[Entry] = []
        for region in self.regions:
            # Region jest nagłówkiem, a kraje linkami, co usuwa jedno kliknięcie.
            entries.append(Entry("heading", region.name, detail="Region"))
            if region.devices:
                entries.append(Entry("node", region.name, region, "Country", (region.name,)))
            entries.extend(
                Entry("node", country.name, country, "Country", (region.name, country.name))
                for country in region.children
            )
        return entries

    def _country_entries(self, country: Node) -> list[Entry]:
        entries: list[Entry] = []
        country_path = self.views[-1].path
        for city in country.children:
            # Analogicznie miasto grupuje wybieralne oddziały.
            entries.append(Entry("heading", city.name, detail="City"))
            if city.devices:
                entries.append(Entry("node", city.name, city, "Branch", (*country_path, city.name)))
            entries.extend(
                Entry("node", branch.name, branch, "Branch", (*country_path, city.name, branch.name))
                for branch in city.children
            )
        if country.devices:
            roles: dict[str, list[Device]] = defaultdict(list)
            for device in country.devices:
                roles[device.role].append(device)
            entries.extend(
                Entry("role", role, devices, f"{len(devices)} devices")
                for role, devices in sorted(roles.items(), key=lambda item: item[0].casefold())
            )
        return entries

    def _location_entries(self, location: Node) -> list[Entry]:
        current_path = self.views[-1].path
        entries = [
            Entry("node", child.name, child, "Location", (*current_path, child.name))
            for child in location.children
        ]
        roles: dict[str, list[Device]] = defaultdict(list)
        for device in location.devices:
            roles[device.role].append(device)
        for role, devices in sorted(roles.items(), key=lambda item: item[0].casefold()):
            # Rola jest tylko nagłówkiem; Enter na urządzeniu od razu uruchamia SSH.
            entries.append(Entry("heading", role, detail="Device Role"))
            entries.extend(
                Entry(
                    "device",
                    device.name,
                    device,
                    f"{device.ssh_target}{'    manual' if device.source == 'manual' else ''}",
                )
                for device in devices
            )
        return entries

    async def _render_entries(self) -> None:
        """Odświeża listę w miejscu, bez dopisywania kolejnych linii terminala."""
        search = self.query_one("#search", Input).value.casefold().strip()
        entries = self._entries_for_view()
        self.visible_entries = [
            entry
            for entry in entries
            if not search
            or search in entry.label.casefold()
            or search in entry.detail.casefold()
        ]
        list_view = self.query_one(ListView)
        await list_view.clear()
        self.item_entries.clear()
        items = []
        icons = {"heading": "", "node": "↳", "role": "◆", "device": "●"}
        for entry in self.visible_entries:
            line = Text()
            if entry.kind == "device" and id(entry.value) in self.selected_devices:
                icon = "✓"
            else:
                icon = "◇" if entry.kind == "device" and entry.value.source == "manual" else icons.get(entry.kind, " ")
            line.append(f"{icon}  {entry.label}")
            if entry.detail:
                line.append(f"    {entry.detail}", style="dim")
            item = ListItem(
                Label(line),
                classes="city-heading" if entry.kind == "heading" else None,
                disabled=entry.kind == "heading",
            )
            self.item_entries[id(item)] = entry
            items.append(item)
        if items:
            await list_view.extend(items)
            # Nagłówki są disabled, ale jawnie ustawiamy zaznaczenie na pierwszym
            # aktywnym elemencie, aby Enter działał bez wciskania strzałki.
            list_view.index = next(
                (
                    index
                    for index, entry in enumerate(self.visible_entries)
                    if entry.kind != "heading"
                ),
                None,
            )
        self.query_one("#breadcrumb", Static).update(" / ".join(view.title for view in self.views))

    @on(Input.Changed, "#search")
    async def _filter_changed(self) -> None:
        await self._render_entries()

    @on(Input.Submitted, "#search")
    def _filter_submitted(self) -> None:
        self.query_one(Input).remove_class("visible")
        self.query_one(ListView).focus()

    @on(ListView.Selected)
    async def _selected(self, event: ListView.Selected) -> None:
        # Tylko aktywne wpisy docierają do tego handlera; nagłówki są disabled.
        entry = self.item_entries.get(id(event.item))
        if entry is None:
            return
        if entry.kind == "node":
            self.views.append(View(entry.label, node=entry.value, path=entry.path))
            await self._reset_and_render()
        elif entry.kind == "role":
            self.views.append(View(entry.label, role_devices=entry.value))
            await self._reset_and_render()
        elif entry.kind == "device":
            if self.selected_devices:
                self._connect_selected()
            else:
                self._connect_ssh(entry.value)

    async def action_toggle_selection(self) -> None:
        """Zaznacza bieżące urządzenie klawiszem Ctrl+T lub Space."""
        list_view = self.query_one(ListView)
        if list_view.index is None or list_view.index >= len(self.visible_entries):
            return
        entry = self.visible_entries[list_view.index]
        if entry.kind != "device":
            self._set_status("Only devices can be selected.", "error")
            return
        device_id = id(entry.value)
        if device_id in self.selected_devices:
            self.selected_devices.pop(device_id)
        else:
            self.selected_devices[device_id] = entry.value
        current_index = list_view.index
        await self._render_entries()
        list_view.index = current_index
        self._set_status(f"Selected devices: {len(self.selected_devices)}.")

    async def action_clear_selection(self) -> None:
        """Usuwa wszystkie zaznaczenia bez zmiany bieżącego widoku."""
        if not self.selected_devices:
            self._set_status("No devices are selected.")
            return
        list_view = self.query_one(ListView)
        current_index = list_view.index
        self.selected_devices.clear()
        await self._render_entries()
        list_view.index = current_index
        self._set_status("Device selection cleared.")

    def _connect_selected(self) -> None:
        """Przekazuje zaznaczone urządzenia do integracji z kartami iTerm2."""
        devices = list(self.selected_devices.values())
        try:
            open_iterm_tabs(devices)
        except (OSError, RuntimeError) as error:
            self._set_status(f"Could not open iTerm2 tabs: {error}", "error")
            return
        self.selected_devices.clear()
        self.run_worker(self._render_entries(), exclusive=True)
        self._set_status(f"Opened {len(devices)} SSH sessions in iTerm2 tabs.", "success")

    async def _reset_and_render(self) -> None:
        search = self.query_one(Input)
        search.value = ""
        search.remove_class("visible")
        await self._render_entries()
        self.query_one(ListView).focus()

    async def action_back(self) -> None:
        # Escape najpierw zamyka wyszukiwanie, a dopiero potem cofa poziom drzewa.
        search = self.query_one(Input)
        if search.has_focus or search.value:
            search.value = ""
            search.remove_class("visible")
            await self._render_entries()
            self.query_one(ListView).focus()
        elif len(self.views) > 1:
            self.views.pop()
            await self._render_entries()

    async def action_search(self) -> None:
        # Wyszukiwanie jest globalne, dlatego działa niezależnie od bieżącego oddziału.
        if not self.regions:
            self._set_status("No local data to search. Run Sync with NetBox first.", "error")
            return
        if self.views[-1].search_entries is None:
            self.views.append(View("Device search", search_entries=self._global_device_entries()))
        search = self.query_one(Input)
        search.value = ""
        search.add_class("visible")
        await self._render_entries()
        search.focus()

    def _global_device_entries(self) -> list[Entry]:
        """Spłaszcza urządzenia z całego drzewa dla wyszukiwania po nazwie/IP."""
        entries: list[Entry] = []

        def visit(node: Node, path: list[str]) -> None:
            # Pełna ścieżka w detail podpowiada, gdzie znajduje się wynik.
            for device in node.devices:
                location = " / ".join(path)
                source = "    manual" if device.source == "manual" else ""
                detail = f"{device.ssh_target}    {location} / {device.role}{source}"
                entries.append(Entry("device", device.name, device, detail))
            for child in node.children:
                visit(child, [*path, child.name])

        for region in self.regions:
            visit(region, [region.name])
        return sorted(entries, key=lambda entry: entry.label.casefold())

    def action_sync(self) -> None:
        # exclusive zapobiega równoległym synchronizacjom i wyścigom przy zapisie cache.
        if self.syncing:
            self._set_status("Sync is already running.")
            return
        self.syncing = True
        ssl_status = "enabled" if self.config.verify_ssl else "disabled"
        self._set_status(f"Connecting to NetBox… SSL verification: {ssl_status}")
        self.run_worker(self._sync_worker, thread=True, exclusive=True, exit_on_error=False)

    def action_add_device(self) -> None:
        """Otwiera formularz tylko w kontekście konkretnego oddziału."""
        view = self.views[-1]
        if view.node is None or len(view.path) < 3:
            self._set_status("Navigate to a branch before adding a manual device.", "error")
            return
        roles = sorted({device.role for device in view.node.devices}, key=str.casefold)
        self.push_screen(AddDeviceScreen(view.path, roles), self._manual_device_added)

    def action_edit_config(self) -> None:
        """Otwiera aktywny config.toml i wczytuje ustawienia po zamknięciu edytora."""
        try:
            ensure_config_file(self.config.config_path)
            if not self._edit_file(self.config.config_path):
                return
            self.config = Config.from_env()
        except (OSError, ValueError) as error:
            self._set_status(f"Could not reload configuration: {error}", "error")
            return
        self._set_status(f"Configuration reloaded from {self.config.config_path}.", "success")

    def action_edit_manual(self) -> None:
        """Otwiera manual.json i natychmiast odświeża ręczne urządzenia."""
        try:
            ensure_manual_file(self.config.manual_path)
            if not self._edit_file(self.config.manual_path):
                return
            manual_devices = load_manual_devices(self.config.manual_path)
        except (OSError, ValueError) as error:
            self._set_status(f"Could not reload manual inventory: {error}", "error")
            return
        self.manual_devices = manual_devices
        self.regions = self._merged_regions()
        self.views = [View("Countries", path=())]
        self.selected_devices.clear()
        self.run_worker(self._reset_and_render(), exclusive=True)
        self._set_status(
            f"Manual inventory reloaded: {len(manual_devices)} devices.", "success"
        )

    def _edit_file(self, path: Any) -> bool:
        """Oddaje terminal edytorowi bez przekazywania sekretów NetBoxa."""
        environment = os.environ.copy()
        environment.pop("NETBOX_API_TOKEN", None)
        environment.pop("NETBOX_URL", None)
        try:
            with self.suspend():
                result = subprocess.run(
                    [*editor_command(), str(path)], check=False, env=environment
                )
        except OSError as error:
            self._set_status(f"Could not start editor: {error}", "error")
            return False
        if result.returncode != 0:
            self._set_status(
                f"Editor exited with status {result.returncode}; file was not reloaded.",
                "error",
            )
            return False
        return True

    def _manual_device_added(self, manual: ManualDevice | None) -> None:
        if manual is None:
            return
        duplicate = any(
            item.location_path == manual.location_path
            and item.name.casefold() == manual.name.casefold()
            for item in self.manual_devices
        )
        if duplicate:
            self._set_status(f"Manual device {manual.name} already exists in this branch.", "error")
            return
        self.manual_devices.append(manual)
        try:
            save_manual_devices(self.config.manual_path, self.manual_devices)
        except OSError as error:
            self.manual_devices.pop()
            self._set_status(f"Could not save manual inventory: {error}", "error")
            return
        # Aktualny View wskazuje węzeł z self.regions, więc możemy dopisać wpis
        # bez przebudowy drzewa i pozostawić użytkownika w tym samym oddziale.
        current_node = self.views[-1].node
        assert current_node is not None
        current_node.devices.append(
            Device(manual.name, manual.role, manual.target, source="manual")
        )
        current_node.devices.sort(
            key=lambda device: (device.role.casefold(), device.name.casefold())
        )
        self.run_worker(self._render_entries(), exclusive=True)
        self._set_status(f"Manual device {manual.name} saved.", "success")

    def _sync_worker(self) -> None:
        # Operacje sieciowe wykonujemy w wątku, aby interfejs nie zamarzał.
        try:
            cache, device_count = synchronize(self.config)
        except Exception as error:
            self.call_from_thread(self._sync_failed, describe_sync_error(error))
        else:
            self.call_from_thread(self._sync_finished, cache, device_count)

    def _sync_failed(self, message: str) -> None:
        self.syncing = False
        self._set_status(message, "error")
        self.notify(message, title="Sync failed", severity="error", timeout=8)

    def _sync_finished(self, cache: Cache, device_count: int) -> None:
        self.syncing = False
        self.cache = cache
        self.regions = self._merged_regions()
        self.views = [View("Countries", path=())]
        self.run_worker(self._reset_and_render(), exclusive=True)
        country_count = sum(len(region.children) for region in cache.regions)
        message = f"Sync complete: {device_count} devices, {country_count} countries."
        self._set_status(message, "success")
        self.notify(message, title="NetBox")

    def _merged_regions(self) -> list[Node]:
        from .manual import merge_manual_devices

        return merge_manual_devices(
            self.cache.regions if self.cache else [], self.manual_devices
        )

    def _connect_ssh(self, device: Device) -> None:
        environment = os.environ.copy()
        # Proces SSH nie potrzebuje sekretów NetBoxa i nie powinien ich dziedziczyć.
        environment.pop("NETBOX_API_TOKEN", None)
        environment.pop("NETBOX_URL", None)
        self._set_status(f"Connecting to {device.name} ({device.ssh_target})…")
        try:
            # Na czas SSH oddajemy terminal klientowi systemowemu, a po jego
            # zakończeniu Textual odtwarza poprzedni ekran.
            with self.suspend():
                subprocess.run(["ssh", device.ssh_target], check=False, env=environment)
        except OSError as error:
            self._set_status(f"Could not start ssh: {error}", "error")
        else:
            self._set_status(f"SSH session with {device.name} ended.")

    def _set_status(self, message: str, style_class: str | None = None) -> None:
        status = self.query_one("#status", Static)
        status.remove_class("error", "success")
        if style_class:
            status.add_class(style_class)
        status.update(message)
