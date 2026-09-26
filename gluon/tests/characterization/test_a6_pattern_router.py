"""
A6 - Pattern-mode (non-parametric) URL parsing quirks.

Source: gluon/rewrite.py REGEX_VERSION (41), REGEX_URL (53-55),
REGEX_ARGS (56), regex_url_in (688-751), filter_url (786-888).
Docs: docs/architecture/04-routing.md,
docs/architecture/11-security-boundaries.md.

Uses a temporary applications tree, exactly like test_router.py, and the
filter_url() unit-test interface provided by gluon.rewrite.
"""

import os
import unittest

from gluon.http import HTTP
from gluon.rewrite import filter_url, load

from ._support import make_app_tree, preserved_routes, temp_dir

HOST = "http://domain.com"


class TestPatternRouter(unittest.TestCase):
    """A6: pattern mode (no ``routers``), default routes."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = temp_dir()
        cls.root = cls._tmp.__enter__()
        make_app_tree(cls.root, {"app": None})
        cls._routes = preserved_routes(cls.root)
        cls._routes.__enter__()
        load(data="")  # pattern mode, no routes_in/out

    @classmethod
    def tearDownClass(cls):
        cls._routes.__exit__(None, None, None)
        cls._tmp.__exit__(None, None, None)

    def test_basic_acf_and_args(self):
        self.assertEqual(filter_url(HOST + "/app/c/f/x/y"), "/app/c/f ['x', 'y']")

    def test_current_hyphen_splits_function_name_into_args(self):
        """PINS-DEFECT: A6-hyphen. '/a/c/my-page' -> function 'my', args ['-page']."""
        self.assertEqual(filter_url(HOST + "/app/c/my-page"), "/app/c/my ['-page']")

    def test_current_dot_dot_segments_are_kept_in_args(self):
        """PINS-DEFECT: A6-dotdot. Pattern mode keeps '..' in request.args."""
        self.assertEqual(
            filter_url(HOST + "/app/c/f/../secret"), "/app/c/f ['..', 'secret']"
        )

    def test_illegal_arg_characters_are_replaced_by_underscore(self):
        self.assertEqual(filter_url(HOST + "/app/c/f/a%20b~c"), "/app/c/f ['a_b_c']")

    def test_extension_is_reported_when_not_html(self):
        self.assertEqual(filter_url(HOST + "/app/c/f.json"), "/app/c/f.json")

    def test_static_file_resolves_inside_static_folder(self):
        static = filter_url(HOST + "/app/static/css/x.css")
        expected = os.path.join(self.root, "applications", "app", "static", "css", "x.css")
        self.assertEqual(os.path.normcase(static), os.path.normcase(expected))

    def test_static_version_segment_is_stripped(self):
        static = filter_url(HOST + "/app/static/_1.2.3/css/x.css")
        expected = os.path.join(self.root, "applications", "app", "static", "css", "x.css")
        self.assertEqual(os.path.normcase(static), os.path.normcase(expected))

    def test_static_traversal_is_rejected(self):
        with self.assertRaises(HTTP) as cm:
            filter_url(HOST + "/app/static/../controllers/default.py")
        self.assertEqual(cm.exception.status, 400)

    def test_current_version_only_static_url_raises_valueerror(self):
        """PINS-DEFECT: A6-version-only. Unpacking a 1-item list at rewrite.py:725."""
        with self.assertRaises(ValueError):
            filter_url(HOST + "/app/static/_1.2.3")

    def test_empty_static_path_is_404(self):
        with self.assertRaises(HTTP) as cm:
            filter_url(HOST + "/app/static")
        self.assertEqual(cm.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
