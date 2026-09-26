"""
B4, B5, B14 - Execution-environment side effects.

Source: gluon/compileapp.py local_import_aux (333-358), build_environment
(405-473, Validator.translator at 428-430); gluon/shell.py env (108-191,
check_credentials monkeypatch at 172-177).
Docs: docs/architecture/05-dynamic-execution-environment.md,
docs/architecture/02-startup-and-bootstrap.md.
"""

import importlib
import os
import shutil
import sys
import unittest

from gluon import fileutils
from gluon.compileapp import build_environment, local_import_aux
from gluon.globals import Request, Response, Session
from gluon.settings import global_settings
from gluon.validators import IS_NOT_EMPTY

from ._support import (preserved_current, preserved_validator_translator,
                       temp_dir, write_file)

LOCAL_IMPORT_APP = "_char_local_import"


class TestLocalImport(unittest.TestCase):
    """B4: local_import() of an app module."""

    def setUp(self):
        self.app_dir = os.path.join(
            global_settings.applications_parent, "applications", LOCAL_IMPORT_APP
        )
        if os.path.exists(self.app_dir):
            self.skipTest("%s already exists" % self.app_dir)
        write_file(os.path.join(self.app_dir, "modules", "__init__.py"))
        write_file(os.path.join(self.app_dir, "modules", "charmod.py"), "VALUE = 42\n")
        importlib.invalidate_caches()

    def tearDown(self):
        shutil.rmtree(self.app_dir, ignore_errors=True)
        prefix = "applications.%s" % LOCAL_IMPORT_APP
        for name in [m for m in sys.modules if m.startswith(prefix)]:
            del sys.modules[name]

    def test_module_is_importable_by_dotted_path(self):
        module = importlib.import_module(
            "applications.%s.modules.charmod" % LOCAL_IMPORT_APP
        )
        self.assertEqual(module.VALUE, 42)

    def test_current_local_import_raises_attributeerror(self):
        """PINS-DEFECT: B4. getattr(leaf_module, '<app>') after import_module."""
        with self.assertRaises(AttributeError):
            local_import_aux("charmod", app=LOCAL_IMPORT_APP)


ES_LANGUAGE = """{
'!langcode!': 'es',
'!langname!': 'Espanol',
'Enter a value': 'Introduzca un valor',
}
"""


class TestValidatorTranslatorIsProcessGlobal(unittest.TestCase):
    """B5: build_environment rebinds Validator.translator for everyone."""

    def setUp(self):
        self._current = preserved_current()
        self._current.__enter__()
        self._translator = preserved_validator_translator()
        self._translator.__enter__()
        self._tmp = temp_dir()
        root = self._tmp.__enter__()
        self.folder_es = os.path.join(root, "app_es")
        self.folder_en = os.path.join(root, "app_en")
        write_file(os.path.join(self.folder_es, "languages", "es.py"), ES_LANGUAGE)
        os.makedirs(os.path.join(self.folder_en, "languages"))

    def tearDown(self):
        self._tmp.__exit__(None, None, None)
        self._translator.__exit__(None, None, None)
        self._current.__exit__(None, None, None)

    def build(self, folder, language):
        request = Request(env={"HTTP_ACCEPT_LANGUAGE": language})
        request.env.http_accept_language = language
        request.application = os.path.basename(folder)
        request.controller = "c"
        request.function = "f"
        request.folder = folder
        return build_environment(request, Response(), Session())

    def test_validator_uses_request_language(self):
        self.build(self.folder_es, "es")
        _, error = IS_NOT_EMPTY()("")
        self.assertEqual(error, "Introduzca un valor")

    def test_current_later_request_changes_translation_of_earlier_validator(self):
        """PINS-DEFECT: B5. A validator built during request A uses B's T."""
        self.build(self.folder_es, "es")
        validator = IS_NOT_EMPTY()  # created while request A (es) is active
        self.build(self.folder_en, "en")  # another request starts
        _, error = validator("")
        self.assertEqual(error, "Enter a value")


class TestShellEnvReplacesCheckCredentials(unittest.TestCase):
    """B14: gluon.shell.env() monkeypatches fileutils.check_credentials."""

    def setUp(self):
        self._current = preserved_current()
        self._current.__enter__()
        self._translator = preserved_validator_translator()
        self._translator.__enter__()
        self.original = fileutils.check_credentials

    def tearDown(self):
        fileutils.check_credentials = self.original
        self._translator.__exit__(None, None, None)
        self._current.__exit__(None, None, None)

    def test_current_env_makes_check_credentials_always_true(self):
        """PINS-DEFECT: B14. Process-wide, persists after env() returns."""
        from gluon.shell import env

        with temp_dir() as folder:
            env("charapp", dir=folder)
        self.assertIsNot(fileutils.check_credentials, self.original)
        self.assertTrue(fileutils.check_credentials(Request(env={})))

    def test_name_imported_copies_are_not_patched(self):
        import gluon.tools
        from gluon.shell import env

        with temp_dir() as folder:
            env("charapp", dir=folder)
        self.assertIs(gluon.tools.check_credentials, self.original)


if __name__ == "__main__":
    unittest.main()
