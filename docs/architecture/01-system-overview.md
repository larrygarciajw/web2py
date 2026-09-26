# 01 — System Overview

## Purpose

Describe what web2py is in this repository, how the code is organized, how it runs, and where each subsystem is documented (docs 02–14). All claims were checked against source at commit `cb91b60c` (branch `ai/bootstrap-analysis`). Labels: **[Current]**, **[Compat]**, **[Legacy]**, **[Suspected issue]**, **[Unverified]**.

## Relevant source files

| Path | Role |
|---|---|
| `web2py.py` | CLI entry. Changes the working directory (`web2py.py:37`), prepends its own folder to `sys.path` (`:39`), imports `gluon.widget` (`:41`) and calls `gluon.widget.start()` (`:54`) |
| `gluon/__init__.py` | Package bootstrap: `import_packages()` (`:137`), then eager imports of `compileapp`, `dal`, `globals`, `html`, `http`, `main`, `sqlhtml`, `validators` (`:151-158`) |
| `gluon/main.py` | WSGI app `wsgibase` (`:285`), `serve_controller` (`:160`), `appfactory` (`:637`), `HttpServer` (`:722`) |
| `gluon/compileapp.py` | Execution environment (`build_environment`, `:405`) and model/controller/view runners (`:581`, `:668`, `:734`) |
| `gluon/globals.py` | `current` thread-local (`:99`), `Request` (`:291`), `Response` (`:649`), `Session` (`:1156`) |
| `gluon/packages/{pydal,yatl,rocket3}` | Git submodules (see `.gitmodules`) |
| `applications/{admin,welcome,examples}` | Bundled applications |
| `handlers/`, `anyserver.py`, `app.yaml` | Deployment adapters |

## Main classes / functions

| Symbol | Location | Note |
|---|---|---|
| `wsgibase(environ, responder)` | `gluon/main.py:285` | The single WSGI callable for all apps **[Current]** |
| `appfactory(wsgiapp=wsgibase, …)` | `gluon/main.py:637` | Optional wrapper that adds an access log and profiler **[Current]** |
| `HttpServer` | `gluon/main.py:722` | Wraps `rocket3.Rocket3` (`:806`) **[Current]** |
| `build_environment` | `gluon/compileapp.py:405` | Builds the dict namespace for app code **[Current]** |
| `restricted(ccode, environment, layer)` | `gluon/restricted.py:304` | Plain `exec(ccode, environment)` (`:314`). It is not a sandbox **[Current]** |
| `current` | `gluon/globals.py:99` | `threading.local()` holding request, response, session, T and cache **[Current]** |
| `global_settings` | `gluon/settings.py:15` | Process-wide `Storage`. The alias `settings` exists for old code (`:16`) **[Compat]** |
| `start()` | `gluon/widget.py:660` | Parses the CLI (`console()` at `gluon/console.py:64`) and starts the server, scheduler, cron or shell **[Current]** |

## What web2py is here

- A fork of web2py `3.3.3-stable+timestamp.2026.04.28.08.03.04` (`gluon/version.py:1`). `gluon/__init__.py:13` still declares `__version__ = "3.0.3"` **[Suspected issue]** (metadata mismatch, already known).
- A full-stack WSGI framework. One process serves every app under `applications/`, all through `gluon.main.wsgibase` **[Current]**.
- App code (models, controllers, views) is **not imported**. It is read from disk, compiled, and `exec`'d in a prepared dict namespace **[Current]** (`compileapp.py:626`, `:724`, `:797` → `restricted.py:314`).
- There is no packaging metadata (`setup.py`, `pyproject.toml`) at the repo root. Only the submodules have a `pyproject.toml` **[Current]**.

## Top-level layout

| Path | Contents | Label |
|---|---|---|
| `web2py.py` | CLI launcher (57 lines) | [Current] |
| `gluon/` | Framework core: 44 `.py` files, about 34.4k lines (`wc -l gluon/*.py`) | [Current] |
| `gluon/packages/` | Submodules `pydal`, `yatl`, `rocket3`. Note that the submodule named `gluon/packages/dal` has path `gluon/packages/pydal` (`.gitmodules`) | [Current] |
| `gluon/contrib/` | 177 `.py` files: vendored libraries and optional features (login methods, redis/memcache, markmin, pysimplesoap, pyaes, multipart…) | [Current]/[Legacy] mix |
| `gluon/tests/` | stdlib `unittest` suite | [Current] |
| `applications/` | `admin`, `welcome`, `examples`, plus `applications/__init__.py`, which makes `applications.<app>.modules.*` importable (`compileapp.py:352`) | [Current] |
| `handlers/` | cgi, fcgi, gae, isapi, modpython, scgi, wsgi and gevent adapters. They are meant to be copied to the root | [Current]/[Legacy] |
| `anyserver.py` | Runner for third-party WSGI servers. Its `rocket` entry imports the nonexistent `gluon.rocket` (`anyserver.py:59`) | [Legacy] |
| `app.yaml` | GAE config, `entrypoint: gunicorn -b :$PORT gluon:wsgibase` (`app.yaml:14`) | [Current] |
| `scripts/` (53 entries), `extras/`, `docker/`, `examples/` | Ops scripts, build tooling, Dockerfiles, sample `routes`/`logging` configs | [Current]/[Legacy] |
| `site-packages/` | Tracked folder (only `__init__.py`). Added to `sys.path` at import time (`fileutils.py:588`) | [Current] |
| `deposit/`, `logs/`, `httpserver.*`, `parameters_*.py`, `welcome.w2p` | Runtime artifacts created by imports, the server or tests. Git-ignored | [Current] |

## Three-tier code organization

| Tier | Modules | Evidence |
|---|---|---|
| **1. Real gluon code** | `main`, `compileapp`, `globals`, `rewrite`, `restricted`, `http`, `storage`, `html`, `sqlhtml`, `tools`, `authapi`, `cache`, `scheduler`, `languages`, `utils`, `fileutils`, `widget`, `console`, `shell`, `newcron`, `custom_import`, `cfs`, `serializers`, `streamer`, `recfile`, `contenttype`, `form`, `admin`, `debug`, `highlight`, `decoder`, `messageboxhandler`, `xmlrpc`, `settings`, `version`, `digest` | Largest: `tools.py` 7707 lines, `sqlhtml.py` 4521, `html.py` 3001 |
| **2. Thin shims over submodules** [Compat] | `template.py` (1 line → `yatl.template.parse_template, render`), `sanitizer.py` (1 line → `yatl.sanitizer.sanitize`), `validators.py` (9 lines → `pydal.validators`), `dal.py` (48 lines: re-exports pydal and installs web2py hooks), `sql.py` (30 lines: `SQLDB`/`SQLField`/`SQLTable`… aliases, `sql.py:22-30`) | `gluon/template.py:1`, `gluon/sanitizer.py:1`, `gluon/validators.py:1-9`, `gluon/dal.py:12-25` |
| **3. Submodules** | `pydal` (DAL, validators, portalocker), `yatl` (template engine, sanitizer), `rocket3` (threaded WSGI server) | `gluon/__init__.py:137-146` |

Notes:
- `gluon/dal.py` is not only a re-export. At import time it changes `DAL` class attributes: `serializers`, `uuid`, `representers` (`dal.py:21-25`). It also registers contrib DB drivers into `pydal.drivers.DRIVERS` (`dal.py:28-47`) **[Current]**.
- `gluon/template.py` re-exports only `parse_template` and `render`. Old code that imports other names from `gluon.template` (for example `TemplateParser`) would fail **[Unverified]**: no in-repo caller was found.
- `gluon/digest.py` is an orphan. No module in `gluon/`, `applications/` or `gluon/tests/` imports it. Its `pbkdf2_hex` refers to the undefined names `sha1` and `binascii` (`digest.py:19`, `:23`) **[Legacy]/[Suspected issue]**.

## Bundled apps

| App | Role | Notes |
|---|---|---|
| `welcome` | Scaffolding app, and the template for new apps (`create_welcome_w2p`, `fileutils.py:332`) | Imports `gluon.contrib.appconfig`, `gluon.tools`, `gluon.scheduler`, … |
| `admin` | Web IDE: edit, compile, pack and install apps, debugger, webservices | Security-sensitive. Uses `gluon.admin` (6 imports), `gluon.fileutils` (11), `gluon.debug`, `gluon.compileapp` |
| `examples` | Documentation/demo site | Uses `gluon.contrib.{pysimplesoap,rss2,pyrtf,feedparser,spreadsheet}` |

- `controllers/appadmin.py` is byte-identical in all three apps (same md5 `6bd368ac…`) **[Current]**.
- `views/appadmin.html` is **not** identical. The `admin` copy adds `nonce="{{=response.nonce}}"` on `<script>`/`<style>` (3 places). `welcome` and `examples` are identical **[Current]**.

## Runtime model

1. **Single process, many apps.** `wsgibase` serves every app. The app is chosen per request by `rewrite.url_in` (`main.py:337`). There is no per-app process or interpreter isolation **[Current]**.
2. **Threaded server.** The built-in server is `rocket3.Rocket3` with a thread pool (`main.py:806-815`). Other servers go through `handlers/` or `anyserver.py` **[Current]**.
3. **Per-request state** lives in:
   - `gluon.globals.current` (`threading.local`, `globals.py:99`). It is cleared at the start of each request (`main.py:314`) and populated by `build_environment` (`compileapp.py:432-438`).
   - `gluon.rewrite.THREAD_LOCAL` (`rewrite.py:36`) for routing parameters.
   - pydal's own `THREAD_LOCAL` for connections and the DB folder (`gluon/packages/pydal/pydal/connection.py:56-63`, `:118`) **[Current]**.
4. **Process-global mutable state** that request code touches:
   - `global_settings` (`settings.py:15`). `gluon_parent` defaults to `os.getcwd()` (`settings.py:24`).
   - `builtins.__import__` is replaced process-wide by `custom_import_install()` (`custom_import.py:25-28`), called on every `build_environment` (`compileapp.py:470-472`).
   - `Validator.translator` is a **class attribute** of pydal's `Validator`, rebound on every request to that request's `T` (`compileapp.py:428-430`, used by `pydal/validators.py:98-99`) **[Suspected issue]**: concurrent requests could translate validator messages with another request's `T`. Not demonstrated.
   - The `cfs` bytecode cache and `CACHED_REGEXES` (`compileapp.py:56`).
5. **exec-based app code.** `build_environment` copies `_base_environment_`, which holds all names from `html.__all__` and `validators.__all__` plus `HTTP`, `redirect`, `DAL`, `Field`, `SQLDB`, `SQLField`, `SQLFORM`, `SQLTABLE` and `LOAD` (`compileapp.py:391-402`). It then adds `request`, `response`, `session`, `T`, `cache` and `local_import` (`:422-468`). Models, the controller and the view are exec'd into the same dict **[Current]**. `SQLDB`/`SQLField` are **[Compat]**.
6. **App modules.** `custom_importer` first tries the **native** import, then falls back to `applications.<app>.modules.<name>` (`custom_import.py:63-100`). A same-named module elsewhere on `sys.path` therefore shadows the app module **[Current]**.
7. **Success is an exception.** `serve_controller` ends with `raise HTTP(...)` (`main.py:223`), and commit happens in the `except HTTP` branch (`main.py:475-500`) **[Current]**.
8. **Import-time side effects.** Importing any `gluon.*` runs `gluon/__init__.py`, which imports `gluon.main`. That import:
   - creates folders (`main.py:58-59` → `fileutils.py:582-590`)
   - may import `messageboxhandler` and set `LC_CTYPE=C` (`main.py:68-79`)
   - configures logging (`:81-84`)
   - loads routes (`:128`)
   **[Current]**.
9. **Dead monkeypatch.** `main.py:91-93` sets `pydal.get_default_represent = lambda value: value`, but the bundled pydal never reads that name (no occurrence under `gluon/packages/pydal/pydal`) **[Legacy]**.

## Execution flow (summary)

`web2py.py` → `widget.start()` → `console()` options → `main.HttpServer` → `rocket3` → `appfactory(wsgibase)` → `wsgibase`:
`url_in` → (static: `Response.stream` → `streamer.stream_file_or_304_or_206`) → `Request`/`Response`/`Session` → `session.connect` → `serve_controller` (`build_environment` → `run_models_in` → `run_controller_in` → `run_view_in`) → `raise HTTP` → commit/rollback via `BaseAdapter.close_all_instances` → session save → `try_rewrite_on_error` (may call `wsgibase` again, `main.py:592`) → optional soft cron (`:594-598`) → `HTTP.to()`. Details are in docs 02–03.

## Major subsystems (index)

| # | Doc | Scope (one line) |
|---|---|---|
| 02 | [02-startup-and-bootstrap.md](02-startup-and-bootstrap.md) | `web2py.py`, `gluon/__init__` package bootstrap, `widget.start`, `console` CLI, import-time side effects |
| 03 | [03-http-request-lifecycle.md](03-http-request-lifecycle.md) | `wsgibase` step by step, `serve_controller`, commit/rollback, tickets, `routes_onerror` re-entry |
| 04 | [04-routing.md](04-routing.md) | `rewrite.py`: pattern `routes_in/out` vs parametric `routers`, `url_in`/`url_out`, `URL()` |
| 05 | [05-dynamic-execution-environment.md](05-dynamic-execution-environment.md) | `build_environment`, `restricted`, `current`, injected globals, `custom_import` |
| 06 | [06-application-loading.md](06-application-loading.md) | Model ordering/filtering, exposed controllers, views, the compiled-app layout, `cfs` |
| 07 | [07-pydal-integration.md](07-pydal-integration.md) | `gluon/dal.py` hooks, `sql.py` aliases, validators shim, transaction handling |
| 08 | [08-auth-sessions-cache.md](08-auth-sessions-cache.md) | `Session` backends and pickle, `Auth`/`AuthAPI`, `cache.py` |
| 09 | [09-template-and-forms.md](09-template-and-forms.md) | yatl views, `html.py` helpers, `FORM`/`SQLFORM`/`form.Form`, CSRF formkeys |
| 10 | [10-scheduler.md](10-scheduler.md) | `scheduler.py` workers and tables, `-K`/`-X`, `newcron` |
| 11 | [11-security-boundaries.md](11-security-boundaries.md) | Admin gatekeeping, unpickling, crypto, `is_https`, exec surfaces |
| 12 | [12-deployment.md](12-deployment.md) | Rocket, `handlers/`, `anyserver.py`, GAE/gunicorn, Docker |
| 13 | [13-legacy-compatibility.md](13-legacy-compatibility.md) | Shims, aliases, deprecated APIs, Python 2 remnants |
| 14 | [14-dependency-map.md](14-dependency-map.md) | Import graph, layers, cycles, fan-in/out, coupled areas |

## Dependencies

- Runtime: Python 3 standard library plus the three submodules. pydal declares `requires-python >= 3.10` in its `pyproject.toml` (see `docs/ai-context/baseline.md`) **[Current]**.
- Optional: `Crypto` (PyCryptodome). Without it, `gluon.contrib.pyaes` is used (`utils.py:36-43`). Other optional packages: redis, memcache, DB drivers, tornado, PyYAML **[Current]**.
- Full graph: [14-dependency-map.md](14-dependency-map.md).

## Side effects

- Importing `gluon` creates the `applications`, `deposit`, `site-packages` and `logs` folders next to `gluon_parent` (`fileutils.py:582-585`). It also reorders `sys.path` so that `""`, `site-packages` and `gluon_parent` come first (`fileutils.py:588-589`, `add_path_first` `:603`) **[Current]**.
- `import_packages()` inserts each submodule's **repository root** at `sys.path[0]` (`gluon/__init__.py:141-143`). Those roots also contain importable `tests` packages (`gluon/packages/{pydal,yatl,rocket3}/tests/__init__.py`). A top-level `import tests` can therefore resolve to a submodule's test package **[Suspected issue]** (not demonstrated).
- Every request can create missing app folders (`main.py:426` → `fileutils.py:595`) **[Current]**.

## Compatibility constraints

- Keep all of these: the injected namespace (`compileapp.py:391-468`), the shim modules (tier 2), the `sys.modules` registration of the submodules (`gluon/__init__.py:144`), `local_import` (`compileapp.py:333`), `global_settings`/`settings` aliases (`settings.py:15-16`), the `gluon/__init__.py` `__all__` star-export used by `from gluon import *` (`gluon/__init__.py:15-121`; used in `tools.py:55`) **[Compat]**.
- `from gluon import current` (for example in `authapi.py:11` and `custom_import.py:17`) relies on the package re-export at `gluon/__init__.py:153` **[Compat]**.

## Related tests

- The official runner is `python web2py.py --run_system_tests`. It `execv`s `python -m unittest -c gluon.tests`, which loads only the modules star-imported by `gluon/tests/__init__.py:1-28`.
- Baseline (Windows 10 / Python 3.14): 487 run, 473 pass, 1 error (PAM on Windows), 13 skipped. See `docs/ai-context/baseline.md`.
- End-to-end request path: `test_web` (real server on :8000). Environment: `test_appadmin`, `test_compileapp`, `test_globals`.

## Known gaps in test coverage

- `gluon/tests/__init__.py` does not import `test_main`, `test_login_methods`, `test_oauth20_account`, `test_update_languages`, `test_rocket` (already known) **and `test_restricted`**. That last one holds 20 tests: SafeUnpickler, safe_unpickle sessions, TicketStorage, snapshot. None of these run under the official runner or CI (`.github/workflows/tests.yml:76`, `appveyor.yml:44`) **[Current]**.
- No tests for `widget`, `console`, `shell`, `custom_import`, `cfs`, or execution of a compiled app (`test_compileapp.test_compile` only compiles, `test_compileapp.py:124-127`).
- The `Validator.translator` cross-thread behavior is not tested.

## Open questions

1. Does anything outside the repo still import `gluon.digest` or the removed `gluon.template` names? **[Unverified]**
2. Does the `sys.path[0]` placement of submodule repo roots ever shadow user modules in real deployments? **[Unverified]**
3. Is `global_settings.gluon_parent = os.getcwd()` (`settings.py:24`) intended for WSGI handlers that do not `chdir`? `handlers/wsgihandler.py:24` only checks for `applications/`. **[Unverified]**

## Discrepancies with the technical reference

| Reference (`web2py_technical_reference-v2.md`) | Source |
|---|---|
| §1: PyDAL lives in `gluon/packages/dal` | Path is `gluon/packages/pydal`. Only the submodule *name* is `gluon/packages/dal` (`.gitmodules`) |
| §3: root `VERSION` file; `deposit/` part of the repo | No `VERSION`. The version is in `gluon/version.py:1`. `deposit/` is created at runtime (`fileutils.py:584`) |
| §4: `gluon.template`, `gluon.sanitizer`, `gluon.validators` implement the engines | 1–9 line re-exports (tier 2) |
| §2: models run in strict alphabetical order | Sorted by depth then name, and filtered by `response.models_to_run` (`compileapp.py:595-619`) |
| §14.3: `gluon.compileapp.exec_environment` | Defined in `gluon/shell.py:68` |
| §1: `gluon.sql` is a pre-PyDAL layer | It is a 30-line alias module over `gluon.dal`/pydal (`sql.py:15-30`) |
| Omitted by the reference | `authapi.py`, `form.py`, `console.py`, `cfs.py`, `digest.py` (orphan), the `Validator.translator` global hook, the dead `pydal.get_default_represent` patch |

## Modernization considerations

- Make the package import side-effect free: move folder creation, logging, locale and route loading out of `gluon.main` module scope. This would change `gluon/__init__.py:156` behavior, so it needs characterization tests first.
- Add `test_restricted` to `gluon/tests/__init__.py`, or switch to discovery, so the existing tests run.
- Decide whether to remove or fix `gluon/digest.py` and the no-op `pydal.get_default_represent` patch. Both are compatibility-neutral but need approval.
