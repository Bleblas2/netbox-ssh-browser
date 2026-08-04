from __future__ import annotations

from typing import Any

import httpx


class NetBoxClient:
    """Minimalny klient REST API ograniczony do operacji odczytu potrzebnych nssh."""

    def __init__(self, url: str, token: str, verify_ssl: bool = True) -> None:
        # NetBox 4.5+ używa Bearer dla tokenów v2; starsze tokeny używają Token.
        scheme = "Bearer" if token.startswith("nbt_") else "Token"
        self._client = httpx.Client(
            base_url=f"{url.rstrip('/')}/api/",
            headers={"Authorization": f"{scheme} {token}", "Accept": "application/json"},
            timeout=30.0,
            verify=verify_ssl,
            follow_redirects=True,
        )

    def __enter__(self) -> "NetBoxClient":
        self._client.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self._client.__exit__(*args)

    def get_all(self, endpoint: str, **params: str | int) -> list[dict[str, Any]]:
        """Pobiera wszystkie strony wskazanego endpointu NetBoxa."""
        result: list[dict[str, Any]] = []
        url: str | None = endpoint.lstrip("/")
        current_params: dict[str, str | int] | None = {"limit": 200, **params}
        while url:
            # Pole next może być pełnym URL-em; httpx obsługuje zarówno pełne,
            # jak i względne adresy kolejnych stron.
            response = self._client.get(url, params=current_params)
            response.raise_for_status()
            payload = response.json()
            result.extend(payload.get("results", []))
            url = payload.get("next")
            current_params = None
        return result

    def check_status(self) -> dict[str, Any]:
        """Oddziela problem z łącznością API od uprawnień do obiektów DCIM."""
        response = self._client.get("status/")
        response.raise_for_status()
        return response.json()

    def fetch_inventory(
        self, device_statuses: tuple[str, ...] = ()
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Pobiera regiony, oddziały i urządzenia dla jednej synchronizacji."""
        regions = self.get_all("dcim/regions/")
        sites = self.get_all("dcim/sites/")
        if device_statuses:
            # API filtruje pojedynczy status. Dla wielu statusów odpytujemy je
            # osobno, a słownik po ID usuwa ewentualne duplikaty.
            devices_by_id: dict[int, dict[str, Any]] = {}
            devices_without_id: list[dict[str, Any]] = []
            for status in device_statuses:
                for device in self.get_all("dcim/devices/", status=status):
                    device_id = device.get("id")
                    if isinstance(device_id, int):
                        devices_by_id[device_id] = device
                    else:
                        devices_without_id.append(device)
            devices = [*devices_by_id.values(), *devices_without_id]
        else:
            devices = self.get_all("dcim/devices/")
        return regions, sites, devices
