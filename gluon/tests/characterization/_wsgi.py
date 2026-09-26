"""
In-process harness for gluon.main.wsgibase (test-only).

Builds a throw-away application tree under a temporary
``applications_parent`` and calls ``wsgibase(environ, start_response)``
directly: no server, no port, no network.

Everything global that wsgibase or build_environment touches is saved and
restored: ``global_settings.applications_parent``, ``app_folders`` and
``db_sessions``, ``gluon.current``, ``Validator.translator`` and the routing
state.
"""

import io
import os
import shutil
import tempfile
from http.cookies import SimpleCookie

from ._support import (preserved_current, preserved_validator_translator,
                       write_file)

APP = "charapp"

DB_MODEL = """
db = DAL('sqlite://storage.sqlite')
db.define_table('thing', Field('name'))
"""


class Result(object):
    def __init__(self, status, headers, body):
        self.status = status
        self.code = int(status.split(" ", 1)[0])
        self.headers = headers
        self.body = body

    @property
    def text(self):
        return self.body.decode("utf8", "replace")

    def header(self, name):
        for key, value in self.headers:
            if key.lower() == name.lower():
                return value
        return None

    def set_cookies(self):
        """Parsed Set-Cookie headers as {name: value}."""
        jar = SimpleCookie()
        for key, value in self.headers:
            if key.lower() == "set-cookie":
                jar.load(value.strip())
        return {name: morsel.value for name, morsel in jar.items()}


class WsgiHarness(object):
    """Use as a context manager; ``call()`` performs one request."""

    def __init__(self, app=APP):
        self.app = app
        self.root = None

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self):
        from gluon import rewrite
        from gluon.settings import global_settings

        self.root = tempfile.mkdtemp(prefix="w2p_char_wsgi_")
        self.folder = os.path.join(self.root, "applications", self.app)
        for sub in ("models", "controllers", "views", "static", "private"):
            os.makedirs(os.path.join(self.folder, sub))
        self._old_parent = global_settings.applications_parent
        self._old_app_folders = set(global_settings.app_folders or ())
        dbs = global_settings.db_sessions
        self._old_db_sessions = dbs if dbs is True else set(dbs)
        global_settings.applications_parent = self.root
        self._current = preserved_current()
        self._current.__enter__()
        self._translator = preserved_validator_translator()
        self._translator.__enter__()
        rewrite.load(data="")  # plain pattern routing, no routes.py
        return self

    def __exit__(self, *exc):
        from gluon import rewrite
        from gluon.settings import global_settings

        self._translator.__exit__(None, None, None)
        self._current.__exit__(None, None, None)
        global_settings.applications_parent = self._old_parent
        global_settings.app_folders = self._old_app_folders
        global_settings.db_sessions = self._old_db_sessions
        rewrite.load(data="")
        shutil.rmtree(self.root, ignore_errors=True)
        return False

    # -- app content -------------------------------------------------------

    def write(self, relpath, text):
        write_file(os.path.join(self.folder, *relpath.split("/")), text)

    def model(self, name, text):
        self.write("models/%s" % name, text)

    def controller(self, name, text):
        self.write("controllers/%s" % name, text)

    def path(self, *parts):
        return os.path.join(self.folder, *parts)

    # -- requests ----------------------------------------------------------

    def call(
        self,
        path,
        method="GET",
        remote_addr="127.0.0.1",
        headers=None,
        cookies=None,
        scheme="http",
        body=b"",
        extra_environ=None,
    ):
        from gluon.main import wsgibase

        path_info, _, query = path.partition("?")
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path_info,
            "QUERY_STRING": query,
            "REMOTE_ADDR": remote_addr,
            "HTTP_HOST": "127.0.0.1:8000",
            "SERVER_NAME": "127.0.0.1",
            "SERVER_PORT": "8000",
            "SERVER_PROTOCOL": "HTTP/1.1",
            "wsgi.url_scheme": scheme,
            "wsgi.input": io.BytesIO(body),
            "wsgi.errors": io.StringIO(),
            "wsgi.version": (1, 0),
            "CONTENT_LENGTH": str(len(body)),
        }
        for key, value in (headers or {}).items():
            environ["HTTP_" + key.upper().replace("-", "_")] = value
        if cookies:
            environ["HTTP_COOKIE"] = "; ".join(
                "%s=%s" % (k, v) for k, v in cookies.items()
            )
        environ.update(extra_environ or {})

        captured = {}

        def start_response(status, response_headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = response_headers

        chunks = wsgibase(environ, start_response)
        body_bytes = b"".join(
            c if isinstance(c, bytes) else str(c).encode("utf8") for c in chunks
        )
        if hasattr(chunks, "close"):
            chunks.close()
        return Result(captured["status"], captured["headers"], body_bytes)

    def url(self, controller, function, *args):
        return "/".join(["", self.app, controller, function] + list(args))
