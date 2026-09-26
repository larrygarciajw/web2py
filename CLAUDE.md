# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

This is a fork of web2py 3.3.3 (Python 3.9+, limited-maintenance upstream) that is being **incrementally modernized** while preserving the web2py programming model and compatibility with existing applications. Goals and non-goals are in `docs/project-goals.md`. Migrating to Django, Flask, FastAPI or py4web, rewriting the framework, and removing compatibility mechanisms are all out of scope.

## Source-of-truth rule

The **current source code is authoritative**. Documentation, including `docs/ai-context/web2py_technical_reference-v2.md` (in Spanish, partly outdated), gives context only. When docs and code disagree, trust the code and record the discrepancy. Known discrepancies are listed in `docs/ai-context/architecture-report.md` §11.

## Working rules

- **Characterization tests before any core refactor.** Before changing behavior in `gluon/`, add tests that pin the current behavior (including quirks), and confirm they pass on unmodified code.
- **Small, incremental changes.** One concern per change. Don't combine refactoring with behavior changes.
- **Targeted tests plus regression.** Run the tests for the touched module, then the full suite, and compare against the baseline in `docs/ai-context/baseline.md`. Any new failure, error or skip must be explained.
- A failing test is not evidence of a bug unless it actually demonstrates one.
- Do not change the submodules `gluon/packages/{pydal,yatl,rocket3}`. They are separate upstream projects pinned by commit.
- Do not modify production code or tests, or delete runtime artifacts, without explicit approval for that step.

## Commands

No build step, linter or formatter config exists in the repo. Tests use stdlib `unittest` (no pytest config).

```bash
# Official full suite (what CI and the Makefile run)
W2P_SKIP_SCHEDULER_TESTS=1 python web2py.py --run_system_tests -v

# Equivalent direct form. Use this on Windows (see below).
W2P_SKIP_SCHEDULER_TESTS=1 python -m unittest -v -c gluon.tests

# Single module / class / test
python -m unittest -v gluon.tests.test_storage
python -m unittest -v gluon.tests.test_globals.testResponse
python -m unittest -v gluon.tests.test_router.TestRouter.test_router_args

# Run the dev server
python web2py.py -a <admin_password> -i 127.0.0.1 -p 8000

# Shell with an app's models loaded; run a script in an app's environment
python web2py.py -S welcome -M
python web2py.py -S welcome -M -R path/to/script.py
```

Run commands from the repo root. Tests use relative paths such as `applications/`.

Test environment switches:
- `DB` selects the DAL URI (default `sqlite:memory`).
- `W2P_SKIP_SCHEDULER_TESTS=1` skips the scheduler suite.
- `--with_coverage` requires `coverage` and uses `gluon/tests/coverage.ini`.

Six test modules (42 test functions) are not imported by `gluon/tests/__init__.py` and are never run by the suite, so run them explicitly by name. They are `test_restricted`, `test_login_methods`, `test_oauth20_account`, `test_update_languages`, `test_main` and `test_rocket`.

### Windows baseline limitations

The accepted baseline is Windows 10 / Python 3.14: 487 tests, 473 pass, 1 error, 13 skipped (details in `docs/ai-context/baseline.md`).

- `--run_system_tests` calls `os.execv`. On Windows this detaches the child and returns exit 0 immediately, so output gets truncated. Use the direct `python -m unittest` form.
- A known error: `test_contribs...test_pam_authentication_requires_account_approval`. `gluon/contrib/pam.py` calls `CDLL(None)` on Windows.
- Symlink tests are skipped without the symlink privilege. Redis, tornado and PyYAML tests are skipped when those libraries are absent.
- `test_web` starts a real server on port 8000. `test_cron` spawns `web2py.py` subprocesses.
- Test runs leave git-ignored artifacts in the repo root and in `applications/`, such as `parameters_8000.py`, `httpserver.*`, `welcome.w2p` and `applications/admin/{cache,sessions,private}`.
- Importing `gluon` has side effects: it creates `deposit/`, `logs/` and similar folders (`gluon/main.py` → `fileutils.create_missing_folders`).

## Architecture (big picture)

**Request flow.** `web2py.py` → `gluon/widget.py:start()` (CLI options in `gluon/console.py`) → `main.HttpServer` → rocket3 → `gluon.main.wsgibase`.

`wsgibase` runs these steps:
1. `rewrite.url_in` routes the request (parametric `routers` or pattern `routes_in`).
2. Static files are streamed.
3. `Request`, `Response` and `Session` are built (`gluon/globals.py`), and `session.connect` runs.
4. `serve_controller` does the following:
   - `compileapp.build_environment` injects the globals.
   - `run_models_in` runs the models.
   - `run_controller_in` runs the controller.
   - `run_view_in` renders the view.
5. **The result is raised as `HTTP`.** A successful response also travels as an exception.
6. The `except HTTP` branch commits via `BaseAdapter.close_all_instances("commit")` and stores the session.
7. `RestrictedError` → rollback and an error ticket (`gluon/restricted.py`).
8. `routes_onerror` may re-enter `wsgibase` recursively.

**Dynamic execution.** Models, controllers and views are not imported. They are `exec`'d by `restricted()` (no sandbox) in a dict namespace built by `compileapp.build_environment`. Code outside that namespace reaches request state through `gluon.current` (a `threading.local`).
- Models are ordered by directory depth, then alphabetically, and filtered by `response.models_to_run`. They are not simply alphabetical.
- A controller function is exposed if it matches `REGEX_EXPOSED` in `compileapp.py`: defined at column 0, takes no parameters, and has at most one leading underscore.
- If `applications/<app>/compiled/` exists, only the compiled `.pyc` code runs.

**Code location.** Several `gluon` modules are thin shims over submodules:
- `gluon/template.py` and `gluon/sanitizer.py` → yatl
- `gluon/validators.py` → `pydal.validators`
- `gluon/dal.py` and `gluon/sql.py` → pydal

`gluon/__init__.py:import_packages()` puts the submodules on `sys.path` and aliases them. It also imports `gluon.main`, so importing anything from `gluon` triggers main's import-time side effects.

**Critical core files:**
- request pipeline: `gluon/main.py`, `compileapp.py`, `globals.py` (sessions, pickle-based), `rewrite.py`, `restricted.py`, `http.py`, `storage.py`
- crypto and cookies: `utils.py`
- helpers, URL signing, `FORM` CSRF: `html.py`
- forms and grid: `sqlhtml.py`
- Auth: `tools.py` + `authapi.py`
- `cache.py`, `scheduler.py`
- file ops and credentials: `fileutils.py`
- `custom_import.py`, `cfs.py`
- CLI and shell: `widget.py`, `console.py`, `shell.py`
- admin gatekeeping: `applications/admin/models/access.py`

**Bundled apps.**
- `applications/welcome` is the scaffolding app and the reference for app-level API usage.
- `applications/admin` is the web IDE. It is security-sensitive: file write, code exec, app install.
- `appadmin.py` is byte-identical across all three apps. Keep them in sync.

## Compatibility policy

Existing apps must keep working. Preserve all of the following unless a change is explicitly approved:
- the injected global namespace, including `SQLDB`, `SQLField` and `local_import`
- the shim modules
- `Storage` returning `None` for missing keys
- the compiled-app `.pyc` layout
- both router systems, `routes_onerror` and `routes_apps_raw`
- deprecated CLI option aliases
- legacy crypto formats (`secure_loads_deprecated`, `LazyCrypt` unsalted hashes)
- pickled session and ticket formats
- `Crud` and other deprecated-but-present APIs

## Normally excluded from analysis

- `applications/**/{languages,sessions,cache,errors,uploads}/`
- `__pycache__/`, `*.pyc`, `*.log`
- generated/runtime files: `deposit/`, `logs/`, `httpserver.*`, `parameters_*.py`, `*.w2p`, `applications/*/databases/`
- `binaries/`

Old or legacy code is **not** excluded for being old. `gluon/contrib/` and `handlers/` are in scope, and they contain known Python 2 remnants.

## Reference documents

- `docs/project-goals.md`: objectives, scope and incremental strategy.
- `docs/ai-context/architecture-report.md`: verified architecture, request lifecycle, subsystems, high-risk areas, discrepancies with the reference, open questions.
- `docs/ai-context/baseline.md`: environment and test baseline to compare against.
- `docs/ai-context/web2py_technical_reference-v2.md`: historical/architectural reference. Verify before relying on it.
- `docs/architecture/`: location for architecture decision records and design notes produced during modernization (currently empty).
- `docs/*.rst`: upstream Sphinx API stubs.
