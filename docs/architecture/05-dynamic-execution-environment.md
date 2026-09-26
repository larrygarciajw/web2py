# 05 — Dynamic Execution Environment

## Purpose

Describes how web2py runs application code (models, controllers, views). The code is not imported. It is compiled and `exec`'d into a dict namespace built per request. The document also covers how request state reaches code outside that namespace (`gluon.current`), how app `modules/` are imported, how components (`LOAD`) re-enter the controller layer, and how the CLI shell and scheduler build the same environment.

All statements were checked against source at commit `cb91b60c`. Labels: **[Current]**, **[Compat]**, **[Legacy]**, **[Suspected issue]**, **[Unverified]**.

## Relevant source files

| File | Role |
|---|---|
| `gluon/compileapp.py` | `_base_environment_`, `build_environment`, `LOAD`, `LoadFactory`, `local_import_aux`, `run_*_in` |
| `gluon/restricted.py` | `compile2`, `restricted`, `RestrictedError` |
| `gluon/cfs.py` | `getcfs` mtime-keyed cache of compiled code |
| `gluon/globals.py` | `current` thread-local, `Request`, `Response` (`_caller`, `_view_environment`, `render`) |
| `gluon/custom_import.py` | `custom_importer`, `TrackImporter`, `track_changes` |
| `gluon/main.py` | `wsgibase` (clears `current`), `serve_controller` |
| `gluon/shell.py` | `env()`, `exec_environment()`, `run()` |
| `gluon/scheduler.py` | `executor()` builds an env for tasks |
| `gluon/languages.py`, `gluon/cache.py` | `TranslatorFactory` (T) and `Cache`, created per request |

## Main classes / functions

### `_base_environment_` (module level, built once at import)
`gluon/compileapp.py:391-402`. **[Current]**
- Every name in `html.__all__` (`:391`) and `validators.__all__` (`:392`). `gluon/validators.py:1-9` re-exports `pydal.validators.__all__`.
- `__builtins__` (`:393`). This is the `compileapp` module's `__builtins__`, which is the builtins dict, so a later patch of `builtins.__import__` is visible to exec'd code.
- `HTTP`, `redirect`, `DAL`, `Field`, `SQLFORM`, `SQLTABLE`, `LOAD` (`:394-402`).
- **[Compat]** `SQLDB = DAL` and `SQLField = Field` (`:398-399`, marked "for backward compatibility"). The bundled `appadmin.py:76` still uses `isinstance(value, SQLDB)`.

### `build_environment(request, response, session, store_current=True)`
`gluon/compileapp.py:405-473`. **[Current]** Per-call steps, in order:
1. `environment = dict(_base_environment_)`. This is a shallow copy (`:410`).
2. If `request.env` is falsy, it sets `request.env = Storage()` (`:412-413`).
3. Resets `response.models_to_run` to `[r"^\w+\.py$", r"^<c>/\w+\.py$", r"^<c>/<f>/\w+\.py$"]` (`:416-420`).
4. `T = TranslatorFactory(<folder>/languages, request.env.http_accept_language)` (`:422-424`). `cache = Cache(request)` (`:425`).
5. `Validator.translator = staticmethod(lambda text: None if text is None else str(T(text)))` (`:428-430`).
6. If `store_current` is true, it sets `current.globalenv`, `.request`, `.response`, `.session`, `.T` and `.cache` (`:432-438`).
7. A Jython branch (`:440-459`) (see Legacy).
8. Injects `request`, `response`, `session` and `local_import` (`:461-468`). `T` and `cache` were already injected at step 4.
9. `BaseAdapter.set_folder(<folder>/databases)` (`:469`). In pydal this writes `THREAD_LOCAL._pydal_folder_` (`gluon/packages/pydal/pydal/connection.py:56-63`), so it is thread-local.
10. `custom_import_install()` (`:470-472`).

**Final injected names:** html helpers, validators, `__builtins__`, `HTTP`, `redirect`, `DAL`, `Field`, `SQLDB`, `SQLField`, `SQLFORM`, `SQLTABLE`, `LOAD`, `T`, `cache`, `request`, `response`, `session`, `local_import`. `restricted()` adds `__file__` and `__name__` at exec time. **`db`, `auth` and `current.db` are not framework-provided.** Apps define them in models.

### `restricted(ccode, environment=None, layer="Unknown", scode=None)`
`gluon/restricted.py:304-331`. **[Current]**
- Sets `environment["__file__"] = layer` and `environment["__name__"] = "__restricted__"` (`:312-313`). The consequence is that `if __name__ == "__main__":` blocks never run under the web server.
- It runs a plain `exec(ccode, environment)` (`:315`). **It is not a sandbox.** It applies no builtin filtering and no resource limits, and it only wraps errors.
- Exception mapping:
  - `HTTP` is re-raised unchanged (`:316-317`).
  - `RestrictedError` is re-raised without re-wrapping (`:318-320`).
  - Any other `Exception` becomes `RestrictedError(layer, scode or ccode, "<type> <value>", environment)` (`:321-331`).
  - `BaseException` subclasses (`SystemExit`, `KeyboardInterrupt`) are **not** caught here. They propagate to `wsgibase`'s bare `except`.
- `RestrictedError.__init__` captures `traceback.format_exc()` and a `snapshot()` of the environment (`:237-251`).

`compile2(code, layer)` is simply `compile(code, layer, "exec")` (`gluon/restricted.py:300-301`). `layer` becomes the filename in tracebacks.

### `getcfs(key, filename, filter=None)`
`gluon/cfs.py:25-55`. **[Current]**
- The process-global dict is `cfs` (`:21`). Its lock is `cfs_lock` (`:22`).
- The cache entry is `(st_mtime, data)`. It is reused only when the mtime is **equal** (`:46`).
- If `stat` fails, it returns `filter()` uncached (`:39-42`).
- The lock guards only the dict get and set. `filter()` runs outside the lock (`:51`), so concurrent misses may compile twice. That is benign.
- The cache is never evicted. Entries accumulate per key.

Keys used:

| Caller | Key |
|---|---|
| Models | the model path (`compileapp.py:625`) |
| Controller source | the path (`:710`) |
| Compiled controller code | `"<path>:<function>"` (`:721-722`) |
| Compiled `.pyc` | the pyc path (`:682`, `:778`) |

**Non-compiled views are not cached.** `parse_template` and `compile2` run on every request (`:793-795`).

### `current`
`current = threading.local()` (`gluon/globals.py:99`). It is re-exported by `gluon/__init__.py:153`.

| Writer | Evidence | Fields |
|---|---|---|
| `wsgibase` start | `gluon/main.py:314` `current.__dict__.clear()` | clears everything at the **start** of each request. Nothing clears it at the end, so state lingers on the worker thread until its next request. |
| `build_environment(store_current=True)` | `compileapp.py:432-438` | `globalenv, request, response, session, T, cache` |
| `LOAD` / `LoadFactory` | `compileapp.py:200-208`, `:307-315` | temporarily swaps `request`/`response` |
| `Session.connect` | `globals.py:1245` | `_session_cookie_key` |
| Scheduler | `scheduler.py:540` (`W2P_TASK`), `:690` (`_scheduler`) | task context |
| `shell.env()` | calls `build_environment` (`shell.py:179`) | the same fields as the web path |
| `exec_environment` | `store_current=False` (`shell.py:98`) | **none** |

`current.request` does not exist between `current.__dict__.clear()` and `build_environment`. `wsgibase` therefore guards its commit and session logic with `hasattr(current, "request")` (`main.py:484`). The result is that errors raised before `serve_controller` (invalid app, `DISABLED`) skip the DB session store and the commit.

### Custom importer
`gluon/custom_import.py`. **[Compat]**
- `custom_import_install()` (`:25-28`) replaces `builtins.__import__` process-wide on the first `build_environment`. It is never uninstalled. At install time, every name already in `sys.modules` is added to `INVALID_MODULES` (`:27`). Those names are always imported natively.
- `custom_importer` (`:46-98`) activates only when `current` has `request`, the import is absolute (`level <= 0`), and the top-level name is not in `INVALID_MODULES` (`:58-62`). It works like this:
  1. It first tries the **native** import (`:64-65`). Stdlib and site-packages therefore shadow app modules of the same name.
  2. On an `ImportError` whose `e.name` is the top-level name (`:66-69`), it retries under `modules_prefix = "<parent-of-folder>.<app>.modules"`. The prefix is computed from the last two path items of `request.folder` (`:77-78`), which gives `applications.<app>.modules`. This relies on `applications/__init__.py` and `applications/<app>/modules/__init__.py` existing, and on `gluon_parent` being on `sys.path` (`fileutils.py:591-592`).
  3. For `import a.b` it imports each component under the prefix and returns the top-level package (`:79-92`). For `from a import x` it imports `<prefix>.a` with the fromlist (`:93-96`).
- **Reload tracking.** `TRACK_IMPORTER` (`:192`) is used only if `current.request._custom_import_track_changes` is truthy (`:72-75`). That flag is set only by `track_changes(True)` (`:31-33`), which nothing in `gluon/`, `welcome` or `admin` calls. The app must call it each request, typically from a model. `TrackImporter._reload_check` (`:137-177`) compares file mtimes and calls `importlib.reload`.
- `local_import(name, reload=False, app=request.application)` is injected as a lambda (`compileapp.py:464-468`) that calls `local_import_aux` (`:333-358`).

### `LOAD` (components)
`gluon/compileapp.py:70-223`. **[Current]**
- **AJAX (`ajax=True` or `url=`)** (`:117-160`). It builds a URL and validates `times` and `timeout`. It returns `DIV(content, _id=target, _data-w2p_remote=url, …)`. The client JS fetches it later. The local `statement` string is computed but never used (`:148-157`). `target` is always non-None (`:112`), so the branch always returns at `:160`.
- **Non-AJAX (inline)** (`:162-223`):
  - It builds `other_request = Storage(request)`, a shallow copy with a copied `env`, and new `controller`, `function`, `extension`, `args`, `vars`, `cid` and `path_info` (`:166-187`). It also builds a fresh `Response()` (`:175`).
  - `other_environment = copy.copy(current.globalenv)` (`:191`, commented "FIXME: NASTY"). Because `current.globalenv` is the same dict the parent models and controller run in, the copy contains every name the parent defined up to the `LOAD` call.
  - It swaps `current.request` and `current.response` (`:200-201`). It calls `run_controller_in(c, f, other_environment)` (`:202`), then `run_view_in` if the result is a dict (`:203-206`). It restores `current` afterwards (`:208`).
  - **Models are not re-run.** `current.globalenv`, `session`, `T`, `cache` and any `db` are shared with the parent.
  - It returns `TAG[""](DIV(XML(page)), script)` (`:223`). The component's `response.flash`, headers and cookies are discarded.
- `LoadFactory` (`:226-330`) is a copy of `LOAD` bound to an explicit environment. Its AJAX branch lacks `times`/`timeout` and emits an inline `<script>`. Its docstring says it is "new and experimental".

### Shell / scripts
`gluon/shell.py:108-191`. `env()` differs from the web path in these ways:

| Aspect | `shell.env()` | Web (`wsgibase`) |
|---|---|---|
| `request` | `Request({})` with synthetic `http_host`, `remote_addr=127.0.0.1`, `path_info` (`:128-170`) | from WSGI environ |
| `request.folder` | `applications/<a>` relative, or `dir` (`:135-138`) | absolute (`main.py:373`) |
| `is_shell` / `is_scheduler` | `cmd_opts.shell is not None` / `False` (`:151-156`), overridable via `extra_request` | `False` / `False` (`main.py:379-380`) |
| credentials | **monkeypatches `gluon.fileutils.check_credentials` to always return True, process-wide and permanently** (`:174-177`) | real check |
| models | run only if `import_models` (`:181-186`). A `RestrictedError` causes `sys.exit(1)` | always |
| `__name__` after build | `"__main__"` (`:190`) | `"__restricted__"` |
| controller exec | `run()` uses plain `exec`/`execfile` with no `restricted()`, and calls `f()` via `exec("print( %s())")` (`:295-309`) | `restricted` + `response._caller` |

`exec_environment()` (`shell.py:68-105`) calls `build_environment(..., store_current=False)` and does not run models. It execs one file, preferring the `.pyc` next to it (`:99-104`), and returns a `Storage`. It still mutates the process globals: it sets `Validator.translator`, calls `set_folder` and installs the importer.

The scheduler `executor()` (`scheduler.py:486`) calls `env(a, c, import_models=True, extra_request={"is_scheduler": True})` (`:521-523`). It then runs `globals().update(_env)` (`:541`), which copies the whole app namespace into the scheduler module globals of the child process.

## Execution flow

```
wsgibase: current.__dict__.clear()                     main.py:314
  … url_in, session.connect (current.request absent)
  serve_controller                                      main.py:160
    env = build_environment(req, resp, sess)            main.py:176
    response.view = "c/f.ext"                           main.py:180-184
    run_models_in(env)            # same dict mutated   main.py:191
    response._view_environment = copy.copy(env)         main.py:192   <- snapshot AFTER models, BEFORE controller
    page = run_controller_in(c, f, env)                 main.py:193   <- controller execs into the model dict
    if dict: _view_environment.update(page); run_view_in(...)   main.py:194-197
    raise HTTP(status, page, **headers)                 main.py:223
```

**Namespace sharing.**
- Models and the controller share one dict.
- The view receives a **shallow** copy taken after the models ran, plus the returned dict. Controller-level globals (helper functions, module-level variables in the controller file) are **not** visible to the view unless returned. Mutable objects (`request`, `response`, `session`, `db`) are shared by reference.
- **Asymmetry:** in `LOAD`, `other_response._view_environment = other_environment` (`compileapp.py:193`) is the *same* dict the component controller ran in, not a copy. Component views therefore **do** see controller-level globals.
- `Response.render()` (`globals.py:745-772`) updates `_view_environment` in place and calls `run_view_in`.

## Dependencies
`compileapp` → `html`, `validators` (pydal), `dal`, `sqlhtml`, `cache`, `languages`, `cfs`, `restricted`, `template` (yatl), `custom_import`, `pydal.base.BaseAdapter`, `rewrite` (for 404 messages via `THREAD_LOCAL.routes.error_message`).

## Side effects

Side effects of `build_environment` and related code, per call unless noted:

| Effect | Scope | Evidence |
|---|---|---|
| `Validator.translator` overwritten | **process-wide class attribute** (pydal `validators.py:181`) | `compileapp.py:428-430` |
| `builtins.__import__` replaced (first call) | process | `custom_import.py:26-28` |
| `BaseAdapter.set_folder` | thread-local | `compileapp.py:469` |
| `current.*` set | thread-local | `compileapp.py:432-438` |
| `CacheInRam` storage | shared per app across requests (`meta_storage` class dict) | `cache.py:188`, `:203-204` |
| `check_credentials` monkeypatch (shell only) | process, permanent | `shell.py:177` |
| `add_path_first` (`_TEST` only) | `sys.path` mutated | `compileapp.py:689-695` |

## Compatibility constraints
- **[Compat]** The injected name set, including `SQLDB`, `SQLField` and `local_import`, must stay stable.
- **[Compat]** `__name__ == "__restricted__"` in web execution, and `"__main__"` in the shell.
- **[Compat]** App modules must stay importable both as plain `import x` (via `custom_importer`) and as `applications.<app>.modules.x`. Stdlib-first resolution order is observable behavior.
- **[Compat]** The view namespace is a post-model snapshot. Apps may depend on controller globals being absent from, or present in (components), the view.
- **[Compat]** `response._caller` (default `lambda f: f()`, `globals.py:669`) is the hook through which actions are invoked (`compileapp.py:720`). Actions get **no** positional args.

## Related tests
- `gluon/tests/test_appadmin.py:31-100` drives `run_controller_in`/`run_view_in` with a hand-built `locals()` env, **not** `build_environment`. It covers compiled mode (`:224-228`) and file-stream views (`:89-96`).
- `gluon/tests/test_restricted.py` covers `SafeUnpickler`, tickets and `snapshot`. `TestRestrictedErrorSnapshot` (`:357-380`) covers `RestrictedError`. No test calls `restricted()` directly with an HTTP or `BaseException`.
- `gluon/tests/test_web.py` (a real server) exercises the full path indirectly.
- `gluon/tests/test_scheduler.py` exercises `executor` → `shell.env` (skipped when `W2P_SKIP_SCHEDULER_TESTS=1`).

## Known gaps in test coverage
None of the following is referenced in `gluon/tests/`: `build_environment`, `getcfs`, `custom_import`, `TrackImporter`, `track_changes`, `local_import`, `exec_environment`, `gluon.shell`, `LOAD` (only imported in `test_appadmin.py:33`), `LoadFactory`, or the `Validator.translator` wiring. There is also no test of the view-namespace snapshot semantics or of `current` cleanup.

## Open questions
1. **[Suspected issue]** `local_import_aux` (`compileapp.py:353-355`) calls `importlib.import_module(name)`, which already returns the **leaf** module. It then does `getattr(module, item)` for each of `<app>, modules, a, …`. That is the old `__import__`-returns-top-package idiom, and it would raise `AttributeError` for normal modules. It is unverified at runtime and has no test.
2. **[Suspected issue]** `Validator.translator` is a class attribute that is overwritten per request (`compileapp.py:428`). Under a threaded server, validator messages may be translated with another concurrent request's `T`.
3. **[Suspected issue]** `LOAD` restores `current.request`/`response` without `try/finally` (`compileapp.py:200-208`). If the component raises (`HTTP` redirect, `RestrictedError`), the parent continues with the component's `current.request` and `current.response`.
4. **[Suspected issue]** `LOAD(post_vars=Storage())` uses a mutable default argument (`compileapp.py:84`) that is assigned by reference (`:174`). It is shared across calls.
5. **[Suspected issue]** `TrackImporter._reload_check` can evaluate `None > float` when a previously tracked file disappears and is not replaced by a package (`custom_import.py:150-167`). Packages are tracked by their **directory** mtime (`:187-188`), so edits to `__init__.py` alone may not trigger a reload. `_import_dates` is shared without a lock, and `THREAD_LOCAL` (`:107`) is unused.
6. **[Suspected issue]** `shell.exec_pythonrc` (`shell.py:194-206`) calls `execfile(file)` with no globals. `exec` then runs in `execfile`'s own frame, and `locals()` returns only `{'file': …}`. `PYTHONSTARTUP` definitions probably never reach the shell env.
7. **[Unverified]** How `current` (`threading.local`) behaves under gevent/eventlet servers (`anyserver.py`) without monkeypatching.
8. `exec_environment` does not set `current`. Model code that reads `current.request` (for example `AppConfig`, `gluon/contrib/appconfig.py:44`) sees stale or absent state. **[Unverified]** end-to-end.

## Discrepancies with the technical reference
| Reference (`web2py_technical_reference-v2.md`) | Source |
|---|---|
| §2 pipeline step 1: `current` is assigned when Request/Response/Session are created | `current` is **cleared** at `main.py:314` and only populated by `build_environment` (`compileapp.py:432-438`), after `session.connect` |
| §2 pipeline step 6: action invoked as `function(*request.args, **request.vars)` | `response._caller(function)` → `f()` with no arguments (`compileapp.py:720`, `globals.py:669`) |
| §14.1 example uses `current.db` | The framework never sets `current.db`. The app must assign it. |
| §14.3 `gluon.compileapp.exec_environment` | It lives in `gluon/shell.py:68`. It runs only the given file (no other models) and does not set `current`. |
| `restricted` described as a "restricted execution environment" | plain `exec`, no sandbox (`restricted.py:315`) |
| §9 views "compiled to bytecode" | only after `compile_application`. Otherwise they are re-parsed and re-compiled on every request (`compileapp.py:793-795`). |

## Modernization considerations (optional)
- Wrap the `LOAD` `current` swap in `try/finally`. Make `Validator.translator` thread-aware, or resolve it through `current.T`.
- Add characterization tests for `build_environment` names, the view snapshot semantics, `custom_importer` resolution order, and `local_import`.
- Document that `custom_importer` is process-global before any attempt to replace it with a `sys.meta_path` finder.
