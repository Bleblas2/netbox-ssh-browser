import contextlib
import io
import unittest

from netbox_ssh import __version__
from netbox_ssh.cli import main


class EntrypointTests(unittest.TestCase):
    def test_version_does_not_start_tui(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exit_result:
            main(["--version"])
        self.assertEqual(exit_result.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"nssh {__version__}")


if __name__ == "__main__":
    unittest.main()
