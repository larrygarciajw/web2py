# 13 — Legacy and Compatibility Mechanisms

## Purpose

This document catalogues the mechanisms that exist so that old applications and old deployments keep working (**[Compat]**, which must be preserved per `CLAUDE.md` and `docs/project-goals.md`). It separates them from code that is obsolete, dead or broken on Python 3 (**[Legacy]**). Every item has source evidence. **[Suspected issue]** marks a likely defect found by static reading that has not been run. **[Unverified]** marks claims that could not be confirmed.

How it was checked:
- Code was read statically.
- Syntax errors and `SyntaxWarning`s were found by calling `compile()` on source text only. No `gluon` import and no execution took place. The scan covered 334 files: `gluon/*.py`, `gluon/contrib/**`, `handlers/`, root `*.py`, `scripts/**`, `extras/**`, app `controllers`/`models`/`modules`, and `gluon/tests/`.

## Relevant source files
`gluon/{template,sanitizer,validators,dal,sql,settings,__init__,storage,utils,console,tools,sqlhtml,compileapp,custom_import,shell,widget,messageboxhandler,admin}.py`, `gluon/packages/pydal/pydal/validators.py`, `handlers/*`, `anyserver.py`, `applications/admin/controllers/{default,webservices,wizard,gae}.py`, `scripts/`, `tox.ini`, `Makefile`, `app.yaml`.

## Main classes / functions

### A. [Compat] Shim modules (old import paths → submodules)
| Module | Contents (entire file unless noted) |
|---|---|
| `gluon/template.py:1` | `from yatl.template import parse_template, render` |
| `gluon/sanitizer.py:1` | `from yatl.sanitizer import sanitize` |
| `gluon/validators.py:1-9` | `from pydal.validators import *`, plus `ValidationError, Validator, __all__, get_digest, simple_hash, translate` |
| `gluon/dal.py:12-48` | Re-exports pydal `DAL, Field, SQLCustomType, geo*, DRIVERS, Migrator, InDBMigrator, Expression, Query, Row, Rows, Set, Table`. **Mutates pydal globally**: `DAL.serializers`, `DAL.uuid`, `DAL.representers`, `DAL.Field`, `DAL.Table` (`:21-25`). Registers contrib drivers `pymysql` and `pypyodbc` when pydal lacks them (`:28-41`). The `pg8000` fallback imports `gluon/contrib/pg8000`, which does not exist, and fails silently (`:42-48`). **[Legacy]** |
| `gluon/sql.py:13-30` | `SQLDB = GQLDB = DAL`, `SQLField = Field`, `SQLTable = Table`, `SQLXorable = Expression`, `SQLQuery`, `SQLSet`, `SQLRows`, `SQLStorage = Row`. Note that `__all__ = ["DAL","Field","DRIVERS"]` (`:13`), so `from gluon.sql import *` does **not** export `SQLDB`. |
| `gluon/settings.py:16` | `settings = global_settings  # legacy compatibility`. Still used by `applications/admin/controllers/gae.py:19`. |

### B. [Compat] Package bootstrap / `sys.modules`
- `import_packages()` (`gluon/__init__.py:137-149`) inserts `gluon/packages/{pydal,yatl,rocket3}` at `sys.path[0]` and sets `sys.modules[pkg] = builtins.__import__(pkg)`. The same name maps to itself. This is not aliasing to a different name. The effective mechanism is the `sys.path` insertion, which makes top-level `import pydal` resolve to the submodule.
- **[Legacy]** The IDE-only `if 0:` block (`gluon/__init__.py:161-181`) imports `from .languages import translator` (`:164`). No such name exists in `gluon/languages.py`. The block never executes.

### C. [Compat] Injected environment names
- `SQLDB = DAL` and `SQLField = Field` (`gluon/compileapp.py:398-399`). The byte-identical bundled `appadmin.py:76` uses `isinstance(value, SQLDB)`.
- `local_import` (`compileapp.py:464-468`). **[Suspected issue]** The `local_import_aux` body appears broken on Py3 (see doc 05, open question 1).
- `custom_import` keeps a Py<3.3 `_DEFAULT_LEVEL` branch (`custom_import.py:43`), which is dead. It also keeps the backward-compatibility `rstrip` on the folder path (`:76-77`).

### D. [Compat] `Storage` semantics and pickling
- `Storage` (`gluon/storage.py:33-66`) sets `__getitem__ = __getattr__ = dict.get` (`:60-61`). A missing key returns `None` for both `s.x` and `s['x']`.
- The docstring claims "setting obj.foo = None deletes item foo" (`:36`). That is false: `__setattr__ = dict.__setitem__` (`:58`) stores `None`. The docstring also uses Py2 `print o.a`. **[Legacy]** documentation.
- `copyreg.pickle(Storage, pickle_storage)` (`:145-149`). The `__getnewargs__` lambda (`:62`) calls `getattr(dict, self)`, which would raise. It is unreachable because copyreg takes precedence. **[Legacy]**
- `StorageList` (`:153-167`) returns and stores `[]` for a missing key. `FastStorage` (`:211`) is unused by gluon.
- Other copyreg registrations that sessions, tickets and cache rely on:
  - `Session` (`globals.py:1761`)
  - `XML` (`html.py:762`)
  - `__tag_div__` (`html.py:1366`)
  - `lazyT` (`languages.py:444`)
  - pydal `Row` (`cache.py:63`)

### E. [Compat] Legacy crypto formats
- **Cookie / secure data.** `secure_loads` dispatches to `secure_loads_deprecated` when the payload has exactly one `b":"` (`gluon/utils.py:247-256`). The deprecated format is `<hmac-md5 hex>:<b64(IV+AES-CBC)>`. Its key is space-padded (`__pad_deprecated`, `:286-288`), and its HMAC key defaults to `sha1(key).hexdigest()` (`:328-334`). The current format is `hmac256:<sig>:<data>` (`:235`).
  - **[Suspected issue]** In `secure_dumps_deprecated`, a `str` `hash_key` is encoded to bytes (`:298-299`) and then `.encode` is called again (`:307`), which raises `AttributeError`. It works only with the default `hash_key`, which is what the tests use (`gluon/tests/test_utils.py:143-215`).
  - Dumps pads with PKCS7 `pad()` (`:305`) while loads strips spaces (`:343`). The round-trip still works because `pickle.loads` ignores trailing bytes, and the tests cover the compressed case (`test_utils.py:203`).
- **Passwords.** `LazyCrypt.__eq__` (`pydal/validators.py:4504-4536`) accepts `alg$salt$hash`, or an **unsalted** hex digest whose algorithm is guessed from its length via `DIGEST_ALG_BY_SIZE` (32→md5, 40→sha1, 56→sha224, 64→sha256, 96→sha384, 128→sha512, `:4442-4449`). The comparison uses `==`, which is not constant-time (`:4536`).
  - **[Suspected issue]** `__str__` splits the key with `split(":", 1)` (`:4488`), while `__eq__` uses `split(":")[1]` (`:4518`). Keys containing more than one `:` would hash differently. The code is in the pydal submodule, which must not be edited here.
- `unpad` keeps a Py2 `ord` branch (`utils.py:212-213`). **[Legacy]**

### F. [Compat] Deprecated CLI aliases (`gluon/console.py:74-91`)
There are 16 deprecated spellings. Each emits a warning (`parse_args`, `:824-839`):

`--debug`→`--log_level`, `--nogui`→`--no_gui`, `--ssl_private_key`→`--server_key`, `--ssl_certificate`→`--server_cert`, `--interfaces` (hint `--interface`), `-n` / `--numthreads` / `--minthreads`→`--min_threads`, `--maxthreads`→`--max_threads`, `-z`, `--shutdown_timeout` (no replacement), `--profiler`→`--profiler_dir`, `--run-cron`→`--with_cron`, `--softcron`→`--soft_cron`, `--cron`→`--cron_run`, `--test`→`--run_doctests`.

In addition:
- 25 hyphenated aliases (`--no-gui`, `--log-level`, …) are accepted but hidden from help (`:99-126`). They are not deprecated.
- An integer `-D` level is deprecated (`:840-842`).
- **[Suspected issue]** For `-z`, the hint is `None`, so `dest = "z"` (`:830`). The option's real dest is `shutdown_timeout` (`:568-573`), so `getattr(options, "z")` (`:834`) would raise `AttributeError` when `-z N` is passed.
- Only exact tokens are detected, so `--debug=10` is not warned.

### G. [Compat] Deprecated-but-present APIs
- `Crud` (`gluon/tools.py:4966`, `# pragma: no cover`, no runtime warning). It is still used by `applications/admin/models/db.py:9`. It is tested by `TestCrud` (`test_tools.py:2194`).
- `Auth.reset_password_deprecated` (`tools.py:3822`). `retrieve_password` routes to it whenever `reset_password_requires_verification` is false (`:4316-4319`), and that setting **defaults to False** (`:1652`). The deprecated flow emails a newly generated plaintext password (`:3892`). Its tests are TODOs (`test_tools.py:1405`, `:1421`).
- `form_factory = SQLFORM.factory` (`sqlhtml.py:4340`, "deprecated").
- Formstyles `table3cols, table2cols, divs, ul, bootstrap, bootstrap3_*, bootstrap4_*, inline` (`sqlhtml.py:1479-1490`). The framework default remains `Response.formstyle = "table3cols"` (`globals.py:675`), while welcome uses `bootstrap4_inline`.
- The compiled-app legacy names `models_*.pyc` and `views.<c>.<f>.pyc` / `views.generic.pyc` (`compileapp.py:577`, `:769-774`).
- **[Legacy]** The `read_pyc` 12-byte header branch for Py<3.7 is dead (`compileapp.py:484`).

### H. [Legacy] Python 2 remnants. Each was verified by reading.

**Broken or dead at runtime (NameError, AttributeError, TypeError on Py3):**

| Location | Evidence | Effect |
|---|---|---|
| `gluon/admin.py:504` | `urlopen(full_url)`; only `urllib.request` is imported (`:17`) | `upgrade()` always returns `(False, NameError)` |
| `admin/controllers/default.py:416-417` | `StringIO()`, `urlopen`, both undefined (not in `gluon.admin`, not in admin models `0_imports.py`) | `pack_exe` raises NameError |
| `admin/controllers/default.py:2021` | `urlopen` inside a bare `except` → `session.plugins = []` → `session.plugins["results"]` (`:2028`) | **[Suspected issue]** the `plugins()` page probably always raises `TypeError` (list indices) |
| `admin/controllers/default.py:2049` | `plugin_install(app, urlopen(source), …)` | NameError → ticket |
| `admin/controllers/webservices.py:74` | `io.StringIO(base64.b64decode(data))` | TypeError (bytes) |
| `admin/controllers/webservices.py:87` | `isinstance(authkey, unicode)` | NameError |
| `admin/controllers/wizard.py:522`, `:532` | `urllib.urlopen(...)` inside `try/except Exception` | layout and plugin download silently skipped |
| `handlers/gaehandler.py:30`, `:99` | `import cPickle`; `gluon.admin.create_missing_folders()` (not defined in `gluon.admin`) | ImportError on Py3; the Py2 `webapp` API (`:48-49`) |
| `handlers/isapiwsgihandler.py:27` | `print "USAGE…"` | SyntaxError |
| `handlers/web2py_on_gevent.py:109` | `print '…'` | SyntaxError |
| `handlers/modpythonhandler.py:202` | `raise a, b, c` | SyntaxError |
| `anyserver.py:59`, `:66` | `from gluon.rocket import …` (module removed) | `rocket` servers are broken |
| `scripts/` | 14 files fail to compile (Py2 `print`): `check_lang_progress, cpdb, cpplugin, dict_diff, extract_{mssql,mysql,oracle,pgsql,sqlite}_models, fixws, lang_update_from_langfile, parse_top_level_domains, rmorphans` | unusable on Py3 |
| `extras/build_web2py/web2py.site_{27,37}.py:31` | the compile fails with an invalid character, probably a non-UTF-8 encoding | **[Unverified]** |
| `compileapp.py:440-459` | the Jython hack references an undefined `builtin` | dead (`is_jython` is false on CPython) |
| `compileapp.py:361-388` | the commented `imp`-based "OLD IMPLEMENTATION" | dead text |

**Harmless remnants (shims or guards):**
- `shell.py:44` `raw_input = input`
- `tools.py:46` `from urllib import request as urllib2`
- `cfs.py:16` and `cache.py:22` `import _thread as thread`
- `messageboxhandler.py:6-9` Tkinter/tkinter switch
- `widget.py:41-47` "requires Python 2.7/3.5" warning, which never fires on 3.x ≥ 3.5
- `widget.py:873` py2exe comment
- `settings.py:47` `is_py2 = False`
- `from __future__ import print_function` in `gluon/{admin,console,scheduler,widget}.py` (line 13 or 37), 30 `gluon/contrib` files and `scripts/sessions2trash.py`

The Tkinter GUI `web2pyDialog` (`widget.py:115-606`) is [Compat]: it is still reachable from `start()`.

**`gluon/contrib` counts** (whole-word `grep -ow` occurrences in `*.py`; many are inside `PY2` guards or comments):

| Word | unicode | basestring | xrange | iteritems | cPickle | urllib2 | StringIO | PY2 |
|---|---|---|---|---|---|---|---|---|
| Occurrences | 125 | 44 | 36 | 6 | 5 | 52 | 29 | 44 |
| Files | 24 | 22 | 6 | 4 | 4 | 7 | 12 | 16 |

`gluon/contrib` has 54 entries and `login_methods/` has 23.

### I. [Legacy] GAE-specific paths
- `global_settings.web2py_runtime_gae` is set **only** by `handlers/gaehandler.py:53`, which is broken on Py3 (see H). `Request` copies `global_settings` into `request.env` (`globals.py:316-317`), so the flag is effectively always falsy.
- The supported GAE path is `app.yaml` (`runtime: python311`, `entrypoint: gunicorn … gluon:wsgibase`). It never sets the flag. Welcome detects GAE via the `GAE_APPLICATION` environment variable and `DAL("firestore")` instead (`welcome/models/db.py:35-47`).
- The GAE branches that therefore look dead include:
  - `Cache` → `gae_memcache` (`cache.py:573-576`)
  - `read_pyc` skipping the magic check (`compileapp.py:496`)
  - `check_credentials` Google users (`fileutils.py:514-526`)
  - `create_missing_*` skips (`fileutils.py:583`, `:596`)
  - 15 gluon/app files reference the flag in total
- The contrib modules `gae_memcache.py` and `gae_retry.py` import `google.appengine.*` (the legacy runtime).

### J. [Legacy] Tooling staleness
- `tox.ini` targets `envlist = py27, pypy` using `unit2` and `unittest2`.
- `Makefile`: `build`/`install` run `python -m build` / `pip install .`, but there is no `setup.py` or `pyproject.toml`. The `src` target zips `fabfile.py`, `README.markdown`, `CHANGELOG`, `NEWINSTALL`, `VERSION` and `MANIFEST.in`, and none of these exist. `NEWINSTALL` is created by the target itself.
- `gluon/__init__.py:13` `__version__ = "3.0.3"` vs `gluon/version.py` 3.3.3.

### K. SyntaxWarnings (invalid escapes, and `is` with a literal)

55 warnings came from the compile-only scan:

| Area | Locations |
|---|---|
| admin controllers (exec'd at runtime, so they warn per compile) | `gae.py:46,53,67`, `openshift.py:38`, `webservices.py:23,29` |
| gluon/contrib | `feedparser.py` (16 lines), `webclient.py:31`, `populate.py:89-121`, `login_methods/{janrain,rpx}_account.py:95`, `memcache/memcache.py:154`, `pyrtf/Elements.py:702`, `sms_utils.py:116`, `pyrtf/Renderer.py:92` (`is not` with int) |
| tests | `test_router.py:1884`, `test_routes.py:112` (inside a string), `test_tools.py:2818,2824`, `test_scheduler.py:1003,1017` (`is` with str) |
| scripts / extras | `autoroutes.py`, `contentparser.py`, `extract_mysql_models.py`, `import_static.py`, `standalone_exe_cxfreeze.py`, `build_web2py.py:69` |

The baseline (`docs/ai-context/baseline.md`) saw a subset of these at test time. Invalid escapes are slated to become errors in a future Python release, and they would then break the admin controllers.

### L. Other process-global legacy side effects
- `gluon/tools.py:5528` `urllib2.install_opener(build_opener(HTTPCookieProcessor()))` runs at import time. It installs a cookie-keeping global opener for **all** `urllib.request.urlopen` calls in the process. **[Compat]**/**[Suspected issue]**
- The `shell.env()` `check_credentials` monkeypatch is permanent (`shell.py:174-177`). See doc 05.

## Execution flow
Not applicable (catalogue).

## Dependencies
The shims depend on the pinned submodules `pydal`, `yatl` and `rocket3`. `gluon/dal.py` depends on `gluon/contrib/pymysql` and `pypyodbc.py`.

## Side effects
- Importing `gluon.dal` mutates `pydal.DAL` class attributes.
- Importing `gluon.tools` installs a global urllib opener.
- `import gluon` → `import_packages()` changes `sys.path`.

## Compatibility constraints
**Must preserve (all [Compat]):**
- sections A–G
- the `settings` alias
- the copyreg registrations
- `Storage` returning `None`
- both crypto formats and unsalted hash recognition
- the CLI aliases
- `Crud`, `form_factory` and the formstyles
- the byte-identical `appadmin.py` (verified with `cmp` across welcome, admin and examples)

**Removable only with approval (all [Legacy]):** sections H–J. Several items in H are already non-functional.

## Related tests
- `test_utils.py:138-215` covers the deprecated secure dumps/loads.
- `test_tools.py:2194` covers `TestCrud`.
- `test_appadmin.py:38` imports `gluon.sql.SQLDB`.
- `test_storage.py` covers `Storage`.
- `test_compileapp.py:158` covers `check_new_version` with a mocked `urlopen`.

## Known gaps in test coverage
There are no tests for:
- `upgrade()`
- admin `plugins`, `install_plugin`, `pack_exe` and `webservices.install`
- deprecated CLI option handling (`console.parse_args`)
- `LazyCrypt` unsalted recognition
- `reset_password_deprecated` / `retrieve_password` (TODO)
- `gluon.sql` aliases beyond the import
- `handlers/*`
- `anyserver.py`
- `scripts/`

## Open questions
1. Is anything still deployed through `gaehandler.py`/the legacy GAE runtime? If not, the whole `web2py_runtime_gae` surface is dead. **[Unverified]**
2. `request.env` includes every `global_settings` key (`globals.py:317`), so a `global_settings.trusted_lan_prefix` set in `settings.py` (commented at `:51`) reaches `request.env` and is a live setting **[Current]**. Open point: admin matches it against `request.client` (from `X-Forwarded-For`), appadmin against `remote_addr` (see doc 11).
3. Is `retrieve_password` → `reset_password_deprecated` the intended default? It is a security-relevant compat default.

## Discrepancies with the technical reference
| Reference | Source |
|---|---|
| §18 "Py2 stdlib modules (`urllib2`, `cPickle`, `Queue`, `thread`) removed completely" | Core aliases `urllib.request as urllib2` (`tools.py:46`) and `_thread as thread` (`cfs.py:16`). `cPickle` remains in `gaehandler.py:30` and contrib. Broken Py2 code remains in admin, handlers and scripts (H). |
| §1 `gluon.sql` is "the DAL layer prior to PyDAL" | 30-line alias module over pydal (`sql.py:13-30`) |
| §4 `template.py` is the template parser/compiler | a one-line yatl re-export |
| §18 supports "Python 3.9 to 3.12+" | pydal requires ≥3.10 (baseline). `tox.ini` still lists py27. |

## Modernization considerations (optional)
- Characterize the §F `-z` path and the §E `hash_key` path before touching them.
- Treat the section H admin breakages as candidate bug fixes, each with its own test. They are separate from compat work.
