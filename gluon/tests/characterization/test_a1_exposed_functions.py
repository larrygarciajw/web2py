"""
A1 - Controller function exposure contract.

Source: gluon/compileapp.py REGEX_LONG_STRING, REGEX_EXPOSED,
find_exposed_functions (lines 547-553).
Docs: docs/architecture/06-application-loading.md,
docs/architecture/05-dynamic-execution-environment.md.

The same function decides which actions are reachable by URL in source
apps (run_controller_in) and which per-function .pyc files are produced
for compiled apps (compile_controllers), so it is a core compatibility
contract.
"""

import unittest

from gluon.compileapp import find_exposed_functions


class TestExposedFunctions(unittest.TestCase):
    """A1: which ``def`` lines become URL-callable actions."""

    def exposed(self, source):
        return find_exposed_functions(source)

    def test_plain_function_without_parameters_is_exposed(self):
        self.assertEqual(self.exposed("def index():\n    return 1\n"), ["index"])

    def test_spaces_inside_empty_parentheses_are_allowed(self):
        self.assertEqual(self.exposed("def index(  ):\n    pass\n"), ["index"])

    def test_single_leading_underscore_is_exposed(self):
        self.assertEqual(self.exposed("def _helper():\n    pass\n"), ["_helper"])

    def test_double_leading_underscore_is_not_exposed(self):
        self.assertEqual(self.exposed("def __private():\n    pass\n"), [])

    def test_function_with_required_parameter_is_not_exposed(self):
        self.assertEqual(self.exposed("def edit(record):\n    pass\n"), [])

    def test_function_with_default_parameter_is_not_exposed(self):
        self.assertEqual(self.exposed("def edit(a=1):\n    pass\n"), [])

    def test_current_return_annotation_prevents_exposure(self):
        """PINS-DEFECT: A1-annotation. ``def f() -> dict:`` is not exposed."""
        self.assertEqual(self.exposed("def index() -> dict:\n    return {}\n"), [])

    def test_indented_function_is_not_exposed(self):
        source = "class C:\n    def method():\n        pass\n"
        self.assertEqual(self.exposed(source), [])

    def test_decorated_function_is_exposed(self):
        source = "@auth.requires_login()\ndef secret():\n    return 1\n"
        self.assertEqual(self.exposed(source), ["secret"])

    def test_function_inside_triple_quoted_string_is_ignored(self):
        source = '"""\ndef hidden():\n    pass\n"""\n' "'''\ndef hidden2():\n'''\n"
        self.assertEqual(self.exposed(source), [])

    def test_function_starting_with_digit_after_underscore_is_exposed(self):
        self.assertEqual(self.exposed("def _1():\n    pass\n"), ["_1"])

    def test_async_function_is_not_exposed(self):
        self.assertEqual(self.exposed("async def index():\n    pass\n"), [])

    def test_order_follows_source_order_and_keeps_duplicates(self):
        source = "def b():\n    pass\ndef a():\n    pass\ndef b():\n    pass\n"
        self.assertEqual(self.exposed(source), ["b", "a", "b"])


if __name__ == "__main__":
    unittest.main()
