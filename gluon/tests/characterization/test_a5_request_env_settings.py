"""
A5 - Request.__init__ copies global_settings into request.env.

Source: gluon/globals.py Request.__init__ (lines 313-317);
gluon/settings.py (commented trusted_lan_prefix example, line 51);
consumers: applications/admin/models/access.py:25-26,
applications/*/controllers/appadmin.py:24-28.
Docs: docs/architecture/11-security-boundaries.md,
docs/architecture/02-startup-and-bootstrap.md.
"""

import unittest

from gluon.globals import Request
from gluon.settings import global_settings

from ._support import preserved_global_settings


class TestRequestEnvIncludesGlobalSettings(unittest.TestCase):
    """A5: global_settings keys are visible through request.env."""

    def test_trusted_lan_prefix_reaches_request_env(self):
        with preserved_global_settings("trusted_lan_prefix"):
            global_settings.trusted_lan_prefix = "192.168.0."
            request = Request(env={})
        self.assertEqual(request.env.trusted_lan_prefix, "192.168.0.")

    def test_trusted_lan_prefix_absent_by_default(self):
        with preserved_global_settings("trusted_lan_prefix"):
            global_settings.pop("trusted_lan_prefix", None)
            request = Request(env={})
        self.assertIsNone(request.env.trusted_lan_prefix)

    def test_global_settings_override_wsgi_environ_keys(self):
        """global_settings is applied after the environ, so it wins."""
        with preserved_global_settings("trusted_lan_prefix"):
            global_settings.trusted_lan_prefix = "10."
            request = Request(env={"trusted_lan_prefix": "172.16."})
        self.assertEqual(request.env.trusted_lan_prefix, "10.")

    def test_web2py_path_is_applications_parent(self):
        request = Request(env={})
        self.assertEqual(request.env.web2py_path, global_settings.applications_parent)

    def test_environ_keys_are_kept_verbatim(self):
        request = Request(env={"HTTP_X_TEST": "1"})
        self.assertEqual(request.env.HTTP_X_TEST, "1")
        self.assertIsNone(request.env.http_x_test)


if __name__ == "__main__":
    unittest.main()
