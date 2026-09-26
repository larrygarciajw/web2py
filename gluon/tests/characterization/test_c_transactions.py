"""
C1-C4 - Transaction outcome of a request, observed through wsgibase.

Source: gluon/main.py wsgibase (285-600): except HTTP branch commits
(475-500), except RestrictedError logs a ticket and rolls back (534-558);
gluon/restricted.py restricted() re-raises HTTP (316-317);
gluon/packages/pydal/pydal/connection.py close / close_all_instances
(167-222).
Docs: docs/architecture/03-http-request-lifecycle.md,
docs/architecture/07-pydal-integration.md.

Every test runs against a fresh temporary app with a sqlite file database.
Row counts are read back through a second request, so only public
behavior is observed.
"""

import os
import unittest

from . import _hooks
from ._wsgi import DB_MODEL, WsgiHarness

MODEL = DB_MODEL + """
if request.function == 'missing_action':
    db.thing.insert(name='from model')
"""

HOOK_MODEL = """
from gluon.tests.characterization import _hooks

def _record(adapter):
    _hooks.CALLS.append('adapter' if adapter is not None else None)

def _boom_per_adapter(adapter):
    if adapter is not None:
        raise RuntimeError('commit failed')

def _boom_always(adapter):
    raise RuntimeError('commit failed')

if request.function == 'with_custom_commit':
    response.custom_commit = _record
elif request.function == 'with_private_custom_commit':
    response._custom_commit = _record
elif request.function == 'with_failing_custom_commit':
    response.custom_commit = _boom_per_adapter
elif request.function == 'with_always_failing_custom_commit':
    response.custom_commit = _boom_always
elif request.function == 'with_do_not_commit':
    response.do_not_commit = True
"""

CONTROLLER = """
def insert_ok():
    db.thing.insert(name='ok')
    return 'ok'

def insert_redirect():
    db.thing.insert(name='redirect')
    redirect(URL('count'))

def insert_403():
    db.thing.insert(name='forbidden')
    raise HTTP(403, 'nope')

def insert_crash():
    db.thing.insert(name='crash')
    1 / 0

def count():
    return str(db(db.thing).count())

def with_custom_commit():
    return insert_ok()

def with_private_custom_commit():
    return insert_ok()

def with_failing_custom_commit():
    return insert_ok()

def with_always_failing_custom_commit():
    return insert_ok()

def with_do_not_commit():
    return insert_ok()
"""


class TransactionTestCase(unittest.TestCase):
    def setUp(self):
        _hooks.reset()
        self.h = WsgiHarness().__enter__()
        self.h.model("db.py", MODEL)
        self.h.model("hooks.py", HOOK_MODEL)
        self.h.controller("default.py", CONTROLLER)

    def tearDown(self):
        self.h.__exit__(None, None, None)
        _hooks.reset()

    def get(self, function):
        return self.h.call(self.h.url("default", function))

    def rows(self):
        result = self.get("count")
        self.assertEqual(result.code, 200, result.text)
        return int(result.text)


class TestCommitOnSuccessAndHTTP(TransactionTestCase):
    """C1, C2: which outcomes commit."""

    def test_successful_action_commits(self):
        result = self.get("insert_ok")
        self.assertEqual((result.code, result.text), (200, "ok"))
        self.assertEqual(self.rows(), 1)

    def test_redirect_commits(self):
        result = self.get("insert_redirect")
        self.assertEqual(result.code, 303)
        self.assertEqual(result.header("Location"), "/charapp/default/count")
        self.assertEqual(self.rows(), 1)

    def test_current_user_raised_http_403_commits(self):
        """PINS-DEFECT: C2-4xx. Any HTTP raised by the action commits."""
        result = self.get("insert_403")
        self.assertEqual((result.code, result.text), (403, "nope"))
        self.assertEqual(self.rows(), 1)

    def test_current_404_for_unexposed_function_commits_model_writes(self):
        """PINS-DEFECT: C2-404. Models ran before the 404 was raised."""
        result = self.get("missing_action")
        self.assertEqual(result.code, 404)
        self.assertEqual(self.rows(), 1)


class TestRollbackAndTicket(TransactionTestCase):
    """C3: unhandled exception -> rollback + ticket."""

    def test_exception_rolls_back_and_writes_ticket(self):
        result = self.get("insert_crash")
        self.assertEqual(result.code, 500)
        tickets = os.listdir(self.h.path("errors"))
        self.assertEqual(len(tickets), 1)
        self.assertIn(tickets[0], result.text)
        self.assertEqual(self.rows(), 0)

    def test_ticket_id_is_exposed_in_web2py_error_header(self):
        result = self.get("insert_crash")
        header = result.header("web2py_error")
        self.assertIsNotNone(header)
        self.assertTrue(header.startswith("ticket charapp/"), header)


class TestCommitHooks(TransactionTestCase):
    """C4: response.custom_commit / _custom_commit / do_not_commit."""

    def test_current_custom_commit_called_per_adapter_then_with_none(self):
        """PINS-DEFECT: C4-calls. close_all_instances calls it twice."""
        result = self.get("with_custom_commit")
        self.assertEqual(result.code, 200)
        self.assertEqual(_hooks.CALLS, ["adapter", None])

    def test_custom_commit_that_does_not_commit_discards_writes(self):
        self.get("with_custom_commit")
        self.assertEqual(self.rows(), 0)

    def test_current_private_custom_commit_is_ignored(self):
        """PINS-DEFECT: C4-name. main.py reads custom_commit, not _custom_commit."""
        self.get("with_private_custom_commit")
        self.assertEqual(_hooks.CALLS, [])
        self.assertEqual(self.rows(), 1)

    def test_current_per_adapter_commit_failure_is_silent(self):
        """PINS-DEFECT: C4-silent. Adapter.close() swallows it; client sees 200."""
        result = self.get("with_failing_custom_commit")
        self.assertEqual((result.code, result.text), (200, "ok"))
        self.assertEqual(self.rows(), 0)

    def test_current_failure_in_final_none_call_becomes_framework_500(self):
        """PINS-DEFECT: C4-final. close_all_instances calls action(None) unguarded."""
        result = self.get("with_always_failing_custom_commit")
        self.assertEqual(result.code, 500)
        self.assertIn("Ticket issued", result.text)
        self.assertEqual(self.rows(), 0)

    def test_do_not_commit_discards_writes(self):
        result = self.get("with_do_not_commit")
        self.assertEqual(result.code, 200)
        self.assertEqual(self.rows(), 0)


if __name__ == "__main__":
    unittest.main()
