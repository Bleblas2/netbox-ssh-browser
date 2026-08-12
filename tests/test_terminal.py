import os
import unittest
from unittest.mock import patch

from netbox_ssh.model import Device
from netbox_ssh.terminal import ITERM_TABS_SCRIPT, open_iterm_tabs, run_system_ssh


class ITermTabsTests(unittest.TestCase):
    def test_converts_applescript_argv_reference_to_text(self) -> None:
        self.assertIn("command_text as text", ITERM_TABS_SCRIPT)
        self.assertNotIn("contents of command_text", ITERM_TABS_SCRIPT)

    @patch("netbox_ssh.terminal.subprocess.run")
    @patch("netbox_ssh.terminal.is_iterm2", return_value=True)
    def test_opens_quoted_ssh_commands_without_secrets(self, _is_iterm2, run) -> None:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        devices = [
            Device("switch-one", "Core", "192.0.2.1/24"),
            Device("odd name", "Core", None),
        ]
        with patch.dict(
            os.environ,
            {"NETBOX_API_TOKEN": "secret", "NETBOX_URL": "https://netbox.example"},
        ):
            open_iterm_tabs(devices)

        arguments = run.call_args.args[0]
        self.assertEqual(arguments[-2:], ["ssh 192.0.2.1", "ssh 'odd name'"])
        self.assertNotIn("NETBOX_API_TOKEN", run.call_args.kwargs["env"])
        self.assertNotIn("NETBOX_URL", run.call_args.kwargs["env"])
        self.assertFalse(run.call_args.kwargs["check"])

    @patch("netbox_ssh.terminal.subprocess.run")
    @patch("netbox_ssh.terminal.is_iterm2", return_value=True)
    def test_opens_nested_ssh_command_in_iterm(self, _is_iterm2, run) -> None:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        device = Device("switch-one", "Core", "192.0.2.1", use_jump_host=True)
        open_iterm_tabs([device], "jump-alias")
        self.assertEqual(
            run.call_args.args[0][-1], "ssh -tt jump-alias 'ssh 192.0.2.1'"
        )

    @patch("netbox_ssh.terminal.is_iterm2", return_value=False)
    def test_rejects_batch_outside_iterm2(self, _is_iterm2) -> None:
        with self.assertRaisesRegex(RuntimeError, "requires iTerm2"):
            open_iterm_tabs([Device("switch-one", "Core")])


class SystemSSHTests(unittest.TestCase):
    @patch("netbox_ssh.terminal.subprocess.run")
    def test_runs_single_device_without_secrets(self, run) -> None:
        run.return_value.returncode = 0
        device = Device("switch-one", "Core", "192.0.2.1/24")
        with patch.dict(
            os.environ,
            {"NETBOX_API_TOKEN": "secret", "NETBOX_URL": "https://netbox.example"},
        ):
            results = run_system_ssh([device])

        self.assertEqual(run.call_args.args[0], ["ssh", "192.0.2.1"])
        self.assertEqual(results, [(device, 0)])
        self.assertNotIn("NETBOX_API_TOKEN", run.call_args.kwargs["env"])
        self.assertNotIn("NETBOX_URL", run.call_args.kwargs["env"])

    @patch("netbox_ssh.terminal.subprocess.run")
    def test_runs_marked_device_through_jump_host(self, run) -> None:
        run.return_value.returncode = 0
        device = Device("switch-one", "Core", "192.0.2.1", use_jump_host=True)
        run_system_ssh([device], "jump-alias")
        self.assertEqual(
            run.call_args.args[0],
            ["ssh", "-tt", "jump-alias", "ssh 192.0.2.1"],
        )

    def test_rejects_marked_device_without_configured_jump_host(self) -> None:
        device = Device("switch-one", "Core", use_jump_host=True)
        with self.assertRaisesRegex(ValueError, "No SSH jump host"):
            run_system_ssh([device])


if __name__ == "__main__":
    unittest.main()
