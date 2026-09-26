"""
C7 - DB session store ordering vs commit; C8 - action return values;
C9 - LOAD() and ``current`` when a component raises.

Source: gluon/main.py (session._try_store_in_db before commit at 489,
file/cookie store after commit at 507); gluon/compileapp.py
run_controller_in (668-731), run_view_in (734-799), LOAD (70-260, swap of
current.request/response at 200-208); gluon/http.py HTTP.to (126-166).
Docs: docs/architecture/03-http-request-lifecycle.md,
docs/architecture/05-dynamic-execution-environment.md,
docs/architecture/08-auth-sessions-cache.md.
"""

import unittest

from ._wsgi import DB_MODEL, WsgiHarness

DB_SESSION_MODEL = DB_MODEL + """
session.connect(request, response, db=db)

def _boom(adapter):
    # fail only the per-adapter call, which pydal swallows (see C4)
    if adapter is not None:
        raise RuntimeError('commit failed')

if request.function == 'set_value_commit_fails':
    response.custom_commit = _boom
"""

SESSION_CONTROLLER = """
def set_value():
    session.v = 'stored'
    return 'ok'

def set_value_commit_fails():
    return set_value()

def get_value():
    return str(session.v)
"""

COOKIE = "session_id_charapp"


class TestDbSessionStoreOrdering(unittest.TestCase):
    """C7: the DB session row is written inside the request transaction."""

    def setUp(self):
        self.h = WsgiHarness().__enter__()
        self.h.model("db.py", DB_SESSION_MODEL)
        self.h.controller("default.py", SESSION_CONTROLLER)

    def tearDown(self):
        self.h.__exit__(None, None, None)

    def set_then_get(self, setter):
        first = self.h.call(self.h.url("default", setter))
        self.assertEqual(first.code, 200, first.text)
        cookie = first.set_cookies().get(COOKIE)
        self.assertTrue(cookie, first.headers)
        second = self.h.call(self.h.url("default", "get_value"),
                             cookies={COOKIE: cookie})
        return cookie, second.text

    def test_db_session_round_trip(self):
        cookie, value = self.set_then_get("set_value")
        self.assertRegex(cookie, r"^\d+:")
        self.assertEqual(value, "stored")

    def test_current_failed_commit_loses_session_but_sends_cookie(self):
        """PINS-DEFECT: C7. Row stored before commit, commit fails silently."""
        cookie, value = self.set_then_get("set_value_commit_fails")
        self.assertRegex(cookie, r"^\d+:")
        self.assertEqual(value, "None")


OUTPUT_CONTROLLER = """
def returns_none():
    return None

def returns_str():
    return 'text'

def returns_helper():
    return DIV('x', _id='d')

def returns_dict_without_view():
    return dict(a=1)

def returns_number():
    return 42
"""


class TestActionReturnValues(unittest.TestCase):
    """C8: how an action's return value becomes the response body."""

    @classmethod
    def setUpClass(cls):
        cls.h = WsgiHarness().__enter__()
        cls.h.controller("default.py", OUTPUT_CONTROLLER)

    @classmethod
    def tearDownClass(cls):
        cls.h.__exit__(None, None, None)

    def get(self, function):
        return self.h.call(self.h.url("default", function))

    def test_current_none_renders_literal_none(self):
        """PINS-DEFECT: C8-none. HTTP.to() stringifies the None body."""
        result = self.get("returns_none")
        self.assertEqual((result.code, result.text), (200, "None"))

    def test_string_is_returned_verbatim(self):
        self.assertEqual(self.get("returns_str").text, "text")

    def test_helper_is_serialized_with_xml(self):
        self.assertEqual(self.get("returns_helper").text, '<div id="d">x</div>')

    def test_number_is_stringified(self):
        self.assertEqual(self.get("returns_number").text, "42")

    def test_dict_without_view_or_generic_view_is_404(self):
        result = self.get("returns_dict_without_view")
        self.assertEqual(result.code, 404)
        self.assertIn("invalid view", result.text)

    def test_default_content_type_follows_extension(self):
        result = self.get("returns_str")
        self.assertTrue(result.header("Content-Type").startswith("text/html"))


LOAD_CONTROLLER = """
def comp_ok():
    return 'component:' + request.function

def comp_fail():
    raise ValueError('component failure')

def parent_ok():
    from gluon import current
    html = LOAD('default', 'comp_ok', ajax=False).xml()
    return '%s|%s' % (current.request.function, html)

def parent_fail():
    from gluon import current
    caught = None
    try:
        LOAD('default', 'comp_fail', ajax=False)
    except Exception as e:
        caught = type(e).__name__
    return '%s|%s|%s' % (caught, current.request.function, request.function)
"""


class TestLoadRestoresCurrent(unittest.TestCase):
    """C9: non-ajax LOAD swaps current.request/response."""

    @classmethod
    def setUpClass(cls):
        cls.h = WsgiHarness().__enter__()
        cls.h.controller("default.py", LOAD_CONTROLLER)

    @classmethod
    def tearDownClass(cls):
        cls.h.__exit__(None, None, None)

    def test_successful_component_restores_current(self):
        result = self.h.call(self.h.url("default", "parent_ok"))
        self.assertEqual(result.code, 200, result.text)
        self.assertTrue(result.text.startswith("parent_ok|"), result.text)
        self.assertIn("component:comp_ok", result.text)

    def test_current_failing_component_leaves_current_pointing_at_it(self):
        """PINS-DEFECT: C9. No try/finally around the swap (compileapp.py:200-208)."""
        result = self.h.call(self.h.url("default", "parent_fail"))
        self.assertEqual(result.code, 200, result.text)
        self.assertEqual(result.text, "RestrictedError|comp_fail|parent_fail")


if __name__ == "__main__":
    unittest.main()
