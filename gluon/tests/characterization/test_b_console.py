"""
B10 - CLI option parsing: -t/--taskbar.

Source: gluon/console.py console (64-756), parse_args (818-981; ``os`` is
rebound as a loop variable at 867/880, making the ``os.name`` check at 854
refer to an unbound local).
Docs: docs/architecture/02-startup-and-bootstrap.md.
"""

import sys
import unittest

from gluon import console

from ._support import preserved_global_settings


class TestTaskbarOption(unittest.TestCase):
    """B10: web2py.py -t."""

    def run_console(self, *args):
        saved_argv = sys.argv
        sys.argv = ["web2py.py"] + list(args)
        try:
            with preserved_global_settings("cmd_options"):
                return console.console(version="test")
        finally:
            sys.argv = saved_argv

    def test_current_taskbar_option_raises_unboundlocalerror(self):
        """PINS-DEFECT: B10. 'os' is local to parse_args."""
        with self.assertRaises(UnboundLocalError):
            self.run_console("-t")

    def test_no_gui_option_parses(self):
        options = self.run_console("--no_gui")
        self.assertTrue(options.no_gui)


if __name__ == "__main__":
    unittest.main()
