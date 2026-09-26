"""
B12 - AppConfig.get() comma lists; B13 - lazy_cache() default key.

Source: gluon/contrib/appconfig.py AppConfig (40-49), AppConfigDict.get
(62-80); gluon/cache.py lazy_cache (794-816).
Docs: docs/architecture/08-auth-sessions-cache.md,
docs/architecture/11-security-boundaries.md (welcome passes
configuration.get("host.names") to Auth(host_names=...)).
"""

import os
import unittest

from gluon.cache import Cache, lazy_cache
from gluon.contrib.appconfig import AppConfig
from gluon.globals import Request

from ._support import preserved_current, temp_dir, write_file

APP = "_char_appconfig"

INI = """[host]
names = localhost:*, 127.0.0.1:*

[db]
pool_size = 10
flag = true
"""


class TestAppConfigCommaList(unittest.TestCase):
    """B12: comma-separated values are returned as a one-shot iterator."""

    def setUp(self):
        self._current = preserved_current()
        current = self._current.__enter__()
        self._tmp = temp_dir()
        folder = self._tmp.__enter__()
        write_file(os.path.join(folder, "private", "appconfig.ini"), INI)
        current.request = Request(env={})
        current.request.application = APP
        current.request.folder = folder
        self.config = AppConfig(reload=True)

    def tearDown(self):
        if hasattr(AppConfig, "AppConfig_" + APP):
            delattr(AppConfig, "AppConfig_" + APP)
        self._tmp.__exit__(None, None, None)
        self._current.__exit__(None, None, None)

    def test_scalar_values_are_coerced(self):
        self.assertEqual(self.config.get("db.pool_size"), 10)
        self.assertIs(self.config.get("db.flag"), True)
        self.assertIsNone(self.config.get("db.missing"))

    def test_current_comma_list_is_a_single_use_iterator(self):
        """PINS-DEFECT: B12. map object, exhausted after one pass, not indexable."""
        names = self.config.get("host.names")
        self.assertEqual(list(names), ["localhost:*", "127.0.0.1:*"])
        self.assertEqual(list(names), [])
        with self.assertRaises(TypeError):
            self.config.get("host.names")[0]


class TestLazyCacheDefaultKey(unittest.TestCase):
    """B13: lazy_cache() without an explicit key."""

    def setUp(self):
        self._current = preserved_current()
        current = self._current.__enter__()
        self._tmp = temp_dir()
        request = Request(env={})
        request.application = "a"
        request.folder = self._tmp.__enter__()
        current.request = request
        current.cache = Cache(request)

    def tearDown(self):
        self._tmp.__exit__(None, None, None)
        self._current.__exit__(None, None, None)

    def test_current_arguments_do_not_affect_the_cache_key(self):
        """PINS-DEFECT: B13. Every argument combination shares one entry."""
        calls = []

        @lazy_cache(time_expire=60)
        def square(x):
            calls.append(x)
            return x * x

        self.assertEqual(square(2), 4)
        self.assertEqual(square(3), 4)
        self.assertEqual(calls, [2])

    def test_result_is_cached_between_calls(self):
        @lazy_cache(time_expire=60)
        def make():
            return object()

        first = make()
        self.assertIs(make(), first)

    def test_explicit_key_separates_functions(self):
        @lazy_cache("char-key-one", time_expire=60)
        def one():
            return 1

        @lazy_cache("char-key-two", time_expire=60)
        def two():
            return 2

        self.assertEqual((one(), two()), (1, 2))


if __name__ == "__main__":
    unittest.main()
