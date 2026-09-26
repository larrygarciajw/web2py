"""
A7 - Parametric router: selection of per-app routing parameters.

Source: gluon/rewrite.py load (344-462), map_url_in (1476-1518, notably
line 1489 ``params_apps.get(app, params)`` where ``app`` is the boolean
function parameter, and line 1502 ``map.map_static is False`` where
``map_static`` is a method), filter_err (889-910).
Docs: docs/architecture/04-routing.md.
"""

import unittest

from gluon import rewrite
from gluon.rewrite import filter_err, filter_url, load

from ._support import make_app_tree, preserved_routes, temp_dir

HOST = "http://domain.com"

ROOT_ROUTES = """
routers = dict(BASE=dict(default_application='welcome'))
routes_app = [(r'/examples/$anything', 'examples')]
routes_onerror = [('*/*', '/welcome/default/root_error')]
"""

EXAMPLES_ROUTES = """
routes_onerror = [('*/*', '/examples/default/app_error')]
"""


class TestParametricPerAppParams(unittest.TestCase):
    """A7: which routes_onerror applies to an app in parametric mode."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = temp_dir()
        root = cls._tmp.__enter__()
        make_app_tree(root, {"welcome": None, "examples": EXAMPLES_ROUTES})
        cls._routes = preserved_routes(root)
        cls._routes.__enter__()
        load(data=ROOT_ROUTES)

    @classmethod
    def tearDownClass(cls):
        cls._routes.__exit__(None, None, None)
        cls._tmp.__exit__(None, None, None)

    def test_setup_is_parametric_with_app_level_params_loaded(self):
        self.assertIsNotNone(rewrite.routers)
        self.assertIn("examples", rewrite.params_apps)
        self.assertEqual(
            rewrite.params_apps["examples"].routes_onerror,
            [("*/*", "/examples/default/app_error")],
        )
        self.assertTrue(rewrite.params.routes_app)

    def test_current_request_for_app_selects_root_params(self):
        """PINS-DEFECT: A7-params-apps (rewrite.py:1489)."""
        filter_url(HOST + "/examples/default/index")
        self.assertIs(rewrite.THREAD_LOCAL.routes, rewrite.params)

    def test_current_app_level_routes_onerror_is_not_used(self):
        """PINS-DEFECT: A7-params-apps. The root handler wins for 'examples'."""
        filter_url(HOST + "/examples/default/index")
        self.assertEqual(
            filter_err(404, application="examples"),
            "/welcome/default/root_error?code=404&ticket=tkt",
        )

    def test_current_map_static_attribute_is_a_bound_method(self):
        """PINS-DEFECT: A7-map-static (rewrite.py:1502 compares it with False)."""
        self.assertTrue(callable(rewrite.MapUrlIn.map_static))
        self.assertIsNot(rewrite.MapUrlIn.map_static, False)


if __name__ == "__main__":
    unittest.main()
