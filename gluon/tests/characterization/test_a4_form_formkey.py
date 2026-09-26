"""
A4 - FORM._formkey lifecycle (CSRF protection for FORM and SQLFORM).

Source: gluon/html.py FORM.accepts (lines 2165-2248).
Docs: docs/architecture/09-template-and-forms.md,
docs/architecture/11-security-boundaries.md.
"""

import unittest

from gluon.html import FORM, INPUT
from gluon.storage import Storage

KEYNAME = "_formkey[default]"


def new_form():
    return FORM(INPUT(_name="x"))


def issue_key(session):
    """A GET-like accepts() call: no vars, returns the freshly issued key."""
    form = new_form()
    form.accepts(Storage(), session, formname="default")
    return form.formkey


def submit(session, formkey, formname="default"):
    form = new_form()
    return form.accepts(
        Storage(x="1", _formkey=formkey, _formname=formname),
        session,
        formname="default",
    )


class TestFormKeyLifecycle(unittest.TestCase):
    """A4: key issue, retention window, one-time use."""

    def test_each_accepts_call_issues_a_new_key(self):
        session = Storage()
        first = issue_key(session)
        second = issue_key(session)
        self.assertNotEqual(first, second)
        self.assertEqual(session[KEYNAME], [first, second])

    def test_only_the_last_ten_keys_are_retained(self):
        session = Storage()
        keys = [issue_key(session) for _ in range(11)]
        self.assertEqual(len(session[KEYNAME]), 10)
        self.assertEqual(session[KEYNAME], keys[1:])

    def test_evicted_key_is_rejected(self):
        session = Storage()
        keys = [issue_key(session) for _ in range(11)]
        self.assertFalse(submit(session, keys[0]))

    def test_retained_old_key_is_accepted(self):
        session = Storage()
        keys = [issue_key(session) for _ in range(11)]
        self.assertTrue(submit(session, keys[1]))

    def test_key_is_single_use(self):
        session = Storage()
        key = issue_key(session)
        self.assertTrue(submit(session, key))
        self.assertNotIn(key, session[KEYNAME])
        self.assertFalse(submit(session, key))

    def test_wrong_formname_is_rejected_and_key_is_still_consumed(self):
        session = Storage()
        key = issue_key(session)
        self.assertFalse(submit(session, key, formname="other"))
        self.assertNotIn(key, session[KEYNAME])

    def test_missing_key_is_rejected(self):
        session = Storage()
        issue_key(session)
        self.assertFalse(submit(session, None))

    def test_without_session_no_key_check_is_done(self):
        form = new_form()
        accepted = form.accepts(
            Storage(x="1", _formname="default"), None, formname="default"
        )
        self.assertTrue(accepted)


if __name__ == "__main__":
    unittest.main()
