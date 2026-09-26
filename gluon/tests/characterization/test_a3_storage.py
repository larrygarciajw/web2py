"""
A3 - gluon.storage.Storage semantics not already pinned by test_storage.

Source: gluon/storage.py Storage (lines 33-142), pickle_storage /
copyreg registration (145-149).
Docs: docs/architecture/13-legacy-compatibility.md.

Storage underlies request, response, session, settings and form vars, so
its quirks are part of the application-facing contract.
"""

import copy
import pickle
import unittest

from gluon.storage import Storage


class TestStorageContract(unittest.TestCase):
    """A3: attribute access, None assignment, copying and pickling."""

    def test_current_attribute_none_assignment_keeps_the_key(self):
        """PINS-DEFECT: A3-docstring. The class docstring says it deletes."""
        s = Storage(a=1)
        s.a = None
        self.assertIn("a", s)
        self.assertIsNone(s.a)

    def test_missing_attribute_and_item_return_none(self):
        s = Storage()
        self.assertIsNone(s.missing)
        self.assertIsNone(s["missing"])

    def test_hasattr_is_true_for_any_name(self):
        self.assertTrue(hasattr(Storage(), "anything_at_all"))

    def test_getattr_default_is_ignored(self):
        self.assertIsNone(getattr(Storage(), "missing", "default"))

    def test_del_missing_attribute_raises_keyerror(self):
        s = Storage()
        with self.assertRaises(KeyError):
            del s.missing

    def test_copy_returns_shallow_storage(self):
        inner = [1]
        s = Storage(a=inner)
        c = copy.copy(s)
        self.assertIsInstance(c, Storage)
        self.assertEqual(c, s)
        self.assertIs(c.a, inner)

    def test_pickle_round_trip_preserves_type_and_nesting(self):
        s = Storage(a=1, nested=Storage(b=2))
        loaded = pickle.loads(pickle.dumps(s, pickle.HIGHEST_PROTOCOL))
        self.assertIsInstance(loaded, Storage)
        self.assertIsInstance(loaded.nested, Storage)
        self.assertEqual(loaded.nested.b, 2)

    def test_pickle_references_storage_class_by_module_path(self):
        data = pickle.dumps(Storage(a=1), pickle.HIGHEST_PROTOCOL)
        self.assertIn(b"gluon.storage", data)
        self.assertIn(b"Storage", data)

    def test_instance_dict_lookup_falls_through_to_none(self):
        """__slots__ = () removes __dict__; __getattr__ = dict.get returns None."""
        self.assertIsNone(Storage().__dict__)


if __name__ == "__main__":
    unittest.main()
