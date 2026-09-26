"""
B3 - AuthJWT token signing with and without ``salt``.

Source: gluon/tools.py AuthJWT.__init__ (1314-1360), generate_token
(1381-1395), load_token (1401-1425).
Docs: docs/architecture/08-auth-sessions-cache.md.
"""

import os
import unittest

from gluon.dal import DAL
from gluon.globals import Request, Response, Session
from gluon.http import HTTP
from gluon.languages import TranslatorFactory
from gluon.tools import Auth, AuthJWT

from ._support import preserved_current, temp_dir


class TestAuthJWTSalt(unittest.TestCase):
    """B3: a token produced by generate_token is verified by load_token."""

    def setUp(self):
        self._current = preserved_current()
        current = self._current.__enter__()
        self._tmp = temp_dir()
        folder = self._tmp.__enter__()
        request = Request(env={})
        request.application = "a"
        request.controller = "c"
        request.function = "f"
        request.folder = folder
        current.request = request
        current.response = Response()
        current.session = Session()
        current.T = TranslatorFactory(os.path.join(folder, "languages"), "en")
        self.db = DAL("sqlite:memory")
        self.auth = Auth(self.db)
        self.auth.define_tables(username=True, signature=False)

    def tearDown(self):
        self.db.close()
        self._tmp.__exit__(None, None, None)
        self._current.__exit__(None, None, None)

    def jwt(self, **kwargs):
        return AuthJWT(self.auth, secret_key="k", verify_expiration=False, **kwargs)

    def test_token_without_salt_round_trips(self):
        jwt = self.jwt()
        token = jwt.generate_token({"a": 1})
        self.assertEqual(jwt.load_token(token)["a"], 1)

    def test_current_token_with_string_salt_is_rejected(self):
        """PINS-DEFECT: B3. generate uses "b'k'$salt", load uses "k$salt"."""
        jwt = self.jwt(salt="pepper")
        token = jwt.generate_token({"a": 1})
        with self.assertRaises(HTTP) as cm:
            jwt.load_token(token)
        self.assertEqual(cm.exception.status, 400)
        self.assertEqual(cm.exception.body, "Token signature is invalid")

    def test_current_token_with_callable_salt_is_rejected(self):
        """PINS-DEFECT: B3 (callable salt variant)."""
        jwt = self.jwt(salt=lambda payload: "u%s" % payload["a"])
        token = jwt.generate_token({"a": 1})
        with self.assertRaises(HTTP) as cm:
            jwt.load_token(token)
        self.assertEqual(cm.exception.status, 400)

    def test_tampered_token_is_rejected(self):
        jwt = self.jwt()
        token = jwt.generate_token({"a": 1})
        body, sig = token.rsplit(".", 1)
        with self.assertRaises(HTTP):
            jwt.load_token(body + "." + ("A" if sig[0] != "A" else "B") + sig[1:])


if __name__ == "__main__":
    unittest.main()
