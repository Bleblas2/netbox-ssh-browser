import unittest
from unittest.mock import Mock, call, patch

import httpx

from netbox_ssh.netbox import NetBoxClient
from netbox_ssh.service import describe_sync_error


class PaginationOriginTests(unittest.TestCase):
    @staticmethod
    def make_client(handler, token: str = "fake-token") -> NetBoxClient:
        client_class = httpx.Client
        transport = httpx.MockTransport(handler)
        with patch(
            "netbox_ssh.netbox.httpx.Client",
            side_effect=lambda **kwargs: client_class(transport=transport, **kwargs),
        ):
            return NetBoxClient("https://netbox.example/netbox", token)

    def test_allows_same_origin_absolute_and_relative_next_links(self) -> None:
        next_links = (
            "https://NETBOX.example:443/netbox/api/dcim/devices/?limit=1&offset=1",
            "//netbox.example/netbox/api/dcim/devices/?limit=1&offset=1",
            "/netbox/api/dcim/devices/?limit=1&offset=1",
            "../devices/?limit=1&offset=1",
            "?limit=1&offset=1",
        )
        for token, auth in (("fake-token", "Token"), ("nbt_fake-token", "Bearer")):
            for next_link in next_links:
                with self.subTest(next_link=next_link, auth=auth):
                    requests = []

                    def handler(request: httpx.Request) -> httpx.Response:
                        requests.append(request)
                        if len(requests) == 1:
                            return httpx.Response(
                                200, json={"results": [{"id": 1}], "next": next_link}
                            )
                        return httpx.Response(200, json={"results": [{"id": 2}], "next": None})

                    with self.make_client(handler, token) as client:
                        result = client.get_all("dcim/devices/", limit=1, status="active")

                    self.assertEqual(result, [{"id": 1}, {"id": 2}])
                    self.assertEqual(len(requests), 2)
                    self.assertEqual(dict(requests[0].url.params), {"limit": "1", "status": "active"})
                    self.assertEqual(
                        str(requests[1].url),
                        "https://netbox.example/netbox/api/dcim/devices/?limit=1&offset=1",
                    )
                    for request in requests:
                        self.assertEqual(request.headers["Authorization"], f"{auth} {token}")

    def test_blocks_next_links_outside_configured_origin_before_sending(self) -> None:
        next_links = (
            "https://other.example/api/dcim/devices/",
            "//other.example/api/dcim/devices/",
            "https://netbox.example:444/api/dcim/devices/",
            "http://netbox.example/api/dcim/devices/",
            "https://netbox.example@other.example/api/dcim/devices/",
        )
        for next_link in next_links:
            with self.subTest(next_link=next_link):
                requests = []

                def handler(request: httpx.Request) -> httpx.Response:
                    requests.append(request)
                    return httpx.Response(
                        200, json={"results": [{"id": 1}], "next": next_link}
                    )

                with self.make_client(handler) as client:
                    with self.assertRaisesRegex(httpx.RequestError, "configured NetBox origin"):
                        client.get_all("dcim/devices/")
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0].url.host, "netbox.example")

    def test_follows_same_origin_redirect_and_resolves_next_from_final_url(self) -> None:
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(302, headers={"Location": "../inventory/"})
            if len(requests) == 2:
                return httpx.Response(200, json={"results": [{"id": 1}], "next": "?offset=1"})
            return httpx.Response(200, json={"results": [{"id": 2}], "next": None})

        with self.make_client(handler) as client:
            self.assertEqual(client.get_all("dcim/devices/"), [{"id": 1}, {"id": 2}])
        self.assertEqual(len(requests), 3)
        self.assertEqual(str(requests[2].url), "https://netbox.example/netbox/api/dcim/inventory/?offset=1")
        for request in requests:
            self.assertEqual(request.headers["Authorization"], "Token fake-token")

    def test_blocks_redirects_outside_configured_origin_for_inventory_and_status(self) -> None:
        locations = (
            "https://other.example/api/",
            "https://netbox.example:444/api/",
            "http://netbox.example/api/",
        )
        for operation in ("inventory", "status"):
            for location in locations:
                with self.subTest(operation=operation, location=location):
                    requests = []

                    def handler(request: httpx.Request) -> httpx.Response:
                        requests.append(request)
                        return httpx.Response(302, headers={"Location": location})

                    with self.make_client(handler) as client:
                        with self.assertRaisesRegex(httpx.RequestError, "configured NetBox origin"):
                            if operation == "status":
                                client.check_status()
                            else:
                                client.get_all("dcim/devices/")
                    self.assertEqual(len(requests), 1)

    def test_rejects_malformed_pagination_payloads_before_following_next(self):
        cases = (
            ([], "expected a JSON object"),
            ({}, "results must be a list"),
            ({"results": {}}, "results must be a list"),
            ({"results": [], "next": 123}, "next must be text or null"),
            ({"results": [], "next": {"url": "evil"}}, "next must be text or null"),
        )
        for payload, message in cases:
            with self.subTest(payload=payload):
                requests = []
                def handler(request):
                    requests.append(request)
                    return httpx.Response(200, json=payload)
                with self.make_client(handler) as client:
                    with self.assertRaisesRegex(httpx.RequestError, message) as error:
                        client.get_all("dcim/devices/")
                self.assertEqual(len(requests), 1)
                self.assertNotIn("Configuration error", describe_sync_error(error.exception))

    def test_rejects_invalid_json_as_a_netbox_response_error(self):
        with self.make_client(lambda request: httpx.Response(200, content=b"not json")) as client:
            with self.assertRaisesRegex(httpx.RequestError, "expected valid JSON"):
                client.get_all("dcim/devices/")

    def test_accepts_empty_results_and_null_next(self):
        with self.make_client(lambda request: httpx.Response(
            200, json={"results": [], "next": None}
        )) as client:
            self.assertEqual(client.get_all("dcim/devices/"), [])


class InventoryFilterTests(unittest.TestCase):
    def make_client(self) -> NetBoxClient:
        client = NetBoxClient.__new__(NetBoxClient)
        client.get_all = Mock(side_effect=self.fake_get_all)  # type: ignore[method-assign]
        return client

    @staticmethod
    def fake_get_all(endpoint: str, **params: str) -> list[dict]:
        if endpoint != "dcim/devices/":
            return []
        status = params.get("status")
        if status == "active":
            return [{"id": 1, "name": "active-device"}]
        if status == "planned":
            return [
                {"id": 1, "name": "active-device"},
                {"id": 2, "name": "planned-device"},
            ]
        return [{"id": 3, "name": "all-statuses-device"}]

    def test_fetches_only_configured_statuses_and_deduplicates(self) -> None:
        client = self.make_client()
        _, _, devices = client.fetch_inventory(("active", "planned"))
        self.assertEqual([device["id"] for device in devices], [1, 2])
        self.assertEqual(
            client.get_all.call_args_list,
            [
                call("dcim/regions/"),
                call("dcim/sites/"),
                call("dcim/devices/", status="active"),
                call("dcim/devices/", status="planned"),
            ],
        )

    def test_empty_status_list_fetches_all_devices(self) -> None:
        client = self.make_client()
        _, _, devices = client.fetch_inventory(())
        self.assertEqual([device["id"] for device in devices], [3])
        client.get_all.assert_called_with("dcim/devices/")


if __name__ == "__main__":
    unittest.main()
