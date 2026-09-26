# 07 — PyDAL Integration

## Purpose

This document describes how web2py vendors, imports, patches and drives pydal (the DAL, validators and connection pool). It covers the submodule boundary, the `gluon/dal.py` and `gluon/sql.py` shims, per-request connection handling (commit/rollback), migrations, validator translation, and the pydal internals that gluon code relies on.

Every statement comes from reading the source at commit `cb91b60c` (pydal submodule at `6fd518e0`). Nothing was executed.

Labels: **[Current]** is behavior verified by reading. **[Compat]** is kept for old apps. **[Legacy]** is obsolete. **[Suspected issue]** is a likely defect based on static reading only. **[Unverified]** could not be confirmed.

## Relevant source files

| File | Role |
|---|---|
| `.gitmodules` | Declares the pydal submodule |
| `gluon/packages/pydal/` | Vendored pydal (`pyproject.toml`, `pydal/`, `tests/`) |
| `gluon/__init__.py` | `import_packages()` (`:137-149`) puts pydal on `sys.path` and in `sys.modules` |
| `gluon/dal.py` | web2py adaptations: serializers, uuid, representers, contrib drivers |
| `gluon/sql.py` | Legacy `SQL*` aliases |
| `gluon/validators.py` | 9-line re-export of `pydal.validators` |
| `gluon/main.py` | pydal monkeypatch (`:90-94`); commit/rollback in `wsgibase` (`:494-500`, `:543-552`, `:566-572`) |
| `gluon/compileapp.py` | `Validator.translator` (`:428`), `BaseAdapter.set_folder` (`:469`), `DAL`/`SQLDB` in the base environment (`:396-399`) |
| `gluon/shell.py` | Commit/rollback for `-S -M -R`; `--force_migrate`/`--fake_migrate` monkeypatch (`:265-279`) |
| `scripts/migrator.py` | Script that forces migration of all tables |
| `gluon/packages/pydal/pydal/connection.py` | `ConnectionPool`, `close()` (`:148`), `close_all_instances` (`:205`) |
| `gluon/packages/pydal/pydal/base.py` | `DAL.__new__` instance registry (`:200-225`), `DAL.__init__` (`:320`) |
| `applications/welcome/models/db.py` | Reference DAL setup for new apps |
| `gluon/tests/test_dal.py` | web2py-side DAL tests |

## Main classes / functions

### Vendoring

| Item | Evidence | Label |
|---|---|---|
| Submodule is **named** `gluon/packages/dal` but its **path** is `gluon/packages/pydal` | `.gitmodules:1-3` | [Current] |
| pydal version `1.20260520.0` | `gluon/packages/pydal/pydal/__init__.py:16` | [Current] |
| pydal declares `requires-python = ">=3.10"` | `gluon/packages/pydal/pyproject.toml:6` | [Current] |
| CI still runs Python 3.9 | `.github/workflows/tests.yml:23` | [Current] |
| No 3.10-only syntax (`match`, `X \| None` return hints) was found by grep in `pydal/` | grep only | [Unverified] that pydal really works on 3.9 |
| pydal package layout uses `backends/` and `backend_base.py`. There is **no** `pydal/adapters` package | `ls gluon/packages/pydal/pydal` | [Current] |

### Import mechanism

`import_packages()` (`gluon/__init__.py:137-146`) does the following for `pydal`, `yatl` and `rocket3`:
1. It inserts `gluon/packages/<name>` at **position 0** of `sys.path`, so the vendored copy shadows a pip-installed pydal.
2. It sets `sys.modules[name] = builtins.__import__(name)`. If `pydal` was already imported before `gluon`, `__import__` returns the module that is already in `sys.modules`, and the vendored copy is not used. **[Current]** (this follows from Python semantics; not tested).
3. On `ImportError` it raises `RuntimeError(MESSAGE)`, which suggests `git submodule update --init --recursive` (`:128-134`, `:145-146`).

### `gluon/dal.py` adaptations (all are class-level, process-wide mutations of `pydal.DAL`)

| Line | Change | Effect |
|---|---|---|
| `dal.py:21` | `DAL.serializers = {"json": custom_json, "xml": xml}` | Each `DAL.__init__` copies these into pydal's global `serializers._custom_` (`pydal/base.py:508-510`) |
| `dal.py:22` | `DAL.uuid = lambda x: web2py_uuid()` | pydal's default is `uuidstr` (`pydal/base.py:188`) |
| `dal.py:23` | `DAL.representers = {"rows_render": sqlhtml.represent, "rows_xml": sqlhtml.SQLTABLE}` | Used by `Rows.render` / `Rows.xml` (`pydal/objects.py:4052`, `:3508-3521`). This is why `gluon.dal` imports `gluon.sqlhtml` |
| `dal.py:24-25` | `DAL.Field = Field; DAL.Table = Table` | `db.Field` is used by `Session.connect` (`globals.py:1360`) and `TicketStorage` |
| `dal.py:28-34` | Registers `gluon.contrib.pymysql` if pydal found no `pymysql` | [Compat] |
| `dal.py:35-41` | Registers `gluon.contrib.pypyodbc` as `pyodbc` | [Compat] |
| `dal.py:42-48` | Tries `from .contrib import pg8000`. **`gluon/contrib/pg8000` does not exist**, so the bare `except: pass` always swallows the error | [Legacy] dead code |

`dal.py:14-15` re-export `InDBMigrator`, `Migrator`, `Expression`, `Query`, `Row`, `Rows`, `Set`, `Table` for `from gluon.dal import …` users. **[Compat]**

### `gluon/sql.py` aliases [Compat]

`SQLDB = GQLDB = DAL`, `SQLField = Field`, `SQLTable = Table`, `SQLXorable = Expression`, `SQLQuery = Query`, `SQLSet = Set`, `SQLRows = Rows`, `SQLStorage = Row` (`sql.py:22-30`). Only `DAL`, `Field` and `DRIVERS` are in `__all__` (`:13`). `SQLDB` and `SQLField` are also injected directly into every app environment (`compileapp.py:398-399`). `scripts/migrator.py` depends on `GQLDB`/`SQLDB` being present in the environment (`scripts/migrator.py:16-19`).

### `gluon/main.py` monkeypatch [Legacy]

`main.py:90-94` sets `pydal.get_default_represent = lambda value: value`. A grep of the current pydal finds **no reader** of `get_default_represent` (the only similar name is the private `SQLCompiler._default_represent`, `pydal/compilers/sql.py:514`). The patch is a no-op against this pydal version. **[Legacy]**

### Validators

- `gluon/validators.py:1-9` does `from pydal.validators import *` plus `ValidationError`, `Validator`, `__all__`, `get_digest`, `simple_hash` and `translate`. It has no web2py logic. **[Current]**
- `compileapp.py:428-430` sets **the class attribute** `Validator.translator = staticmethod(lambda text: None if text is None else str(T(text)))` on every request. pydal validators call `self.translator(self.error_message)` (`pydal/validators.py:181`, `:316`, etc.).
- **[Suspected issue]** `Validator.translator` is global to the process, but `T` belongs to one request. Under a threaded server, request B can overwrite the translator while request A is validating, so A's error messages can be translated into B's language. This is inferred from the code and not demonstrated by a test.

### `sqlhtml` / forms dependency on pydal internals

`gluon/sqlhtml.py:27-32` imports `CALLABLETYPES` (`pydal/backend_base.py:76`), `DEFAULT` (`pydal/_globals.py:24`), `default_validators`, `Reference`, `SQLCustomType`, `_repr_ref`, `bar_encode`, `merge_tablemaps`, `smart_query` (`pydal/helpers/methods.py:95,153,205,415`) and `Expression/Field/Row/Rows/Set/Table`. `SQLFORM`, `SQLTABLE` and `grid` work directly on these objects. See doc on forms.

### pydal RestAPI

`pydal/restapi.py` defines `Policy` (`:102`) and `RestAPI` (`:274`). A grep of `gluon/` and `applications/` (outside `gluon/packages`) finds **no import** of `restapi`/`RestAPI`. There is no `pydal.dbapi` module. **[Current]** available but unused by web2py.

## Execution flow

### Per request (connection lifecycle)

1. `build_environment` calls `BaseAdapter.set_folder(<app>/databases)` (`compileapp.py:469`). This stores `THREAD_LOCAL._pydal_folder_` (`pydal/connection.py:56-63`). A `DAL()` created in a model without `folder=` picks it up (`connection.py:223-225`).
2. `DAL.__new__` registers every instance in `THREAD_LOCAL._pydal_db_instances_[db_uid]` (`pydal/base.py:200-225`).
3. Connections are lazy. `ConnectionPool.get_connection` returns the thread-local connection, else pops one from the class-level `ConnectionPool.POOLS[uri]` when `pool_size > 0`, else opens a new one (`connection.py:70-108`). The pool is shared by all threads in the process and guarded by `GLOBAL_LOCKER`.
4. On success (`except HTTP`, `main.py:494-500`):
   - `response.do_not_commit is True` → `close_all_instances(None)`
   - `response.custom_commit` truthy → `close_all_instances(response.custom_commit)`
   - otherwise → `close_all_instances("commit")`
5. On `RestrictedError`, `response._custom_rollback()` or `close_all_instances("rollback")` runs (`main.py:546-549`). The framework catch-all does the same inside `try/except: pass` (`:566-572`).
6. `close_all_instances(action)` (`connection.py:205-221`) calls `db._adapter.close(action)` for every registered instance in the thread, clears both registries, and if `action` is callable calls `action(None)` once more at the end.
7. `close(action)` (`connection.py:148-203`) runs `commit`/`rollback` or `action(self)`. If that raises, it marks the connection as failed. It closes the cursor, recycles the connection into the pool if `pool_size` allows and the action succeeded, otherwise closes it, and finally clears the thread-local slot.

Notes:
- **[Suspected issue]** With `do_not_commit=True`, `close(None)` performs no action and `succeeded` stays `True`, so on a pooled adapter the connection goes **back into the pool with the transaction still open** (`connection.py:169-190`). The next request that pops it inherits the uncommitted work. Most drivers keep it open until the next commit or rollback. Not tested.
- **[Suspected issue]** A callable `custom_commit` is called once per adapter with the adapter, then once with `None` (`connection.py:220-221`). Also, `Response.__init__` defines `_custom_commit` (`globals.py:671`) while `main.py:497` reads `custom_commit`. This asymmetry is already listed in `architecture-report.md` §9.10.
- SQLite ignores pooling: the SQLite adapter forces `self.pool_size = 0` (`pydal/backends/sqlite.py:45`). So welcome's `pool_size = 10` has no effect with the default SQLite URI. **[Current]**

### Shell and scheduler

| Context | Commit behavior | Evidence |
|---|---|---|
| `-S app -M -R file` | `close_all_instances("commit")` after the script; `"rollback"` on exception or `SystemExit` | `shell.py:312-331` |
| `-S app -M` with `python_code` | Same pattern | `shell.py:332-345` |
| `-S app --force_migrate` | Runs `scripts/migrator.py`, then commit or rollback | `shell.py:346-359` |
| `-S app/c/f` | `exec("print(f())")` then `return`: **no commit** | `shell.py:307-309` |
| Interactive shell (IPython/bpython/`code.interact`) | No automatic commit. The user must call `db.commit()` | `shell.py:360-402` |
| Scheduler task (`executor`) | Builds the env via `shell.env(import_models=True)` and runs the task. **No framework commit** after the task, so the task must commit itself. The worker process makes its own `db.commit()` calls | `scheduler.py:486-558`; e.g. `:754`, `:1023` |

### Migrations

- pydal writes one snapshot file per table named `<md5(uri)>_<tablename>.table` in the DAL folder (`pydal/migrator.py:379`; `_uri_hash` at `pydal/base.py:499`). In web2py this folder is `applications/<app>/databases/`, set by `set_folder`.
- `migrate`, `fake_migrate`, `migrate_enabled` and `fake_migrate_all` are `DAL.__init__` parameters (`pydal/base.py:320-344`). A table's `migrate=` may be a string prefix for the file name, which `Auth.define_tables(migrate='myprefix_')` documents (`tools.py:2493`).
- pydal's new "stale `.table` markers" `RuntimeError` (`pydal/base.py:351-392`) only fires when `folder` is passed explicitly to `DAL()`. web2py apps normally rely on `set_folder`, so `folder` is `None` and **the check does not run** for them. **[Current]**
- CLI: `--fake_migrate` (`console.py:347`) and `--force_migrate` (`console.py:354`) are passed to `shell.run` (`widget.py:754-755`). When `force_migrate` is set, `shell.run` (`shell.py:265-279`):
  - forces `c = "appadmin"` so all models run,
  - **replaces `DAL.__init__`** with a wrapper that overrides `migrate_enabled=True`, `migrate=True` and `fake_migrate=<flag>` for every `DAL()`,
  - never restores the original `__init__`, which is acceptable only because the process exits.
- `--fake_migrate` without `--force_migrate` does nothing: the wrapper is installed only inside `if force_migrate` (`shell.py:265`). **[Current]**
- Because `c = "appadmin"`, `shell.run` also executes `controllers/appadmin.py` module code (`shell.py:295-305`) before running the migrator. **[Unverified]** whether appadmin's access checks can abort that run.

### Tickets and sessions in DB

- `Session.connect(db=…)` defines `web2py_session_<masterapp>` through `db.define_table` (`globals.py:1358-1371`). See doc 08.
- `request.tickets_db` is set only when `global_settings.web2py_runtime_gae` is truthy (`globals.py:1352-1353`) or by the admin ticket viewer (`applications/admin/controllers/default.py:1882`). That flag is set only by the legacy `handlers/gaehandler.py:53`, not by the modern GAE entrypoint `gunicorn gluon:wsgibase` (`app.yaml:14`). **[Current]**
- DB tickets use table `web2py_ticket_<app>` with a `text` `ticket_data` field holding pickle bytes (`restricted.py:137-181`). `_store_in_db` calls `reconnect()`, `commit()` and `close()` on the DB itself, independent of the request transaction (`:138-152`).

## Dependencies

pydal symbols that gluon core imports (outside tests and packages). These form the submodule boundary:

| pydal module | Symbols | Importers |
|---|---|---|
| `pydal` (root) | `DAL, Field, SQLCustomType, geo*` | `dal.py:12`; `main.py:91` (patch) |
| `pydal.base` | `BaseAdapter` (re-exported from `backend_base`), `DEFAULT` | `main.py:96`, `compileapp.py:30`, `shell.py:25`, `sql.py:15`, `sqlhtml.py:28`, `scheduler.py:33` |
| `pydal.backend_base` | `CALLABLETYPES` | `sqlhtml.py:27` |
| `pydal.objects` | `Expression, Field, Query, Row, Rows, Set, Table` | `dal.py`, `sql.py`, `sqlhtml.py`, `authapi.py:9`, `tools.py:51`, `scheduler.py:34`, `cache.py:56` |
| `pydal.drivers` | `DRIVERS` | `dal.py:13`, `sql.py:16`, `widget.py:735` |
| `pydal.migrator` | `InDBMigrator, Migrator` | `dal.py:14` |
| `pydal.helpers.classes` | `SQLALL, Reference, SQLCustomType` | `sql.py:17`, `sqlhtml.py:30` |
| `pydal.helpers.methods` | `_repr_ref, bar_encode, merge_tablemaps, smart_query` (private `_repr_ref`) | `sqlhtml.py:31` |
| `pydal.helpers.regex` | `REGEX_UPLOAD_PATTERN` | `globals.py:1011` |
| `pydal.default_validators` | `default_validators` | `sqlhtml.py:29` |
| `pydal.exceptions` | `NotAuthorizedException, NotFoundException` | `globals.py:1010` |
| `pydal.utils` | `utcnow` | `globals.py:67`, `tools.py:52`, `scheduler.py:35` |
| `pydal.validators` | everything | `validators.py` |
| `pydal.contrib.portalocker` | `lock/unlock/LockedFile/read_locked` | `globals.py:66`, `cache.py:46`, `storage.py:18`, `languages.py:24`, `newcron.py:26`, `applications/admin/models/access.py:7` |

Also relied on through attributes: `DAL.serializers/representers/uuid/Field/Table`, `db._adapter.close/reconnect`, `db._migrate`, `db._fake_migrate`, `db._lazy_tables` (`tools.py:2501-2504`, `:2561`), `THREAD_LOCAL` registries (via `close_all_instances`).

Broken boundary crossings:
- **[Legacy]** `gluon/contrib/heroku.py:11` imports `from pydal.adapters import PostgrePsyco, adapters`. `pydal.adapters` no longer exists, and the class is now `PostgresPsyco` (`pydal/backends/postgres.py:196`). The module cannot be imported.
- `gluon/restricted.py:43` whitelists `pydal.objects.Row/Rows` for `SafeUnpickler`. `gluon/cache.py:59-63` registers a `copyreg` reducer for `pydal.objects.Row` (marked "TODO: REMOVE ME ONCE THIS IS FIXED IN DAL", pydal issue #668). This is a process-wide pickling side effect.

## Side effects

- Importing `gluon` mutates `sys.path` and `sys.modules` (`__init__.py:142-144`), patches the `pydal` module (`main.py:93`), and mutates `pydal.DAL` class attributes and the `DRIVERS` dict (`dal.py:21-48`).
- Each request mutates the process-global `Validator.translator` (`compileapp.py:428`) and the thread-local DAL folder (`compileapp.py:469`).
- `DAL(folder=X)` also calls `set_folder(X)` (`pydal/base.py:408-409`), which changes the default folder for later `DAL()` calls in the same thread.
- Each `DAL.__init__` writes web2py serializers into pydal's global `serializers._custom_` (`pydal/base.py:508-510`).
- Migrations create and alter `.table` files and `sql.log` in `applications/<app>/databases/`.

## Compatibility constraints

- `from gluon.dal import DAL, Field, …`, `from gluon.sql import SQLDB, …` and `from gluon.validators import …` must keep working. **[Compat]**
- `SQLDB`/`SQLField` in the model namespace (`compileapp.py:398-399`) must stay. **[Compat]**
- The `.table` naming (`<md5(uri)>_<table>.table`) must stay stable, or existing apps will try to re-create tables.
- Commit-on-success and rollback-on-error, with the `do_not_commit`, `custom_commit` and `_custom_rollback` hooks, are part of the programming model.
- Apps rely on `db.Field`, `DAL.uuid` producing `web2py_uuid()`, and `Rows.xml()` producing `SQLTABLE`.
- Submodules must not be modified (`CLAUDE.md`). Any fix to pydal-side behavior belongs upstream.

## Related tests

| Test | What it covers |
|---|---|
| `test_dal.TestDALSubclass.testRun` (`test_dal.py:23`) | `DAL.serializers` and `DAL.representers` patches |
| `test_dal.TestDALSubclass.testSerialization` (`:34`) | Pickling `Rows` (with `cacheable=True`) |
| `test_dal.TestDALAdapters.test_mysql` (`:103-109`) | **No-op** unless `TRAVIS` is set. It returns early under `APPVEYOR` |
| `test_cache.test_DALcache` (`test_cache.py:139`) | `select(cache=(cache.ram/disk, …))` round-trip |
| `test_globals.testSessionCheckClient` (`test_globals.py:848-931`) | DB session table use through `db.define_table` |
| `test_sqlhtml`, `test_appadmin`, `test_tools`, `test_authapi` | Indirect DAL usage on `DB` (default `sqlite:memory`) |

## Known gaps in test coverage

- **`test_mysql` cannot work even under `TRAVIS`:** it loads `gluon/packages/dal/tests/__init__.py` (`test_dal.py:81-83`). The real path is `gluon/packages/pydal/tests`. It also uses `unittest.makeSuite` (`:94`), which was removed in Python 3.13, and `assertTrue(result)` (`:109`) always passes because a `TestResult` object is truthy. **[Suspected issue]** (static reading; the branch is never executed).
- The CI `mysql:8` service and `CREATE DATABASE pydal` step (`.github/workflows/tests.yml:32-43`, `:69-70`) therefore test nothing.
- pydal's own suite (`gluon/packages/pydal/tests/`, ~30 modules) is not run by web2py CI.
- No test covers `close_all_instances` with `do_not_commit`, `custom_commit` or `_custom_rollback`, pooling across requests, or the shell's commit/rollback branches.
- No test covers `--force_migrate`/`--fake_migrate`, `.table` file handling, or `set_folder` isolation between threads.
- No web2py-side validator tests exist (there is no `test_validators.py`). The `Validator.translator` wiring is untested.
- `gluon/contrib/heroku.py` and the `pg8000` fallback are not imported by any test.

## Open questions

1. Does the vendored pydal actually import and pass on Python 3.9, given `requires-python >= 3.10`? **[Unverified]**
2. Is the translator race observable in practice? That would need a threaded test with two `Accept-Language` values.
3. Does any deployment use `pool_size > 0` together with `do_not_commit`?
4. Is `pydal.get_default_represent` read by any other pydal version still supported by web2py? If not, the patch in `main.py` can be documented as dead.
5. Should `request.tickets_db` be enabled on the modern GAE runtime (`GAE_APPLICATION`), where the file system is read-only?

## Discrepancies with the technical reference

| Reference (`web2py_technical_reference-v2.md`) | Source |
|---|---|
| §1, §3, §10, §19: pydal at `gluon/packages/dal` | Path is `gluon/packages/pydal`. Only the submodule *name* is `gluon/packages/dal` (`.gitmodules:1-2`) |
| §10: `from pydal.dbapi import RestAPI, Policy` | No `dbapi` module. `RestAPI`/`Policy` are in `pydal/restapi.py:102,274` and unused by gluon |
| §10: `migrate=True` compares to `databases/<hash>_<tablename>.table` | Correct for web2py, where the folder comes from `set_folder` (`compileapp.py:469`, `pydal/migrator.py:379`) |
| §10: example passes `folder='applications/myapp/databases'` | In web2py apps `folder` is implicit. Passing it explicitly also enables pydal's stale-marker check (`pydal/base.py:351-392`) |
| §2: "db.commit() on all open pydal connections" | `BaseAdapter.close_all_instances("commit")` over thread-local instances, with `do_not_commit`/`custom_commit` variants (`main.py:494-500`) |
| §2: "db.rollback() on all DAL instances, then ticket" | File tickets are logged before the rollback, DB tickets after it (`main.py:543-552`) |
| §11: `gluon.validators` implements validators | 9-line re-export of `pydal.validators` |
| §1 `[Legacy]`: `gluon.sql` is a DAL "prior to PyDAL" | It is a 30-line alias module over pydal (`sql.py`) |
| §18: supports Python 3.9–3.12+ | Bundled pydal requires `>=3.10` (`pyproject.toml:6`) |

## Modernization considerations

- Replace the process-global `Validator.translator` with a lookup through `current.T`. That requires a pydal-side hook or a gluon-side validator wrapper. Add a threaded characterization test first.
- Remove the no-op `get_default_represent` patch and the `pg8000` fallback. Fix or remove `contrib/heroku.py`.
- Fix `test_dal.load_pydal_tests_module` (path, `makeSuite`) or drop it, and decide whether to run pydal's suite in CI.
- Make CI Python versions consistent with pydal's `requires-python`.
- Consider rolling back before returning a connection to the pool when `do_not_commit` is set. That change would have to happen upstream in pydal.
