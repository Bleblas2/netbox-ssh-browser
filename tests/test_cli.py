import unittest

from netbox_ssh.cli import filter_device_roles
from netbox_ssh.service import (
    filter_ignored_device_types,
    filter_ignored_manufacturers,
    filter_ignored_name_patterns,
)


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

    def test_missing_device_type_is_kept_when_filtering_manufacturers(self) -> None:
        devices = [
            {"name": "without-device-type", "device_type": None},
            {
                "name": "ignored-cisco-device",
                "device_type": {"manufacturer": {"name": "Cisco"}},
            },
        ]

        result = filter_ignored_manufacturers(devices, ("Cisco",))

        self.assertEqual(
            [device["name"] for device in result], ["without-device-type"]
        )


class GlobFilterTests(unittest.TestCase):
    def test_ignores_device_type_fields_case_insensitively(self) -> None:
        devices = [
            {"name": "one", "device_type": {"model": "MX67", "slug": "mx67"}},
            {"name": "two", "device_type": {"display": "ISR4451-X"}},
            {"name": "three", "device_type": {"model": "C9300"}},
            {"name": "unknown", "device_type": None},
        ]
        result = filter_ignored_device_types(devices, ("mx*", "ISR????-X"))
        self.assertEqual([item["name"] for item in result], ["three", "unknown"])

    def test_ignores_device_names_by_glob(self) -> None:
        devices = [
            {"name": "WAW-CORE"},
            {"name": "test-router"},
            {"name": "access-01"},
        ]
        result = filter_ignored_name_patterns(devices, ("*core", "TEST-*"))
        self.assertEqual([item["name"] for item in result], ["access-01"])


if __name__ == "__main__":
    unittest.main()
