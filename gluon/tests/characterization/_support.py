"""Shared fixtures for characterization tests. Test-only code."""

import contextlib
import os
import shutil
import tempfile


@contextlib.contextmanager
def temp_dir(prefix="w2p_char_"):
    """Yield a temporary directory that is removed afterwards."""
    path = tempfile.mkdtemp(prefix=prefix)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_file(path, text=""):
    """Create ``path`` (and parent folders) with ``text`` as UTF-8."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf8") as f:
        f.write(text)


@contextlib.contextmanager
def preserved_current():
    """Snapshot and restore every attribute of ``gluon.globals.current``."""
    from gluon.globals import current

    saved = dict(current.__dict__)
    try:
        yield current
    finally:
        current.__dict__.clear()
        current.__dict__.update(saved)


@contextlib.contextmanager
def preserved_validator_translator():
    """``build_environment`` rebinds the process-wide Validator.translator."""
    from gluon.validators import Validator

    saved = Validator.__dict__["translator"]
    try:
        yield
    finally:
        Validator.translator = saved


@contextlib.contextmanager
def preserved_global_settings(*names):
    """Restore the given ``global_settings`` attributes (or their absence)."""
    from gluon.settings import global_settings

    missing = object()
    saved = {name: global_settings.get(name, missing) for name in names}
    try:
        yield global_settings
    finally:
        for name, value in saved.items():
            if value is missing:
                global_settings.pop(name, None)
            else:
                global_settings[name] = value


@contextlib.contextmanager
def preserved_routes(applications_parent):
    """
    Point ``global_settings.applications_parent`` at a temporary tree and
    restore the previous routing configuration afterwards (same approach as
    gluon/tests/test_router.py).
    """
    from gluon import rewrite
    from gluon.settings import global_settings

    old_parent = global_settings.applications_parent
    global_settings.applications_parent = applications_parent
    try:
        yield rewrite
    finally:
        global_settings.applications_parent = old_parent
        rewrite.load(data="")


def make_app_tree(root, apps):
    """
    Build ``root/applications/<app>/{controllers,static}`` for each app.
    ``apps`` maps app name -> optional app-level routes.py content.
    """
    for app, routes in apps.items():
        for sub in ("controllers", "static"):
            os.makedirs(os.path.join(root, "applications", app, sub), exist_ok=True)
        write_file(os.path.join(root, "applications", app, "controllers", "default.py"))
        if routes is not None:
            write_file(os.path.join(root, "applications", app, "routes.py"), routes)
