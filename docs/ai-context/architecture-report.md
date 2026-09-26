# web2py Architectural Report — Phase 1 (read-only baseline)

**Repo:** `d:\web2py` @ `cb91b60c`, branch `ai/bootstrap-analysis`. **Version:** `gluon/version.py` = `3.3.3-stable+timestamp.2026.04.28` (but `gluon/__init__.py:13` says `__version__ = "3.0.3"` — mismatch).
**Submodules (all populated):** `gluon/packages/pydal` (1.20260520.0), `gluon/packages/yatl` (20260805.1), `gluon/packages/rocket3` (20241225.1).

## Context
This report is the Phase 1 deliverable required by `docs/project-goals.md`: understand the current implementation before any modernization. No source files were modified. Side effect to note: one exploratory `import gluon` ran `create_missing_folders()` (`gluon/fileutils.py:582`), creating empty `deposit/` and `logs/` directories (both untracked/ignored). They can be deleted; nothing tracked changed.

Status labels used below: **[verified]** = I read the code; **[reported]** = sub-agent finding with line refs, not independently re-read; **[suspected]** = static reading, needs a characterization test.

---

## 1. Repository architecture

| Area | Role |
|---|---|
| `web2py.py` (57 L) | CLI entry → `gluon.widget.start()` |
| `gluon/` | Framework core (~40 modules) |
| `gluon/packages/{pydal,yatl,rocket3}` | Git submodules: DAL+validators, template engine+helpers+sanitizer, WSGI server |
| `gluon/contrib/` | Vendored third-party + optional features (login_methods ×22, redis_*, memcache, pyaes, markmin, pysimplesoap, fpdf, feedparser, payment gateways…) |
| `gluon/tests/` | unittest suite (~700 tests) |
| `handlers/` | Deployment adapters (wsgi, cgi, fcgi, scgi, modpython, gae, isapi, gevent) — **examples to copy to root** |
| `anyserver.py` | Runner for ~17 third-party WSGI servers |
| `applications/{admin,welcome,examples}` | Bundled apps |
| `scripts/` (~60), `extras/build_web2py`, `docker/`, `examples/` | Ops, packaging, sample routes |
| `app.yaml`, `gae.nix`, `requirements*.txt` | GAE (python311, `gunicorn gluon:wsgibase`) |
| **Absent:** `VERSION`, `setup.py`, `pyproject.toml`, root `routes.py`, `options_std.py`, `gluon/rocket.py`, `gluon/_compat.py`, `.travis.yml`, root `.coveragerc` |

Core modules are now **three tiers**: (a) real gluon code (main, compileapp, globals, rewrite, html, sqlhtml, tools, authapi, scheduler, cache, restricted, languages, utils…); (b) **thin shims** re-exporting submodules — `template.py` (1 line → yatl), `sanitizer.py` (1 line → yatl), `validators.py` (9 lines → pydal), `dal.py` (48 L), `sql.py` (30 L compat aliases); (c) submodules.

Largest core files: tools 7707, sqlhtml 4521, html 3001, scheduler 2010, globals 1761, rewrite 1579, authapi 1371, languages 1122, console 981, widget 925, main 845, compileapp 827, cache 816.

## 2. Core entry points

| Entry | Path |
|---|---|
| Dev server CLI | `web2py.py` → `gluon/widget.py:660 start()` → `console.py` (argparse, `:64-756`) → `main.HttpServer` (`main.py:722`) → `rocket3.Rocket3(appfactory(wsgibase))` |
| WSGI callable | `gluon.main.wsgibase` (`main.py:285`), wrapped optionally by `appfactory` (`:637`, access log + cProfile) |
| Production | `handlers/wsgihandler.py` (`application = wsgibase`), `gunicorn gluon:wsgibase` |
| Shell / scripts | `-S app[/c/f]`, `-M`, `-R file`, `-A args` → `gluon/shell.py:216 run()` / `env()` |
| Scheduler | `-K app[:groups]` (standalone; multiprocessing per app, `widget.py:621`), `-X` alongside web server |
| Cron | `-Y`, `--soft_cron`, `-C`, `--crontab`, `--cron_threads` → `gluon/newcron.py` |
| Tests | `--run_system_tests [--with_coverage]` → `os.execv python -m unittest -c gluon.tests`; `-T` doctests |
| GUI | Tkinter `web2pyDialog` **still present** (`widget.py:115-606`), used when no `--no_gui` and password is `<ask>` |
| Programmatic | `gluon.shell.exec_environment` (**in shell.py:68, not compileapp**) |

**Bootstrap side effects:** `import gluon` → `import_packages()` (`gluon/__init__.py:137-149`, inserts submodule paths into `sys.path` + `sys.modules` aliases) → imports `gluon.main`, which at import time creates folders, sets `locale LC_CTYPE=C`, loads `logging.conf`, monkeypatches `pydal.get_default_represent`, and runs `load_routes()`.

## 3. HTTP request lifecycle (`gluon/main.py:285-600`)

1. `current.__dict__.clear()`; construct `Request(environ)`, `Response()`, `Session()` (`:314-317`).
2. `fixup_missing_path_info` → `url_in()` (`rewrite.py:201`): parametric `map_url_in` if `routers`, else pattern `regex_url_in`. Resolves app/controller/function/ext/args, static file, static version.
3. **Static:** `response.stream()` → `stream_file_or_304_or_206` **always raises `HTTP`**; the handler returns immediately (no session, no DB, no onerror).
4. Populate request: `client` (X-Forwarded-For first, `:137`), `is_local`, `is_https` (includes `X-Forwarded-Proto`, `:381`), `ajax`, `cid`; content type.
5. Missing app → redirect/404; `DISABLED` file → 503; `create_missing_app_folders`; parse cookies.
6. `session.connect(request, response)` (skipped if `web2py_disable_session`).
7. `serve_controller` (`:160-223`): `build_environment` → `run_models_in` → snapshot `_view_environment` → `run_controller_in` → if dict, `run_view_in` → **`raise HTTP(response.status, page, **headers)`**. Success is delivered as an exception.
8. `except HTTP` (success & redirects): `_try_store_in_db` → **commit** via `BaseAdapter.close_all_instances("commit")` (or `do_not_commit`/`custom_commit`) → `_try_store_in_cookie_or_file` (after commit, intentionally) → component headers (`web2py-component-flash/content/command`) → cookie flags → `cookies2headers`.
9. `except RestrictedError`: log ticket (file tickets before rollback; DB tickets after) → rollback (`_custom_rollback` or `close_all_instances("rollback")`) → HTTP 500 with ticket id.
10. Bare `except`: rollback, `RestrictedError("Framework",…).log()`, 500.
11. `finally`: close session file; `session._unlock`.
12. `try_rewrite_on_error` (`rewrite.py:256`): status ≥399 matched to `routes_onerror` → **recursive `wsgibase` call** (guard `__ROUTES_ONERROR__`) or 303.
13. Soft-cron tick; `http_response.to(start_response)` (`http.py:126`).

**Execution environment** (`compileapp.py:391-473`): base namespace = `html.__all__` + `validators.__all__` + HTTP, redirect, DAL, Field, SQLDB, SQLField, SQLFORM, SQLTABLE, LOAD; per request adds `request, response, session, T, cache, local_import`; sets `current.*`; `custom_import_install()`.
**Models:** sorted by **directory depth, then alphabetical**; filtered by `response.models_to_run` regexes (`^\w+\.py$`, `^c/\w+\.py$`, `^c/f/\w+\.py$`), re-evaluated each iteration; `appadmin` runs all models. Cached by mtime via `cfs.getcfs`.
**Controllers:** exposed if `REGEX_EXPOSED = ^def\s+(_?[a-zA-Z0-9]\w*)\( *\)\s*:` (`:548`) — column-0, **no parameters**, at most one leading underscore (`_foo` **is exposed**).
**Views:** `c/f.ext` → fallback `generic.ext` only if `response.generic_patterns` matches (default `["*"]`; welcome narrows to local/non-production). yatl `parse_template` → `compile2` → `restricted()` (`exec`). Non-compiled views are re-parsed every request.
**Compiled apps:** if `compiled/` exists, **only** `.pyc` runs (per-function controller pyc; `read_pyc` checks `MAGIC_NUMBER`).
**`restricted()`** (`restricted.py:304`) = plain `exec(ccode, env)` — no sandbox despite the name.

## 4. Major subsystems

| Subsystem | Location | Key facts |
|---|---|---|
| Routing | `gluon/rewrite.py` | Pattern (`routes_in/out`, regex) vs parametric (`routers`); per-app `routes.py`; `exec` of routes files (`:379`); separate `THREAD_LOCAL`; `routes_apps_raw` only in pattern mode |
| Request/Response/Session | `gluon/globals.py` | Lazy `body/vars` (multipart via `contrib.multipart`, JSON auto-parse); `Response.stream/download/render/include_files/enable_csp/toolbar`; `current = threading.local()` (`:99`) |
| Sessions | `globals.py:1156-1754` | Backends: file (exclusive portalocker **for whole request**), DB (`web2py_session_<app>`, blob), cookie (AES-CBC+HMAC-SHA256 via `utils.secure_dumps`), redis/memcache via contrib. **Pickle everywhere; unrestricted unpickle by default** (`safe_unpickle=False`, opt-in `SafeUnpickler`). Change detection = md5 of pickle. HttpOnly + SameSite=Lax default |
| Storage | `gluon/storage.py` | `Storage` missing key → `None` for both `.x` and `['x']`; `List` (`request.args(i, cast, otherwise)`); `Settings/Messages` lockable; unused `FastStorage` |
| Templates | yatl submodule | `{{=x}}` → `response.write(x)` → `xmlescape` (`html.py:135`) unless `.xml()`; `eval` of include names, `exec` of rendered code |
| HTML helpers | `gluon/html.py` | `XmlComponent/DIV/XML/URL/FORM/BEAUTIFY/MENU`; URL signing HMAC-SHA1 with per-login key; `verifyURL` constant-time |
| Forms | `html.FORM`, `sqlhtml.SQLFORM` | `_formkey` one-time (keeps last 10), constant-time compare. Newer `gluon/form.py Form` uses reusable per-form key. `SQLFORM.grid` ≈1137-line static method |
| Validators | pydal `validators.py` (5703 L) | `CRYPT` default `pbkdf2(1000,20,sha512)`; `LazyCrypt.__eq__` non-constant-time |
| Auth | `gluon/authapi.py` (AuthAPI, dict-in/out, **no CSRF**) ← `gluon/tools.py:Auth` | Tables: auth_user/group/membership/permission/event (+auth_cas if cas_domains, +auth_token if enable_tokens); 2FA (email code / TOTP hooks); `AuthJWT`; decorators `requires_*`; impersonation pickles session |
| Other tools | `tools.py` | Mail (+DKIM), Recaptcha2, Crud (no deprecation warning), Service (json/xml/rpc/soap/amf), PluginManager, Wiki, fetch/geocode (plain http) |
| Cache | `gluon/cache.py` | `CacheInRam` (global lock), `CacheOnDisk` = **one pickle file per key** + portalocker (not shelve); `cache.action` keyed md5; memcache on GAE |
| Scheduler | `gluon/scheduler.py` | DB-backed; tables task/run/worker/task_deps; worker = heartbeat thread + `multiprocessing.Process` per task; JSON args; ticker election (FIXME deadlock `:1463`) |
| Errors/tickets | `gluon/restricted.py` | `RestrictedError` + `snapshot()`; `TicketStorage` file (`errors/`) or DB; pickle dump, **safe_load** with whitelist on read |
| i18n | `gluon/languages.py` | `ast.literal_eval` for language files |
| Cron | `gluon/newcron.py` | hard/soft/external; pickle lock file |
| DAL | pydal via `gluon/dal.py` | Adds web2py serializers, `uuid`, representers, contrib drivers; commit/rollback via `BaseAdapter.close_all_instances` (pydal `connection.py:205`) |

## 5. Dependency relationships

```
web2py.py → widget → console, main(HttpServer→rocket3), shell, newcron, scheduler
main.wsgibase → rewrite, globals, compileapp, http, restricted, streamer, fileutils, pydal.BaseAdapter
compileapp → html, validators(→pydal), dal(→pydal), sqlhtml, cache, languages, custom_import, cfs, restricted, template(→yatl)
globals → storage, utils(crypto), http, streamer, recfile/portalocker, serializers, html
tools/authapi → dal, validators, html, sqlhtml, utils, storage, globals.current, contrib.login_methods
dal → pydal, sqlhtml (top-level, dal.py:17), serializers, utils
sqlhtml → html, validators, storage, globals, http, serializers, utils (top-level); dal only lazily inside a function (sqlhtml.py:2306-2307, "avoid circular references")
scheduler → dal, shell.env (executor), storage, json
gluon/__init__ → imports main ⇒ importing *anything* in gluon triggers main's side effects
```
Everything reaches request state through `current` (thread-local) or the injected env.

Note: the top-level edge is `dal → sqlhtml`, not the reverse. `import gluon.dal` therefore also loads `sqlhtml` (and, through it, `globals`, `html`, `serializers`, etc.). See `docs/architecture/14-dependency-map.md`.

## 6. Critical files
`gluon/main.py`, `compileapp.py`, `globals.py`, `rewrite.py`, `restricted.py`, `storage.py`, `http.py`, `utils.py` (crypto), `html.py`, `sqlhtml.py`, `tools.py` + `authapi.py`, `cache.py`, `scheduler.py`, `fileutils.py` (credentials, folder creation), `custom_import.py`, `cfs.py`, `__init__.py` (package bootstrap), `widget.py` + `console.py` + `shell.py` (CLI), `gluon/packages/pydal/pydal/{validators,objects,connection}.py`, `gluon/packages/yatl/yatl/template.py`, `applications/admin/models/access.py`.

## 7. Compatibility mechanisms (must be preserved)
- Injected global namespace for models/controllers/views (incl. `SQLDB`, `SQLField`, `local_import`).
- `gluon/sql.py`, `gluon/dal.py`, `gluon/validators.py`, `gluon/template.py`, `gluon/sanitizer.py` shims so `from gluon.X import …` keeps working after code moved to submodules.
- `import_packages()` `sys.modules` aliasing of pydal/yatl/rocket3.
- `custom_import` (app `modules/` importable, reload-on-change).
- Compiled-app `.pyc` layout and `read_pyc` magic handling.
- Legacy crypto: `secure_loads_deprecated` (HMAC-MD5 cookies), `LazyCrypt` unsalted hash recognition.
- `Storage` returning `None`; `copyreg` pickling of `Storage`/`Session`/`XML`.
- Pattern and parametric routers coexisting; `routes_onerror`, `routes_apps_raw`.
- Deprecated CLI option aliases (~32 in `console.py`).
- `Crud`, `reset_password_deprecated`, `form_factory`, `SQLFORM` formstyles back to table3cols.
- Byte-identical `appadmin.py` in all three apps.

## 8. Legacy areas
- **Py2 remnants that break on Py3** [reported]: `gluon/admin.py:504` bare `urlopen` [verified, never imported → `upgrade()` always fails]; admin `controllers/default.py:417,2021,2049` same; `webservices.py:89` `unicode`, `:74` `StringIO(bytes)`; `wizard.py:522,532` `urllib.urlopen`; `handlers/gaehandler.py` `cPickle` + missing `gluon.admin.create_missing_folders`; `handlers/isapiwsgihandler.py` Py2 `print`; `anyserver.py` default `rocket` imports nonexistent `gluon.rocket`; `web2py_on_gevent.py` undefined names.
- `gluon/contrib/`: 242 `unicode`, 43 `basestring`, 36 `xrange`, 55 `PY2` references.
- Tkinter GUI, `messageboxhandler` Tkinter branch, `shell.py` `raw_input` shim, `widget.py` Py2.7/3.5 warnings, py2exe paths.
- `tox.ini` (py27, unittest2), Makefile `src` target referencing missing files.
- Pre-yatl/pydal APIs kept as shims; Crud; SOAP/AMF services; payment gateway contribs; GAE-specific paths (`gae_memcache`, `datastore`).

## 9. High-risk areas
**Security**
1. Pickle-based sessions with **unrestricted unpickle by default** (file/DB/cookie) — any write access to session store or leaked cookie key ⇒ RCE. `SafeUnpickler` exists but opt-in.
2. **Cookie sessions likely broken** [verified by reading]: `secure_dumps` returns bytes stored into `SimpleCookie` (`globals.py:1626-1631`), read back as str, then `secure_loads` does `str.count(b":")` (`utils.py:247`) → TypeError. Not covered by a round-trip test.
3. `is_https` trusts `X-Forwarded-Proto` unconditionally (`main.py:381`) — admin "secure channel" gate bypassable when not behind a proxy (password still required).
4. Admin password compare non-constant-time (`access.py:64` [verified]); `LazyCrypt ==` non-constant-time; PBKDF2 only 1000 iterations.
5. `admin/controllers/webservices.py` `attach_debugger` default authkey `'secret password'`; admin `debug.execute` = arbitrary Python (by design, admin-only).
6. Welcome `appconfig.ini` `host.names = …, *:*, *` defeats `Auth.url` host allowlist.
7. `trusted_lan_prefix` is compared against different client identities: admin matches it against `request.client` (`access.py:25-26`), which is derived from `X-Forwarded-For` (`main.py:137-157`), while appadmin matches it against `remote_addr` (`appadmin.py:24-28`). The setting itself is live: `Request.__init__` copies `global_settings` into `request.env` (`globals.py:317`), so a `global_settings.trusted_lan_prefix` (commented example at `settings.py:51`) reaches `request.env.trusted_lan_prefix`.
8. `AuthAPI` explicitly has no CSRF protection; `gluon/form.py Form` formkey reusable.
9. `restricted()` is not a sandbox (name misleading).

**Correctness / maintainability**
10. `response.custom_commit` read in `main.py:497` but `Response` initializes `_custom_commit` (`globals.py:671`) [verified] — asymmetric with `_custom_rollback`.
11. Control flow by exception (`raise HTTP` on success); recursive `wsgibase` for `routes_onerror`.
12. Import-time side effects in `gluon.main` (folder creation, locale, logging config, monkeypatch).
13. Session file locked for entire request (serializes parallel AJAX).
14. `SQLFORM.grid` (~1137 lines), `SQLFORM.__init__`/`accepts` (~360 each), `tools.py` 7.7k lines.
15. Scheduler: ticker deadlock FIXME; `TASK_STATUS` omits `ASSIGNED`; tests skipped on 3/4 CI Pythons.
16. Parametric router suspected dead branch (`rewrite.py:1502` compares method to `False`) and `:1489` uses bool `app` as key [suspected].
17. `Session.connect` discards user-supplied `separate` callable (`globals.py:1335`) [reported].
18. DB tickets store pickle bytes in a `text` field [suspected adapter-dependent].
19. Version metadata inconsistent; no packaging metadata; pydal requires ≥3.10 while docs/CI claim 3.9.

## 10. Existing test architecture
- **Framework:** stdlib `unittest`; no pytest config. Runner `python web2py.py --run_system_tests [--with_coverage]` (Makefile `tests`/`coverage`). `gluon/tests/__init__.py` star-imports modules.
- **Env switches:** `DB` (default `sqlite:memory`), `W2P_SKIP_SCHEDULER_TESTS`, `TRAVIS`/`APPVEYOR`.
- **CI:** GitHub Actions (ubuntu; Py 3.9/3.11/3.12 skip scheduler, 3.14 full; mysql:8 + redis:7 services) and AppVeyor (Windows, same matrix). Coverage → codecov (`gluon/tests/coverage.ini`, excludes contrib/packages; target 70–100).
- **MySQL service is effectively unused** — `test_dal.test_mysql` only runs under `TRAVIS`.
- **42 tests never run:** 6 modules are not imported in `gluon/tests/__init__.py` [verified]: `test_restricted` (20), `test_login_methods` (13), `test_oauth20_account` (4), `test_update_languages` (4), `test_main` (1), `test_rocket` (0).
- **Integration:** `test_web` spawns a real server on :8000 and drives it with `contrib.webclient`; `test_cron`, `test_scheduler` spawn processes; `test_redis` needs Redis.
- **Submodule suites:** pydal ~472 tests (multi-DB tox), yatl 9, rocket3 2 — not run by web2py CI.

| Module | Coverage |
|---|---|
| tools/Auth (169), sqlhtml (95), html (85), globals (46), appadmin (44), router+routes (36) | Strong |
| storage, scheduler, serializers, fileutils, utils | Moderate |
| restricted (20 tests exist in `test_restricted.py`, but the module is not imported by the runner, so they never run) | **None under the official runner** |
| **main.wsgibase** (1 test, not run), **compileapp** (11, mostly path/plugin), **cache** (action/lazy_cache TODO), languages (7), authapi (8) | **Weak** |
| shell, widget, console, custom_import, cfs, newcron (3), handlers, anyserver, admin controllers, cookie session round-trip | **None** |

## 11. Technical reference vs. source code

| Reference claim | Actual source |
|---|---|
| PyDAL at `gluon/packages/dal` | Path is `gluon/packages/pydal` (submodule *named* `gluon/packages/dal`) |
| `gluon/rocket.py` | Removed; `gluon/packages/rocket3` submodule |
| `template.py`, `sanitizer.py`, `validators.py` are engine implementations | 1–9 line re-exports of yatl/pydal |
| Root `VERSION` file | Absent; `gluon/version.py` (and conflicting `__init__.__version__`) |
| `deposit/` in repo | Created at runtime by `create_missing_folders` |
| Models in "strict alphabetical order" | Depth-first then alphabetical, filtered by `models_to_run` (mutable mid-run), appadmin runs all |
| Functions starting with `__` are private | Also any function with parameters; single `_foo` **is public** |
| `exec_environment` in compileapp | In `gluon/shell.py:68` |
| `pydal.dbapi.RestAPI/Policy` | `pydal/restapi.py`; no `dbapi` module; unused by gluon |
| `cache.disk` shelve (implied) | One pickle file per key + portalocker |
| Python 3.9–3.12 | Docs "3.9+", CI up to 3.14, bundled pydal `requires-python >=3.10` |
| "Py2 modules completely removed" | Core yes; handlers/admin controllers/contrib retain Py2 code (some broken) |
| Session lock → "disk sessions lock the file" | True, and lock spans whole request (exclusive) |
| Commit is "db.commit() on all connections" | `BaseAdapter.close_all_instances("commit")`, with `do_not_commit`/custom hooks; session DB store happens **before** commit, file/cookie **after** |
| Tickets: "rollback, then ticket" | File tickets are logged **before** rollback; DB tickets after |
| Static pipeline step via `stream_file_or_304` | `stream_file_or_304_or_206` (range support); raised as HTTP |
| `anyserver.py` supports rocket | Default `rocket` server is broken (imports `gluon.rocket`) |
| Auth tables: 5 | 5 base + optional `auth_cas`, `auth_token` |
| CSRF: formkey one-time | True for `FORM/SQLFORM`; not for `gluon/form.py Form`; none in `AuthAPI` |
| Handlers list (wsgi, gae, fcgi) | Also cgi, scgi, modpython, isapi, gevent; gae & isapi broken on Py3 |
| Reference omits | `gluon/authapi.py`, `gluon/form.py`, `console.py`, `cfs.py`, CSP (`enable_csp`), `safe_unpickle`, `AuthJWT`, `newcron` |

## 12. Areas requiring further investigation
1. Confirm cookie-session breakage with an end-to-end characterization test (first test to write).
2. Whether any real deployment relies on `response.custom_commit` (public vs `_custom_commit`).
3. Parametric router suspected bugs (`rewrite.py:1489`, `:1502`).
4. pydal ≥3.10 requirement vs Py3.9 CI — does CI actually pass on 3.9?
5. Baseline test run (populate `docs/ai-context/baseline.md`: Python version, pass/fail/skip counts) — not executed yet.
6. `custom_import.py` reload semantics and thread safety; `cfs` cache invalidation.
7. DB ticket storage of pickle bytes in `text` column across adapters.
8. Scheduler ticker election / deadlock FIXME and `ASSIGNED` status validation.
9. Thread-safety of `CacheInRam` global lock under Rocket's thread pool; `current` behaviour under gevent/eventlet (anyserver).
10. `languages.py` and `T` lazy objects in pickled sessions.
11. Full inventory of `gluon/contrib` still in use vs dead (login_methods, payment gateways, pyaes vs PyCryptodome).
12. Admin app attack surface review (webservices, debugger listener, git/pip install, `upgrade_web2py`).

