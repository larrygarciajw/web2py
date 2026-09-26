# 12 — Deployment

## Purpose

This document inventories every way this repository can serve `gluon.main.wsgibase` in production or semi-production. It records what each interface wires up, whether it still works on Python 3 (from static reading), and the deployment-relevant runtime behaviour: static versioning, proxy header trust, admin password files, maintenance mode and logging. It also compares Python support claims with CI and the bundled submodules.

Labels: **[Current]**, **[Compat]**, **[Legacy]**, **[Suspected issue]** (static reading only), **[Unverified]**. Nothing was executed.

## Relevant source files

| Path | Kind |
|---|---|
| `gluon/main.py` (`wsgibase`, `HttpServer`, `appfactory`, `save_password`, `get_client`) | WSGI app plus built-in server |
| `gluon/packages/rocket3/rocket3/__init__.py` (`Rocket3`, `:549`) | Built-in multi-threaded server (submodule) |
| `handlers/*.py`, `handlers/README` | Example adapters, meant to be copied to the root |
| `anyserver.py` | Runner for third-party WSGI servers |
| `app.yaml`, `gae.nix`, `requirements.txt`, `requirements.gae.txt` | Google App Engine / Nix |
| `docker/**` (65 Dockerfiles), `scripts/setup-*.sh` and related | Container and host provisioning |
| `extras/build_web2py/` | PyInstaller binary builds |
| `examples/logging.example.conf`, `examples/routes.*.example.py`, `examples/web.config` | Configuration templates |
| `Makefile`, `.github/workflows/tests.yml`, `appveyor.yml`, `tox.ini` | Build and CI |
| `gluon/rewrite.py`, `gluon/globals.py`, `gluon/html.py` | Static versioning |

## Main classes / functions

### Deployment interfaces and their status

| Interface | How it wires `wsgibase` | Py3 status (static reading) |
|---|---|---|
| **Rocket3 via `web2py.py`** | `HttpServer` → `rocket3.Rocket3(..., app_info={"wsgi_app": appfactory(wsgibase, ...)})` (`main.py:804-815`) | **[Current]**. This is the only path CI exercises (`test_web.py:34`) |
| `handlers/wsgihandler.py` | `application = gluon.main.wsgibase`, or `appfactory(...)` if `LOGGING` (`:35-40`). `SOFTCRON` flag (`:42-43`) | **[Current]** |
| `handlers/cgihandler.py` | `wsgiref.handlers.CGIHandler().run(gluon.main.wsgibase)` (`:71`) | **[Current]**, stdlib only |
| `handlers/fcgihandler.py` | `gluon.contrib.gateways.fcgi.WSGIServer(application, bindAddress="/tmp/fcgi.sock")` (`:48,60`) | **[Suspected issue]** `gluon/contrib/gateways/fcgi.py:64-73` tries `import thread` (Py2), then falls back to `dummy_threading`/`dummy_thread`. Those were removed in Python 3.9, so the module import should fail on every supported Python |
| `handlers/scgihandler.py` | `wsgitools` `SCGIServer(WSGIFilterMiddleware(wsgibase, GzipWSGIFilter), port=4000)` (`:64-81`) | Syntax is Py3-clean. **[Unverified]** because it depends on third-party `wsgitools` |
| `handlers/modpythonhandler.py` | Custom `Handler(req).run(gluon.main.wsgibase)` (`:227-231`) | **[Legacy]** Py2 syntax `raise exc_info[0], exc_info[1], exc_info[2]` (`:202`) is a SyntaxError on Py3 |
| `handlers/isapiwsgihandler.py` | `isapi_wsgi.ISAPIThreadPoolHandler(gluon.main.wsgibase)` (`:8-21`) | **[Legacy]** Py2 `print "USAGE..."` (`:27`) is a SyntaxError on Py3 |
| `handlers/gaehandler.py` | `run_wsgi_app(wsgiapp)` → `gluon.main.wsgibase` (`:86-112`) | **[Legacy]** `import cPickle` (`:30`), the Py2 GAE SDK `google.appengine.ext.webapp` (`:48`), `time.clock` (`:71`, removed in 3.8), `str.decode` (`:88`), and `gluon.admin.create_missing_folders()` (`:99`), which does not exist in `gluon/admin.py` |
| `handlers/web2py_on_gevent.py` | gevent `pywsgi.WSGIServer(address, application, spawn=...)` (`:43-48`) | **[Legacy]** Py2 `print` (`:109`) is a SyntaxError. Undefined `profiler` (`:32`, the option is `profiler_dir`). Reads a nonexistent `VERSION` file (`:53`). Passes an open file object as the optparse version |
| `anyserver.py` | `run()` → `getattr(Servers, name)(application, (ip, port), options=...)` (`:323-349`) | Mixed, see below |
| GAE (python311) | `app.yaml:14` `entrypoint: gunicorn -b :$PORT gluon:wsgibase` | **[Current]** in intent. The same file still has Py2.7-only keys (see below) |
| IIS (`examples/web.config`) | `WSGI_HANDLER = gluon.main.wsgibase` (wfastcgi-style appSettings) | **[Unverified]** |

`handlers/README` states the handlers are examples that "must be copied to the web2py root folder". Every handler checks `os.path.isdir("applications")` and raises `RuntimeError("Running from the wrong folder")` otherwise. `gaehandler.py:37` has `os.chdir` commented out.

### `anyserver.py`

- `Servers` has 19 static methods (`:25-216`): cgi, flup, wsgiref, cherrypy (cheroot), rocket, rocket_with_repoze_profiler, paste, fapws, gevent, bjoern, tornado, twisted, diesel, gunicorn, eventlet, mongrel2, motor, pulsar, waitress.
- **[Suspected issue] The default server is broken.** `-s` defaults to `"rocket"` (`:370`), and `Servers.rocket` / `rocket_with_repoze_profiler` import `gluon.rocket.CherryPyWSGIServer` (`:59`, `:66`). `gluon/rocket.py` does not exist, and Rocket3 has no `CherryPyWSGIServer`. This was already known in the architecture report and is re-verified here.
- **[Suspected issue]** In `Servers.fapws` the inner `def app(environ, start_response)` shadows the outer `app` and calls itself (`:97-99`), which is infinite recursion.
- **[Suspected issue]** `mongrel2_handler` uses Py2 `urllib.unquote` (`:267`) with `import urllib` (`:15`).
- `wsgiref`, `paste` and `gunicorn` reset `options = {}` (`:40`, `:83`, `:157`), so CLI options such as `-w` are ignored for them. The `gevent` server honours `options.workers`.
- `run()` defaults `softcron=True` (`:324`), so soft cron is always on under anyserver. It monkeypatches for gevent and eventlet before `import gluon.main`. It **never sets `web2py_runtime_handler`** and **never calls `save_password`**: the admin password must already exist in `parameters_<port>.py`.

### Built-in server specifics (see 02 for startup)

- `HttpServer` falls back to plain HTTP if the cert or key is missing or unreadable, and only logs a warning (`main.py:789-803`).
- The `appfactory` access log goes to `httpserver.log` with `REMOTE_ADDR` (`:698-715`). The pid file is `httpserver.pid` (`:826`).
- **[Suspected issue]** `HttpServer.stop()` relies on `signal.SIGKILL` (`:843`), which Windows does not have. The error is swallowed.

## Execution flow

Production request path (non-Rocket): web server → handler module (`chdir`, `sys.path`) → `from gluon.settings import ...` → **full `gluon.main` import side effects** (see 02) → `application = wsgibase` → per request: `wsgibase` (`main.py:285`).

### Static files and `static_version`

1. `URL('static', f)` inserts `_<static_version>` **only if** `response.static_version_urls` is true (`html.py:345-355`).
2. `Response.include_files` rewrites the first `/static/` to `/static/_<version>/` when `static_version` is set and `static_version_urls` is **not** (`globals.py:880-887`). This avoids double insertion.
3. Incoming requests: `REGEX_VERSION = ^(_[\d]+\.[\d]+\.[\d]+)$` (`rewrite.py:41`). It is stripped in pattern mode (`rewrite.py:724-725`) and in parametric mode (`MapUrlIn.map_static`, `:1127-1131`). Only exactly three numeric components match. With a `static_version` such as `"1.2"` or `"v3"`, the `_1.2` segment stays in the path and the file is not found. **[Current]**
4. `wsgibase` sets `Cache-Control: max-age=315360000` and `Expires: Thu, 31 Dec 2037 23:59:59 GMT` **only for versioned static requests** (`main.py:340-345`), then `response.stream(...)`. `?attachment` adds `Content-Disposition` (`:340-341`).
5. Reverse-proxy templates use the same three-part pattern: nginx `location ~* ^/(\w+)/static(?:/_[\d]+\.[\d]+\.[\d]+)?/(.*)$` with `expires max` (`scripts/setup-web2py-nginx-uwsgi-ubuntu.sh:58-61`, `scripts/setup_web2py_nginx_ubuntu_24_4.sh`), GAE `app.yaml:24-28` (`expiration: "365d"`), and IIS `examples/web.config:13`.

### Proxy header trust

| Value | Source | Trust |
|---|---|---|
| `request.client` | `get_client` (`main.py:137-157`): the **first** `REGEX_CLIENT` match in `X-Forwarded-For`, otherwise `REMOTE_ADDR`, otherwise `127.0.0.1`/`::1`. HTTP 400 if the value is not a valid IP | Unconditional. The leftmost (client-supplied) entry wins |
| `request.is_local` | `remote_addr in local_hosts and client == remote_addr` (`:376-377`) | Resists a spoofed XFF, because `client` must equal `REMOTE_ADDR` |
| `request.is_https` | `wsgi_url_scheme` in https, **or** `X-Forwarded-Proto` in https, **or** `HTTPS == "on"` (`:381-383`) | Unconditional (already in the architecture report) |
| admin gate | `applications/admin/models/access.py:23-29`: `is_https` → OK. Otherwise `request.env.trusted_lan_prefix` (populated from `global_settings` via `globals.py:317`) matched against `request.client`, which comes from `X-Forwarded-For`; appadmin matches against `remote_addr` instead. Otherwise requires `is_local` | Depends on the two rows above |

No setting exists to configure trusted proxies. **[Current]**

### Admin password / parameters files

- They are written by `save_password(password, port)` (`main.py:603-634`) from `HttpServer`. Provisioning scripts call it directly, for example `python -c "from gluon.main import save_password; save_password('$PW',443)"` (`scripts/setup_web2py_nginx_ubuntu_24_4.sh:182`).
- Admin reads `parameters_<request.env.server_port>.py` and **executes** it with `restricted` (`access.py:32-35`). `admin/controllers/default.py:229` also uses `server_port`. Behind a proxy or uWSGI the port is the front-end port, which is why the scripts use 443.
- If the file is missing: "admin disabled because unable to access password file". If `password=None`: "admin disabled because no admin password" (`access.py:36-50`).
- `parameters*.py` is git-ignored (`.gitignore:27`) and removed by `make clean` (`Makefile:7`).

### Maintenance mode (DISABLED)

If `applications/<app>/DISABLED` exists and the request is **not** `is_local`, the response is HTTP 503 with `static/503.html` if present, otherwise an inline "Temporarily down for maintenance" page (`main.py:392`, `:412-420`). This runs after static serving, so static files are still served.

### Logging

- `main.py:81-84` loads `logging.conf` from `applications_parent`. It is not shipped (`.gitignore:22`). The template `examples/logging.example.conf` defines loggers `root, rocket, markdown, web2py, rewrite, cron, app, welcome` and handlers console, `messageBoxHandler` (Tk) and `RotatingFileHandler("web2py.log", 1 MB × 5)`.
- `HttpServer(path=...)` reloads it relative to the cwd (`main.py:779-780`).
- The `web2py_runtime_handler` flag exists to skip the Tk/locale block under handlers. It is ineffective because of the import order (see 02, **[Suspected issue]**).

### Routes

`routes.py` at `applications_parent` is optional and git-ignored (`.gitignore:21`). The templates are `examples/routes.parametric.example.py` and `examples/routes.patterns.example.py`. `load_routes()` runs at `gluon.main` import (`main.py:128`) and again in `HttpServer` (`:776`). The uWSGI template reloads on `touch-reload = .../routes.py`.

## Dependencies

- Required: the three submodules (pydal, yatl, rocket3). There are no runtime pip requirements for the core.
- `requirements.txt`: `gunicorn`, `google-cloud-firestore`. `requirements.gae.txt` adds `firebase_admin` and comments out pydal, yatl, rocket3, pymysql and psycopg2. Both files use CRLF line endings.
- Optional per interface: gunicorn, gevent, eventlet, tornado, twisted, waitress, paste, cheroot, flup, bjoern, wsgitools, isapi_wsgi, mod_python, repoze.profile, and uwsgi (scripts).

## Side effects

- Every interface triggers the `gluon.main` import side effects in the **current working directory**. The handlers `chdir` first. The gunicorn `gluon:wsgibase` entrypoint relies on the process cwd for `gluon_parent` (`settings.py:24`). On read-only filesystems, the mkdir failure is only printed (`main.py:58-61`).
- Only the built-in server writes `parameters_<port>.py`, `httpserver.pid` and `httpserver.log` (plus the handlers with `LOGGING=True`).

## Compatibility constraints

- `handlers/*` are copied into user deployments. Their module-level name `application` and the file names are an external contract.
- Keep the `parameters_<port>.py` format (Python source executed by admin) and the `save_password` tokens. Scripts import `gluon.main.save_password` directly.
- Keep the `_X.Y.Z` static URL form and the `REGEX_VERSION` shape, because existing nginx/IIS/GAE rules hard-code it.
- The `DISABLED` file and `static/503.html` convention.
- `anyserver.py` CLI and server names are used by 50+ Dockerfiles (`CMD ... anyserver.py -s <server>`).

## Other deployment assets (brief)

- **GAE `app.yaml`:** `runtime: python311` and the gunicorn entrypoint (`:12-14`). It still contains `script: gaehandler.wsgiapp # WSGI (Python 2.7 only)` (`:44`), `admin_console`, `builtins` and appstats (`:47-56`), which are first-generation python27 directives. **[Legacy]** mixed with **[Current]**. The static handlers carry the warning that they are incompatible with the parametric router's language logic (`:20-22`).
- **`gae.nix`:** Nix shell for `python312` with `google-cloud-sdk`, memcached, redis and a venv hook. The file has no trailing newline.
- **docker/:** 65 Dockerfiles across alpine, centos, debian, fedora, opensuse, python, ubuntu and stack (nginx/db/redis/memcached compositions). All of them download `http://web2py.com/examples/static/web2py_src.zip` (**upstream**, not this fork). Eleven use `FROM python:2.7`, and the alpine images install `python` (Py2). The `CMD` lines hard-code `-a 'a'` as the admin password. **[Legacy]**
- **scripts/:** 41 `*.sh`/`*.ps1` provisioning scripts (Ubuntu/Debian/CentOS/Fedora/openSUSE/Heroku/CloudFoundry/Windows 2012R2) plus the uWSGI emperor config (`mount = /=wsgihandler:application`, `processes = 4`, uWSGI cron running `sessions2trash.py`). Many move `handlers/wsgihandler.py` to the root.
- **extras/build_web2py/:** PyInstaller specs for Windows and macOS. `build_web2py.py:9` imports `distutils` (removed in Python 3.12), `:10` imports `gluon.import_all` (the file does not exist), and `:111` uses `--hidden-import=gluon.packages.dal.pydal` (the path is `packages/pydal`). The script says it was "tested with python 3.7.3 and 2.7.16". **[Legacy]** / **[Suspected issue]**. Prebuilt `binaries/web2py_win32_py312.zip` is refreshed by `make win` via git-lfs.
- **Packaging:** there is no `setup.py`, `setup.cfg`, `pyproject.toml` or `MANIFEST.in` at the root. `make build` (`python -m build`), `make deploy` (twine) and `make install` (`pip install .`) (`Makefile:31-38`) cannot succeed. `make src` zips `fabfile.py`, `README.markdown`, `LICENSE`, `CHANGELOG`, `VERSION` and `MANIFEST.in`, none of which exist (`Makefile:46-58`). `make tests` and `make coverage` use `--run_system_tests`.

### Python version support

| Source | Claim |
|---|---|
| `README.md:11,16`; `versioning-and-support-policy.md:43,46` | Python 3.9+ |
| `.github/workflows/tests.yml` | ubuntu. Python 3.9, 3.11 and 3.12 skip the scheduler tests; 3.14 runs everything. `pip install coverage codecov redis tornado` |
| `appveyor.yml` | Windows, same Python matrix. `pip install codecov redis` only (no explicit `coverage`), yet runs `--with_coverage`. **[Unverified]** whether `codecov` pulls in `coverage` |
| `gluon/packages/pydal/pyproject.toml:6` | `requires-python >= 3.10` |
| `gluon/packages/yatl/pyproject.toml:7` / `rocket3/pyproject.toml:7` | `>=3.9` / `>=3.7` |
| `app.yaml` / `gae.nix` | 3.11 / 3.12 |
| `widget.py:41-47` | Warns only below 2.7 or 3.0-3.5 **[Legacy]** |
| `tox.ini` | py27/unittest2 (architecture report) **[Legacy]** |

The submodules are put on `sys.path`, not installed, so pydal's `requires-python` is never enforced. A quick grep of pydal found no `match` statements and no `X | Y` annotations in signatures. Whether 3.9 truly works is **[Unverified]**. **[Suspected issue]** AppVeyor calls `--run_system_tests`, which uses `os.execvpe`/`os.execv` (`widget.py:79,83`). On Windows the parent exits immediately (baseline.md), so the AppVeyor exit status may not reflect test results.

## Related tests

| Test | Covers |
|---|---|
| `gluon/tests/test_web.py:128-138` `testStaticCache` | Non-versioned static has no `max-age`/`expires`. `_1.2.3` gets both. Uses a real server |
| `gluon/tests/test_html.py:58-71` `test_StaticURL` | `URL` inserts `_1.2.3` only with `static_version_urls` |
| `gluon/tests/test_globals.py:122,257` | `include_files` |
| `gluon/tests/test_router.py:1503` | Parametric router with `static_version` |
| `gluon/tests/test_main.py:13` | `save_password("<random>")`. **Not run by the suite** |

## Known gaps in test coverage

- No tests for any `handlers/*.py`, `anyserver.py`, `app.yaml`/gunicorn entrypoint, `appfactory` logging, `HttpServer` SSL fallback, `get_client`/X-Forwarded-For, `is_https`/X-Forwarded-Proto, the DISABLED/503 path, or `parameters_<port>.py` consumption by admin.
- A plain `py_compile` of `handlers/` and `anyserver.py` would catch the SyntaxErrors. No such check exists in CI.

## Open questions

1. Is `handlers/fcgihandler.py` used by anyone? Its `gluon/contrib/gateways/fcgi.py` looks unimportable on Py3.9+.
2. Is the gunicorn `gluon:wsgibase` GAE entrypoint validated anywhere (cwd, read-only FS, `web2py_runtime_gae` only via `GAE_APPLICATION` in `rewrite.py:829`)?
3. Should the Docker assets track this fork instead of the upstream `web2py_src.zip`?
4. Is IIS `web.config` still supported (wfastcgi)?

## Discrepancies with the technical reference

| Reference (§3, §5, §16, §18) | Source |
|---|---|
| Handlers: wsgi, gae, fcgi | Also cgi, scgi, modpython, isapi, gevent. gae, isapi, modpython and gevent contain Py2-only syntax/APIs, and fcgi's gateway looks broken on 3.9+ |
| `anyserver.py` runs Tornado, Gevent, Gunicorn, Eventlet, CherryPy | 19 servers. The default `rocket` is broken. `fapws`/`mongrel2` are defective |
| `static_version` "transforms URLs generated by `URL('static', ...)`" | Only with `response.static_version_urls = True`. Otherwise only `response.include_files` inserts the segment. The version must be `X.Y.Z` numeric |
| Recommended stack: nginx serves static and handles SSL | The templates also rely on web2py honouring `X-Forwarded-*` unconditionally. There is no trusted-proxy configuration |
| `VERSION` file at the root; `deposit/` in the repo | Both are absent. The version is in `gluon/version.py`, and `deposit/` is created at import |
| Python 3.9–3.12+ | CI runs 3.9/3.11/3.12/3.14. Bundled pydal declares >=3.10 |
| "cPickle removed completely" | `handlers/gaehandler.py:30` still imports `cPickle` |

## Modernization considerations (optional)

- Add a CI `py_compile` pass over `handlers/`, `anyserver.py` and `scripts/`. Mark the Py2-only handlers as legacy, or fix them one at a time.
- Point `anyserver` `rocket` at `rocket3.Rocket3` (or change the default to `wsgiref`/`waitress`).
- Add an opt-in trusted-proxy setting for `X-Forwarded-For`/`X-Forwarded-Proto`, keeping the current default for compatibility.
- Add minimal packaging metadata, or remove the dead `build/deploy/install/src` Makefile targets.
