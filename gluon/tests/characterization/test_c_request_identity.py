"""
C5 - HTTP raised before build_environment; C6 - client identity headers.

Source: gluon/main.py get_client (137-157), request.update with is_local /
is_https (371-384), missing app / DISABLED handling (392-420), cleanup
guarded by ``hasattr(current, "request")`` (484), which is only set by
compileapp.build_environment (434).
Docs: docs/architecture/03-http-request-lifecycle.md,
docs/architecture/11-security-boundaries.md,
docs/architecture/12-deployment.md.
"""

import unittest

from ._wsgi import WsgiHarness

CONTROLLER = """
def who():
    return '%s|%s|%s' % (request.client, request.is_local, request.is_https)

def forbidden():
    raise HTTP(403, 'nope')
"""

SESSION_COOKIE = "session_id_charapp"


class HarnessTestCase(unittest.TestCase):
    def setUp(self):
        self.h = WsgiHarness().__enter__()
        self.h.controller("default.py", CONTROLLER)

    def tearDown(self):
        self.h.__exit__(None, None, None)

    def who(self, **kwargs):
        result = self.h.call(self.h.url("default", "who"), **kwargs)
        self.assertEqual(result.code, 200, result.text)
        return result.text


class TestEarlyHTTPSkipsCleanup(HarnessTestCase):
    """C5: responses raised before build_environment carry no session cookie."""

    def test_normal_request_sets_session_cookie(self):
        result = self.h.call(self.h.url("default", "who"))
        self.assertIn(SESSION_COOKIE, result.set_cookies())

    def test_http_raised_by_action_still_sets_session_cookie(self):
        result = self.h.call(self.h.url("default", "forbidden"))
        self.assertEqual(result.code, 403)
        self.assertIn(SESSION_COOKIE, result.set_cookies())

    def test_current_invalid_url_400_has_no_session_cookie(self):
        """PINS-DEFECT: C5. Raised in url_in, before current.request exists."""
        result = self.h.call("/bad-app/x")
        self.assertEqual(result.code, 400)
        self.assertEqual(result.set_cookies(), {})

    def test_current_missing_app_404_has_no_session_cookie(self):
        """PINS-DEFECT: C5."""
        result = self.h.call("/nosuchapp/default/index")
        self.assertEqual(result.code, 404)
        self.assertEqual(result.set_cookies(), {})

    def test_current_disabled_app_503_has_no_session_cookie(self):
        """PINS-DEFECT: C5."""
        self.h.write("DISABLED", "")
        result = self.h.call(self.h.url("default", "who"), remote_addr="10.0.0.5")
        self.assertEqual(result.code, 503)
        self.assertEqual(result.set_cookies(), {})


class TestClientIdentity(HarnessTestCase):
    """C6: request.client / is_local / is_https derived from the environ."""

    def test_loopback_peer_is_local(self):
        self.assertEqual(self.who(), "127.0.0.1|True|False")

    def test_remote_peer_is_not_local(self):
        self.assertEqual(self.who(remote_addr="10.0.0.5"), "10.0.0.5|False|False")

    def test_forwarded_for_sets_client_but_not_is_local(self):
        text = self.who(remote_addr="10.0.0.5",
                        headers={"X-Forwarded-For": "127.0.0.1"})
        self.assertEqual(text, "127.0.0.1|False|False")

    def test_forwarded_for_behind_local_proxy_is_not_local(self):
        text = self.who(headers={"X-Forwarded-For": "1.2.3.4"})
        self.assertEqual(text, "1.2.3.4|False|False")

    def test_current_client_supplied_loopback_first_in_xff_is_local(self):
        """PINS-DEFECT: C6-xff. First XFF entry wins behind a local appending proxy."""
        text = self.who(headers={"X-Forwarded-For": "127.0.0.1, 1.2.3.4"})
        self.assertEqual(text, "127.0.0.1|True|False")

    def test_invalid_forwarded_for_is_400(self):
        result = self.h.call(self.h.url("default", "who"),
                             headers={"X-Forwarded-For": "not_an_ip"})
        self.assertEqual(result.code, 400)

    def test_https_from_url_scheme(self):
        self.assertTrue(self.who(scheme="https").endswith("|True"))

    def test_current_https_from_x_forwarded_proto_is_trusted(self):
        """PINS-DEFECT: C6-proto. Trusted regardless of the peer address."""
        text = self.who(remote_addr="10.0.0.5",
                        headers={"X-Forwarded-Proto": "https"})
        self.assertTrue(text.endswith("|True"), text)

    def test_https_from_https_on_environ(self):
        self.assertTrue(self.who(extra_environ={"HTTPS": "on"}).endswith("|True"))

    def test_disabled_app_is_served_to_local_client(self):
        self.h.write("DISABLED", "")
        self.assertEqual(self.who(), "127.0.0.1|True|False")

    def test_current_disabled_app_bypassed_with_spoofed_xff_behind_local_proxy(self):
        """PINS-DEFECT: C6-xff. DISABLED relies on is_local."""
        self.h.write("DISABLED", "")
        text = self.who(headers={"X-Forwarded-For": "127.0.0.1, 1.2.3.4"})
        self.assertEqual(text, "127.0.0.1|True|False")


if __name__ == "__main__":
    unittest.main()
