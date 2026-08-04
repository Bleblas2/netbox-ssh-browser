import unittest
from unittest.mock import Mock, call

from netbox_ssh.netbox import NetBoxClient


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
