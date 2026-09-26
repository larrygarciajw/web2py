"""
A2 - Model discovery, ordering and conditional-model filtering.

Source: gluon/compileapp.py build_environment (models_to_run, lines
416-420), REGEX_MODEL (578), run_models_in (581-626).
Docs: docs/architecture/06-application-loading.md.

Each model appends its own relative name to ``trace`` (a list injected
into the execution environment), so the tests observe exactly which
models ran and in what order.
"""

import os
import unittest

from gluon.compileapp import build_environment, run_models_in
from gluon.globals import Request, Response, Session

from ._support import (preserved_current, preserved_validator_translator,
                       temp_dir, write_file)

MODELS = [
    "b.py",
    "a.py",
    "z-dash.py",
    "c/x.py",
    "c/f/y.py",
    "c/g/w.py",
    "other/q.py",
]


def make_models(folder, names):
    for name in names:
        path = os.path.join(folder, "models", *name.split("/"))
        write_file(path, "trace.append(%r)\n" % name)


class TestModelLoading(unittest.TestCase):
    """A2: which models run, and in which order, for a given request."""

    def run_models(self, folder, controller, function, before=None):
        request = Request(env={})
        request.application = "charapp"
        request.controller = controller
        request.function = function
        request.folder = folder
        response = Response()
        session = Session()
        env = build_environment(request, response, session)
        env["trace"] = []
        if before:
            before(response, env)
        run_models_in(env)
        return env["trace"], response

    def setUp(self):
        self._current = preserved_current()
        self._current.__enter__()
        self._translator = preserved_validator_translator()
        self._translator.__enter__()

    def tearDown(self):
        self._translator.__exit__(None, None, None)
        self._current.__exit__(None, None, None)

    def test_default_models_to_run_patterns(self):
        with temp_dir() as folder:
            _, response = self.run_models(folder, "c", "f")
        self.assertEqual(
            response.models_to_run,
            [r"^\w+\.py$", r"^c/\w+\.py$", r"^c/f/\w+\.py$"],
        )

    def test_order_is_depth_first_then_alphabetical_and_filtered(self):
        with temp_dir() as folder:
            make_models(folder, MODELS)
            trace, _ = self.run_models(folder, "c", "f")
        self.assertEqual(trace, ["a.py", "b.py", "c/x.py", "c/f/y.py"])

    def test_other_controller_models_are_skipped(self):
        with temp_dir() as folder:
            make_models(folder, MODELS)
            trace, _ = self.run_models(folder, "other", "index")
        self.assertEqual(trace, ["a.py", "b.py", "other/q.py"])

    def test_current_hyphenated_model_is_listed_but_never_runs(self):
        """PINS-DEFECT: A2-hyphen. REGEX_MODEL accepts '-', models_to_run does not."""
        with temp_dir() as folder:
            make_models(folder, MODELS)
            trace, _ = self.run_models(folder, "c", "f")
        self.assertNotIn("z-dash.py", trace)

    def test_appadmin_runs_every_model(self):
        with temp_dir() as folder:
            make_models(folder, MODELS)
            trace, _ = self.run_models(folder, "appadmin", "index")
        self.assertEqual(
            trace,
            ["a.py", "b.py", "z-dash.py", "c/x.py", "other/q.py",
             "c/f/y.py", "c/g/w.py"],
        )

    def test_models_to_run_changed_mid_run_affects_later_models(self):
        with temp_dir() as folder:
            make_models(folder, ["b.py", "c/x.py", "c/f/y.py"])
            write_file(
                os.path.join(folder, "models", "a.py"),
                "trace.append('a.py')\nresponse.models_to_run = [r'^\\w+\\.py$']\n",
            )
            trace, _ = self.run_models(folder, "c", "f")
        self.assertEqual(trace, ["a.py", "b.py"])

    def test_current_falsy_models_to_run_skips_all_remaining_models(self):
        """PINS-DEFECT: A2-falsy. Even appadmin runs nothing further."""
        with temp_dir() as folder:
            make_models(folder, ["b.py", "c/x.py"])
            write_file(
                os.path.join(folder, "models", "a.py"),
                "trace.append('a.py')\nresponse.models_to_run = []\n",
            )
            trace_c, _ = self.run_models(folder, "c", "f")
            trace_admin, _ = self.run_models(folder, "appadmin", "index")
        self.assertEqual(trace_c, ["a.py"])
        self.assertEqual(trace_admin, ["a.py"])

    def test_models_share_one_namespace(self):
        with temp_dir() as folder:
            write_file(os.path.join(folder, "models", "a.py"), "shared = 41\n")
            write_file(
                os.path.join(folder, "models", "b.py"),
                "trace.append(shared + 1)\n",
            )
            trace, _ = self.run_models(folder, "c", "f")
        self.assertEqual(trace, [42])


if __name__ == "__main__":
    unittest.main()
