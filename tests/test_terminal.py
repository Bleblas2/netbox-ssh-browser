import os
import unittest
from unittest.mock import patch

from netbox_ssh.model import Device
from netbox_ssh.terminal import ITERM_TABS_SCRIPT, open_iterm_tabs


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

    @patch("netbox_ssh.terminal.is_iterm2", return_value=False)
    def test_rejects_batch_outside_iterm2(self, _is_iterm2) -> None:
        with self.assertRaisesRegex(RuntimeError, "requires iTerm2"):
            open_iterm_tabs([Device("switch-one", "Core")])


if __name__ == "__main__":
    unittest.main()
