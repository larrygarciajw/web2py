"""
B11 - gluon.form.Form (the newer, py4web-style form).

Source: gluon/form.py Form.__init__ (120-225), clear (230), helper
(236-250), xml / __str__ (252-259).
Docs: docs/architecture/09-template-and-forms.md.
Fixture style follows gluon/tests/test_form.py.
"""

import unittest

from gluon import current
from gluon.dal import DAL, Field
from gluon.form import Form
from gluon.storage import Storage

from ._support import preserved_current


def make_request(method, post_vars=None):
    return Storage(
        method=method,
        post_vars=Storage(post_vars or {}),
        folder="./",
        application="test",
    )


class TestForm(unittest.TestCase):
    """B11: rendering, CSRF key reuse and deletion."""

    def setUp(self):
        self._current = preserved_current()
        self._current.__enter__()
        self.db = DAL("sqlite:memory")
        self.db.define_table("thing", Field("name", "string"))
        current.session = Storage()

    def tearDown(self):
        self.db.close()
        self._current.__exit__(None, None, None)

    def issue_key(self, record=None, **kwargs):
        current.request = make_request("GET")
        return Form(self.db.thing, record=record, **kwargs).formkey

    def post(self, data, record=None, **kwargs):
        current.request = make_request("POST", data)
        return Form(self.db.thing, record=record, **kwargs)

    def test_first_xml_call_renders(self):
        current.request = make_request("GET")
        html = Form(self.db.thing).xml()
        self.assertIn("_formkey", html)

    def test_current_second_xml_call_raises_unboundlocalerror(self):
        """PINS-DEFECT: B11-helper. helper() returns an unbound local when cached."""
        current.request = make_request("GET")
        form = Form(self.db.thing)
        form.xml()
        with self.assertRaises(UnboundLocalError):
            form.xml()

    def test_current_str_returns_bytes(self):
        """PINS-DEFECT: B11-str. __str__ returns xml().encode('utf8')."""
        current.request = make_request("GET")
        with self.assertRaises(TypeError):
            str(Form(self.db.thing))

    def test_current_clear_has_no_self_parameter(self):
        """PINS-DEFECT: B11-clear."""
        current.request = make_request("GET")
        form = Form(self.db.thing)
        with self.assertRaises(TypeError):
            form.clear()

    def test_formkey_is_reusable_across_submissions(self):
        key = self.issue_key()
        first = self.post({"name": "a", "_formkey": key})
        second = self.post({"name": "b", "_formkey": key})
        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertEqual(self.db(self.db.thing).count(), 2)

    def test_current_delete_ignores_deletable_false(self):
        """PINS-DEFECT: B11-delete. A posted _delete removes the record."""
        record_id = self.db.thing.insert(name="keep me")
        key = self.issue_key(record=record_id, deletable=False)
        form = self.post(
            {"_delete": "on", "_formkey": key}, record=record_id, deletable=False
        )
        self.assertTrue(form.deleted)
        self.assertEqual(self.db(self.db.thing).count(), 0)


if __name__ == "__main__":
    unittest.main()
