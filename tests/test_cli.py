import unittest

from netbox_ssh.cli import filter_device_roles
from netbox_ssh.service import filter_ignored_manufacturers


class RoleFilterTests(unittest.TestCase):
    def test_filters_role_names_case_insensitively(self) -> None:
        devices = [
            {"name": "one", "role": {"name": "Core Switch"}},
            {"name": "two", "role": {"name": "Server"}},
        ]
        result = filter_device_roles(devices, ("core switch",))
        self.assertEqual([item["name"] for item in result], ["one"])

    def test_empty_allowlist_means_all(self) -> None:
        devices = [{"name": "one", "role": {"name": "Server"}}]
        self.assertIs(filter_device_roles(devices, ()), devices)


class ManufacturerFilterTests(unittest.TestCase):
    def test_ignores_manufacturer_by_name_or_slug(self) -> None:
        devices = [
            {
                "name": "ignored-by-name",
                "device_type": {
                    "manufacturer": {"name": "Example Vendor", "slug": "example-vendor"}
                },
            },
            {
                "name": "ignored-by-slug",
                "device_type": {
                    "manufacturer": {"name": "Another Vendor", "slug": "another-vendor"}
                },
            },
            {"name": "kept", "device_type": {"manufacturer": {"name": "Cisco"}}},
        ]
        result = filter_ignored_manufacturers(
            devices, ("example vendor", "ANOTHER-VENDOR")
        )
        self.assertEqual([device["name"] for device in result], ["kept"])

    def test_empty_ignore_list_keeps_all(self) -> None:
        devices = [{"name": "one"}]
        self.assertIs(filter_ignored_manufacturers(devices, ()), devices)


if __name__ == "__main__":
    unittest.main()
