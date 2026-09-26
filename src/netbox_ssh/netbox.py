from __future__ import annotations

from typing import Any

import httpx


def _origin(url: httpx.URL) -> tuple[str, str, int | None]:
    # Jawne :443 i domyślny port HTTPS oznaczają ten sam serwer.
    port = url.port
    if port is None:
        port = {"http": 80, "https": 443}.get(url.scheme)
    return url.scheme, url.host, port


class NetBoxClient:
    """Minimalny klient REST API ograniczony do operacji odczytu potrzebnych nssh."""

    def __init__(self, url: str, token: str, verify_ssl: bool = True) -> None:
        # NetBox 4.5+ używa Bearer dla tokenów v2; starsze tokeny używają Token.
        scheme = "Bearer" if token.startswith("nbt_") else "Token"
        api_url = httpx.URL(f"{url.rstrip('/')}/api/")
        self._origin = _origin(api_url)
        self._client = httpx.Client(
            base_url=api_url,
            headers={"Authorization": f"{scheme} {token}", "Accept": "application/json"},
            timeout=30.0,
            verify=verify_ssl,
            follow_redirects=True,
            event_hooks={"request": [self._check_origin]},
        )

    def _check_origin(self, request: httpx.Request) -> None:
        # Sprawdzamy adres przed wysłaniem każdego żądania, także po przekierowaniu.
        # Pole next z odpowiedzi API nie może skierować tokenu do innego serwera
        # ani wymusić zmiany protokołu lub portu.
        if _origin(request.url) != self._origin:
            raise httpx.RequestError(
                "Refusing request outside the configured NetBox origin "
                "(scheme, host and port must match).",
                request=request,
            )

    def __enter__(self) -> "NetBoxClient":
        self._client.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self._client.__exit__(*args)

    def get_all(self, endpoint: str, **params: str | int) -> list[dict[str, Any]]:
        """Pobiera wszystkie strony wskazanego endpointu NetBoxa."""
        result: list[dict[str, Any]] = []
        url: str | httpx.URL | None = endpoint.lstrip("/")
        current_params: dict[str, str | int] | None = {"limit": 200, **params}
        while url:
            response = self._client.get(url, params=current_params)
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as error:
                raise httpx.RequestError(
                    "Invalid NetBox response: expected valid JSON",
                    request=response.request,
                ) from error
            if not isinstance(payload, dict):
                raise httpx.RequestError(
                    "Invalid NetBox response: expected a JSON object",
                    request=response.request,
                )
            page_results = payload.get("results")
            if not isinstance(page_results, list):
                raise httpx.RequestError(
                    "Invalid NetBox response: results must be a list",
                    request=response.request,
                )
            next_url = payload.get("next")
            if next_url is not None and not isinstance(next_url, str):
                raise httpx.RequestError(
                    "Invalid NetBox response: next must be text or null",
                    request=response.request,
                )
            result.extend(page_results)
            # Adres względny odnosimy do bieżącej strony, również gdy zawiera
            # tylko parametry, np. ?offset=200. Przed wysłaniem kolejnego żądania
            # funkcja _check_origin sprawdzi zgodność protokołu, hosta i portu.
            url = response.url.join(next_url) if next_url else None
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
