"""
A8 - gluon.http.HTTP serialization and redirect() details.

Source: gluon/http.py HTTP.__init__ / cookies2headers / to (106-166),
redirect (lines ~180-227).
Docs: docs/architecture/03-http-request-lifecycle.md.
"""

import unittest
from http.cookies import SimpleCookie

from gluon.globals import Request
from gluon.http import HTTP, redirect

from ._support import preserved_current


class Responder(object):
    def __call__(self, status, headers):
        self.status = status
        self.headers = headers


def render(http, env=None):
    responder = Responder()
    body = http.to(responder, env=env)
    return responder, body


class TestHTTPTo(unittest.TestCase):
    """A8: status line, headers and body produced by HTTP.to()."""

    def test_known_status_gets_standard_reason(self):
        responder, _ = render(HTTP(200, "ok"))
        self.assertEqual(responder.status, "200 OK")

    def test_unknown_integer_status(self):
        responder, _ = render(HTTP(299, "x"))
        self.assertEqual(responder.status, "299 UNKNOWN ERROR")

    def test_malformed_string_status_becomes_500(self):
        responder, _ = render(HTTP("not a status", "x"))
        self.assertTrue(responder.status.startswith("500 "))

    def test_default_content_type(self):
        responder, _ = render(HTTP(200, "ok"))
        self.assertIn(("Content-Type", "text/html; charset=UTF-8"), responder.headers)

    def test_content_length_only_for_4xx(self):
        r200, _ = render(HTTP(200, "ok"))
        r404, body = render(HTTP(404, "missing"))
        r500, _ = render(HTTP(500, "boom"))
        self.assertNotIn("Content-Length", dict(r200.headers))
        self.assertEqual(dict(r404.headers)["Content-Length"], str(len(b"missing")))
        self.assertNotIn("Content-Length", dict(r500.headers))
        self.assertEqual(body, [b"missing"])

    def test_empty_4xx_body_is_the_status_line(self):
        _, body = render(HTTP(404))
        self.assertEqual(body, [b"404 NOT FOUND"])

    def test_head_request_returns_empty_body(self):
        _, body = render(HTTP(200, "ok"), env={"request_method": "HEAD"})
        self.assertEqual(body, [b""])

    def test_non_string_body_is_stringified(self):
        _, body = render(HTTP(200, 123))
        self.assertEqual(body, [b"123"])

    def test_header_newlines_are_stripped(self):
        responder, _ = render(HTTP(200, "ok", X_Test="a\r\nb"))
        self.assertEqual(dict(responder.headers)["X_Test"], "ab")

    def test_current_set_cookie_values_keep_a_leading_space(self):
        """PINS-DEFECT: A8-cookie-space. str(morsel)[11:] drops 'Set-Cookie:' only."""
        cookies = SimpleCookie()
        cookies["a"] = "1"
        responder, _ = render(HTTP(200, "ok", cookies=cookies))
        values = [v for k, v in responder.headers if k == "Set-Cookie"]
        self.assertEqual(values, [" a=1"])


class TestRedirect(unittest.TestCase):
    """A8: redirect() raises HTTP 303 with an escaped body."""

    def setUp(self):
        self._current = preserved_current()
        current = self._current.__enter__()
        current.request = Request(env={})

    def tearDown(self):
        self._current.__exit__(None, None, None)

    def test_redirect_raises_303_with_location(self):
        with self.assertRaises(HTTP) as cm:
            redirect("/app/c/f")
        self.assertEqual(cm.exception.status, 303)
        self.assertEqual(cm.exception.headers["Location"], "/app/c/f")

    def test_redirect_encodes_crlf_in_location(self):
        with self.assertRaises(HTTP) as cm:
            redirect("/a\r\nSet-Cookie: x=1")
        self.assertEqual(cm.exception.headers["Location"], "/a%0D%0ASet-Cookie: x=1")

    def test_redirect_refuses_javascript_scheme(self):
        with self.assertRaises(HTTP) as cm:
            redirect("javascript:alert(1)")
        self.assertEqual(cm.exception.headers["Location"], "/")

    def test_current_redirect_to_empty_location_does_nothing(self):
        """PINS-DEFECT: A8-empty-redirect. Not ajax -> returns None, no HTTP."""
        self.assertIsNone(redirect(""))


if __name__ == "__main__":
    unittest.main()
