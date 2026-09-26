"""
B1, B2, B6 - Session storage round trips.

Source: gluon/globals.py Session.connect (1190-1442), renew (1444-1501),
save_session_id_cookie (1549-1571), _try_store_in_cookie (1619-1638),
_try_store_in_file (1707-1737); gluon/utils.py secure_dumps /
secure_loads (220-283); gluon/restricted.py SafeUnpickler,
DEFAULT_SAFE_GLOBALS (38-116).
Docs: docs/architecture/08-auth-sessions-cache.md,
docs/architecture/11-security-boundaries.md.
"""

import os
import unittest

from gluon.globals import Request, Response, Session
from gluon.utils import secure_dumps, secure_loads

from ._support import preserved_current, temp_dir

APP = "a"


def new_request_cycle(current, folder):
    """Fresh request/response/session bound to ``current`` (like main.py)."""
    request = Request(env={})
    request.application = APP
    request.controller = "c"
    request.function = "f"
    request.folder = folder
    response = Response()
    session = Session()
    current.request = request
    current.response = response
    current.session = session
    return request, response, session


class SessionTestCase(unittest.TestCase):
    def setUp(self):
        self._current = preserved_current()
        self.current = self._current.__enter__()
        self._tmp = temp_dir()
        self.folder = os.path.join(self._tmp.__enter__(), APP)
        os.makedirs(self.folder)

    def tearDown(self):
        self._tmp.__exit__(None, None, None)
        self._current.__exit__(None, None, None)

    def cycle(self):
        return new_request_cycle(self.current, self.folder)


class TestCookieSessionRoundTrip(SessionTestCase):
    """B1: cookie-backed sessions (Session.connect(cookie_key=...))."""

    def test_secure_dumps_returns_bytes_and_bytes_round_trip(self):
        dumped = secure_dumps({"x": 1}, "secret")
        self.assertIsInstance(dumped, bytes)
        self.assertTrue(dumped.startswith(b"hmac256:"))
        self.assertEqual(secure_loads(dumped, "secret"), {"x": 1})

    def test_current_secure_loads_rejects_str_input(self):
        """PINS-DEFECT: B1-str. data.count(b':') on a str (utils.py:247)."""
        dumped = secure_dumps({"x": 1}, "secret")
        with self.assertRaises(TypeError):
            secure_loads(dumped.decode("ascii"), "secret")

    def test_current_stored_cookie_value_is_bytes_repr(self):
        """PINS-DEFECT: B1-repr. SimpleCookie stores str(bytes) -> "b'hmac256:...'"."""
        request, response, session = self.cycle()
        session.connect(request, response, cookie_key="secret")
        session.x = 1
        self.assertTrue(session._try_store_in_cookie(request, response))
        value = response.cookies["session_data_%s" % APP].value
        self.assertTrue(value.startswith("b'hmac256:"), value[:20])

    def test_current_next_request_with_session_cookie_raises_typeerror(self):
        """PINS-DEFECT: B1-roundtrip. Reading the stored cookie back fails."""
        request, response, session = self.cycle()
        session.connect(request, response, cookie_key="secret")
        session.x = 1
        session._try_store_in_cookie(request, response)
        coded = response.cookies["session_data_%s" % APP].coded_value

        request2, response2, session2 = self.cycle()
        request2.cookies.load("session_data_%s=%s" % (APP, coded))
        with self.assertRaises(TypeError):
            session2.connect(request2, response2, cookie_key="secret")

    def test_current_unchanged_cookie_session_sets_session_id_cookie_true(self):
        """PINS-DEFECT: B1-id-true. session_id is True in cookie mode."""
        request, response, session = self.cycle()
        session.connect(request, response, cookie_key="secret")
        self.assertIs(response.session_id, True)
        self.assertFalse(session._try_store_in_cookie(request, response))
        self.assertEqual(response.cookies["session_id_%s" % APP].value, "True")


class TestFileSessionSafeUnpickle(SessionTestCase):
    """B2: file sessions reloaded with Session.connect(safe_unpickle=True)."""

    def store_session(self):
        request, response, session = self.cycle()
        session.connect(request, response)
        session.x = 1
        self.assertTrue(session._try_store_in_file(request, response))
        return response.session_id

    def reload_session(self, session_id, **connect_args):
        request, response, session = self.cycle()
        request.cookies.load("session_id_%s=%s" % (APP, session_id))
        session.connect(request, response, **connect_args)
        session._close(response)
        return response, session

    def test_legacy_unpickle_restores_stored_session(self):
        session_id = self.store_session()
        response, session = self.reload_session(session_id)
        self.assertEqual(session.x, 1)
        self.assertEqual(response.session_id, session_id)
        self.assertFalse(response.session_new)

    def test_current_safe_unpickle_discards_stored_session(self):
        """PINS-DEFECT: B2. Session is not in DEFAULT_SAFE_GLOBALS; error swallowed."""
        session_id = self.store_session()
        response, session = self.reload_session(session_id, safe_unpickle=True)
        self.assertIsNone(session.x)
        self.assertNotEqual(response.session_id, session_id)
        self.assertTrue(response.session_new)

    def test_safe_unpickle_works_when_session_class_is_allowed(self):
        session_id = self.store_session()
        response, session = self.reload_session(
            session_id,
            safe_unpickle=True,
            pickle_allowed_classes={"gluon.globals": {"Session"}},
        )
        self.assertEqual(session.x, 1)
        self.assertEqual(response.session_id, session_id)


class TestFileSessionRenewSeparate(SessionTestCase):
    """B6: Session.renew() with separate=True file sessions."""

    def test_separate_creates_two_character_prefix_folder(self):
        request, response, session = self.cycle()
        session.connect(request, response, separate=True)
        self.assertRegex(response.session_id, r"^.{2}/")
        prefix, name = response.session_id.split("/")
        self.assertEqual(prefix, name[-2:])

    def test_current_renew_drops_the_separate_prefix(self):
        """PINS-DEFECT: B6. renew() reads response.session (never set)."""
        request, response, session = self.cycle()
        session.connect(request, response, separate=True)
        old_id = response.session_id
        session.renew()
        self.assertNotEqual(response.session_id, old_id)
        self.assertNotIn("/", response.session_id)
        self.assertTrue(response.session_new)


if __name__ == "__main__":
    unittest.main()
