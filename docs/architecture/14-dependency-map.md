# 14 — Dependency Map

## Purpose

This is the real import graph of the core `gluon/*.py` modules. It excludes `gluon/tests`, `gluon/contrib` and `gluon/packages` as sources. From the graph it derives dependency layers, cycles, request-path dependencies, submodule boundaries and fan-in/fan-out, and it lists the sets of code that must change together.

**Method.** Static text extraction only. No gluon code was imported or run. The extraction:

- matched `^\s*(from|import)\s+(gluon|\.)` in `gluon/*.py`, plus `pydal|yatl|rocket3` imports
- classified an import as **top** if it runs at module import time, including inside module-level `try`/`if`
- classified it as **local** if it sits inside a `def` or method
- dropped matches inside docstrings: `scheduler.py:57`, and `tools.py:1062`, `:1756`, `:2323`, `:6398`

Labels: **[Current]**, **[Compat]**, **[Legacy]**, **[Suspected issue]**, **[Unverified]**.

## Relevant source files

All 44 modules in `gluon/*.py`, with `gluon/__init__.py` as the package hub. Submodule entry points: `gluon/packages/pydal/pydal/`, `gluon/packages/yatl/yatl/`, `gluon/packages/rocket3/rocket3/`.

## Main classes / functions

| Symbol | Location | Dependency role |
|---|---|---|
| `import_packages()` | `gluon/__init__.py:137` | Puts the submodules on `sys.path` and registers them in `sys.modules` |
| package re-exports | `gluon/__init__.py:151-158` | `LOAD`, `DAL`, `Field`, `current`, `html.*`, `HTTP`, `redirect`, `wsgibase`, `SQLFORM`, `SQLTABLE`, `validators.*` |
| `wsgibase` | `gluon/main.py:285` | Root of the request-path dependencies |
| `build_environment` | `gluon/compileapp.py:405` | Pulls in `languages`, `cache`, `validators`, `custom_import` for every request |

## Textual dependency map (module → gluon imports)

`*` = local/lazy (function-level). `(pkg)` = `from gluon import …` resolved through `gluon/__init__.py`. Line numbers are the import lines.

| Module | Top-level gluon imports | Local imports (*) | Submodule imports |
|---|---|---|---|
| `__init__` | compileapp, dal, globals, html, http, main, sqlhtml, validators (`:151-158`) | — | pydal, yatl, rocket3 via `import_packages` (`:137-149`) |
| `admin` | cache, fileutils, http, restricted, settings, utils (`:21-38`) | compileapp (`:218`) | — |
| `authapi` | (pkg) current, settings, storage, utils, validators (`:11-15`) | — | `pydal.objects` (`:9`) |
| `cache` | recfile (`:37`), settings (try, `:40`) | globals via (pkg) current, http (`:627-628`, `:809`); contrib.gae_memcache (`:574`) | `pydal.contrib.portalocker` (`:46`), `pydal.objects.Row` (`:56`) |
| `cfs` | fileutils (`:19`) | — | — |
| `compileapp` | html, rewrite, validators, cache, cfs, dal, fileutils, globals, http, languages, restricted, settings, sqlhtml, storage, template (`:32-52`) | custom_import (`:470`) | `pydal.base.BaseAdapter` (`:30`) |
| `console` | settings, shell, utils (`:51-53`) | — | — |
| `contenttype`, `decoder`, `digest`, `recfile`, `version`, `messageboxhandler` | none | — | — |
| `custom_import` | (pkg) current (`:17`) | — | — |
| `dal` | **sqlhtml** (`:17`), serializers, utils (`:18-19`); contrib.pymysql / pypyodbc / pg8000 (try, `:28-47`) | — | pydal (`:12-15`) |
| `debug` | contrib.dbg (`:98`), **main** (`:207`) | — | — |
| `fileutils` | storage, http, recfile, settings, utils (`:23-27`) | dal (`:490`) | — |
| `form` | dal, storage, utils (`:3-5`); try `gluon.current`/`gluon.helpers`/`gluon.url` (web3py, always fails) → except (pkg) current, html (`:8-15`) | — | — |
| `globals` | settings, recfile, cache, contenttype, restricted, contrib.multipart, fileutils, html, http, serializers, storage, streamer, utils (`:69-82`); contrib.minify (try, `:90`) | contrib.user_agent_parser (`:570`), **compileapp** (`:746`), xmlrpc (`:1051`), html (`:1076`), dal (`:1086`) | `pydal.contrib.portalocker`, `pydal.utils` (`:66-67`); `pydal.exceptions`, `pydal.helpers.regex`* (`:1010-1011`) |
| `highlight` | none | — | `yatl.sanitizer` (`:12`) |
| `html` | decoder, highlight, storage, utils, validators (`:29-33`) | serializers (`:163`, `:2415`, `:2509-2521`, `:2990`), **rewrite** (`:295`), **globals** (`:312`, `:349`, `:395`, `:502`, `:1522`, `:1555`, `:2310`), http (`:2311`), contrib.markmin (`:2953`) | `yatl.sanitizer` (`:28`) |
| `http` | none | **globals** (`:204`, `:223`) | — |
| `languages` | cfs, contrib.markmin, fileutils, html (`:27-30`) | settings (`:90`), contrib.plural_rules (`:179`), **tools** (`:1034`) | `pydal.contrib.portalocker` (`:24`), `yatl.sanitizer` (`:25`) |
| `main` | fileutils, globals, settings, utils (`:25-35`); messageboxhandler (if, `:70`); newcron, compileapp, contenttype, globals, html, http, restricted, rewrite, utils, validators, version (`:98-116`) | **debug** (`:469`) | pydal (`:91`, `:96`); `rocket3`* (`:752`) |
| `newcron` | fileutils (`:28`) | — | `pydal.contrib.portalocker` (`:26`) |
| `restricted` | html, http, settings, storage (`:22-25`) | — | — |
| `rewrite` | fileutils, http, settings, storage (`:25-28`) | — | — |
| `sanitizer`, `template` | none | — | `yatl` (`:1`) |
| `scheduler` | (pkg) DAL, Field, IS_* (`:37-47`); storage, utils (`:48-49`) | (pkg) current (`:513`, `:593`, `:688`, `:879`), **shell** (`:514`) | pydal (`:33-35`) |
| `serializers` | contrib.rss2, html, **languages**, storage (`:12-15`) | — | — |
| `settings` | storage (`:13`) | — | — |
| `shell` | fileutils, admin, compileapp, globals, restricted, settings, storage (`:27-33`) | dal (`:268`) | `pydal.base` (`:25`) |
| `sql` | dal (`:20`) | — | pydal (`:15-18`) |
| `sqlhtml` | serializers, globals, html, http, storage, utils, validators (`:34-73`); settings (try, `:85`) | **dal** (`:2307`, comment "avoid circular references" `:2306`), contrib.populate (`:3763`) | pydal (`:27-32`) |
| `storage` | none | http (`:320`) | `pydal.contrib.portalocker` (`:18`) |
| `streamer` | contenttype, http, utils (`:19-21`) | — | — |
| `tools` | serializers, **(pkg) `*`** (`:55`), authapi, contenttype, contrib.autolinks, contrib.markmin, fileutils, storage, utils (`:54-66`) | contrib.login_methods.cas_auth (`:2578`), settings (`:4700`), contrib.pysimplesoap (`:5881`, `:6220`) | `pydal.objects`, `pydal.utils` (`:51-52`) |
| `utils` | contrib.pyaes (only if `Crypto` is missing, `:36-43`) | restricted (`:278`, `:347`) | — |
| `validators` | none | — | `pydal.validators` (`:1-9`) |
| `widget` | main, newcron, console, fileutils, settings, shell, utils, version (`:27-33`) | contrib.taskbar_widget (`:308`) | `pydal.drivers`* (`:735`) |
| `xmlrpc` | none | — | — |

Notes:
- **[Current]** Every `import gluon.X` first runs `gluon/__init__.py`, which imports `gluon.main` (`:156`). So every module above transitively depends on `main` and its import-time side effects, whatever the table says.
- **[Suspected issue]** `scheduler.main()` loads tasks with `builtins.__import__(filename, globals(), locals(), [], -1)` (`scheduler.py:1981`). Python 3 rejects a negative `level` (ValueError). This affects only the standalone `python gluon/scheduler.py --tasks` path. Not executed.

## Core dependency layers (top-level edges only)

Layer = 1 + the maximum layer of top-level dependencies. Local imports are ignored, and that is exactly what makes the top-level graph a DAG.

| Layer | Modules | Notes |
|---|---|---|
| L0 | `contenttype`, `decoder`, `version`, `recfile`, `digest`, `messageboxhandler`, `xmlrpc`, `http`, `storage`, `utils`, `highlight`, `validators`, `template`, `sanitizer` | Only stdlib, submodules, or contrib (`utils` → `pyaes`) |
| L1 | `settings`, `streamer`, `html` | `html` depends on `pydal.validators.simple_hash` (`html.py:33`) |
| L2 | `fileutils`, `cache`, `restricted` | |
| L3 | `cfs`, `newcron`, `rewrite`, `admin` | |
| L4 | `languages` | Pulls in contrib.markmin at import |
| L5 | `serializers` | Depends on `languages` (for `lazyT`) |
| L6 | `globals` | |
| L7 | `sqlhtml` | |
| L8 | `dal` | **Above** `sqlhtml` and `globals`: `import gluon.dal` loads `sqlhtml` → `globals` → `cache`/`restricted`/`serializers`/`languages` |
| L9 | `compileapp`, `sql` | |
| L10 | `main`, `shell` | |
| L11 | `console`, `debug`, `gluon/__init__` | |
| L12 | `widget`; package-dependent modules `authapi`, `custom_import`, `form`, `scheduler`, `tools` | They use `from gluon import …`, so they need the fully initialized package |

The layering is inverted compared with the usual intuition: the DB shim (`dal`) sits above the UI/form layer (`sqlhtml`) because of `dal.py:17` and `dal.py:23` (`DAL.representers` → `sqlhtml.represent`/`SQLTABLE`) **[Current]**.

## Cycles (all broken by local imports)

The top-level graph has no cycles. These cycles exist once local imports are counted:

| Cycle | Top-level edge | Breaking local edge |
|---|---|---|
| html ⇄ globals | `globals.py:76` → html | `html.py:312` (and 6 more) → globals |
| http → globals → http | `globals.py:77` → http | `http.py:204`, `:223` → globals |
| storage → http → globals → storage | `globals.py:80` → storage | `storage.py:320` → http |
| utils → restricted → html → utils | `restricted.py:22`, `html.py:32` | `utils.py:278`, `:347` → restricted |
| html → serializers → html | `serializers.py:13` → html | `html.py:163` etc. → serializers |
| dal ⇄ sqlhtml | `dal.py:17` → sqlhtml | `sqlhtml.py:2307` → dal (comment at `:2306`) |
| globals → dal → sqlhtml → globals | `dal.py:17`, `sqlhtml.py:35` | `globals.py:1086` → dal |
| fileutils → dal → … → globals → fileutils | `globals.py:75` → fileutils | `fileutils.py:490` → dal |
| globals ⇄ compileapp | `compileapp.py:44` → globals | `globals.py:746` (`Response.render`) → compileapp |
| cache → http → globals → cache | `globals.py:71` → cache | `cache.py:627-628` → http, current |
| languages → tools → (pkg) → compileapp → languages | `compileapp.py:46`, `tools.py:55` | `languages.py:1034` → tools |
| main ⇄ debug | `debug.py:207` → main | `main.py:469` → debug |
| html → rewrite (no cycle) | — | `html.py:295`: `URL()` imports `url_out` lazily "in case used not-in web2py" |

Any refactor that turns one of these local imports into a top-level import will create an import-order failure **[Current]**.

## Request path dependencies (`wsgibase`, dynamic request)

| Step | Module(s) touched | Evidence |
|---|---|---|
| Reset / construct | `globals` (`current`, `Request`, `Response`, `Session`) | `main.py:314-317` |
| Route | `rewrite` (`fixup_missing_path_info`, `url_in`, `THREAD_LOCAL`) | `main.py:336-337` |
| Static (short-circuit) | `globals.Response.stream` → `streamer.stream_file_or_304_or_206`, `contenttype` | `main.py:346`, `globals.py:918`, `:957` |
| Client/host checks | `utils` (`getipaddrinfo`, `is_valid_ip_address`) | `main.py:361`, `:114` |
| App folders | `fileutils.create_missing_app_folders` | `main.py:426` |
| Session | `globals.Session.connect` → `utils.secure_loads`, `restricted.safe_load(s)`, `recfile`, `pydal.contrib.portalocker`, `fileutils.up`, pydal DAL (DB sessions) | `main.py:462`, `globals.py:1190-1400` |
| Debugger (optional) | `debug` (local) | `main.py:468-472` |
| Environment | `compileapp.build_environment` → `html`, `validators`, `dal`, `sqlhtml`, `languages.TranslatorFactory`, `cache.Cache`, `custom_import`, `pydal.BaseAdapter.set_folder` | `compileapp.py:405-473` |
| Models / controller | `compileapp.run_models_in` / `run_controller_in` → `cfs.getcfs`, `restricted.compile2`/`restricted`, `fileutils.listdir`/`read_file`, `read_pyc` | `compileapp.py:581-626`, `:668-731` |
| Request body (lazy) | `globals.Request.body/vars` → `contrib.multipart` | `globals.py:406`, `:488`, `:547` |
| View | `compileapp.run_view_in` → `template.parse_template` (yatl) → `restricted` | `compileapp.py:757`, `:793-797` |
| Success | `http.HTTP` raised; `pydal.BaseAdapter.close_all_instances`; `Session._try_store_*`; `html.xmlescape` for flash headers | `main.py:223`, `:489-507`, `:518` |
| Error | `restricted.RestrictedError.log` → `TicketStorage` (pickle) | `main.py:534-581`, `restricted.py:118-200` |
| On-error routing | `rewrite.try_rewrite_on_error` (may call `wsgibase` again) | `main.py:588-592` |
| Soft cron | `newcron.softcron` | `main.py:594-598` |
| Respond | `http.HTTP.to` | `main.py:600` |

Core modules **not** on the default dynamic path unless app code uses them: `tools`, `authapi`, `scheduler`, `form`, `shell`, `widget`, `console`, `admin`, `xmlrpc` (only `Response.xmlrpc`, `globals.py:1051`), `digest`.

## Submodule boundaries

| Mechanism | Evidence |
|---|---|
| For each of `pydal`, `yatl`, `rocket3`: insert `gluon/packages/<name>` (the **repo root**) at `sys.path[0]`, then `sys.modules[name] = builtins.__import__(name)` | `gluon/__init__.py:138-144` |
| Bundled copies shadow any pip-installed pydal/yatl/rocket3, because of `insert(0)` **[Current]** | `gluon/__init__.py:143` |
| Aliasing is identity (`sys.modules["pydal"]` is `pydal`), so it adds nothing beyond the import itself **[Current]** | `:144` |
| Missing submodule → `RuntimeError` with `git submodule update` instructions | `:145-146`, `:128-134` |

| Submodule | Importing gluon modules | Kind |
|---|---|---|
| pydal | `dal`, `sql`, `validators` (shims); `authapi`, `cache`, `compileapp`, `globals`, `languages`, `main`, `newcron`, `scheduler`, `shell`, `sqlhtml`, `storage`, `tools`, `widget`* | Direct imports; **global mutation**: `DAL.serializers/uuid/representers/Field/Table` (`dal.py:21-25`), `DRIVERS[...]` (`dal.py:28-47`), `Validator.translator` per request (`compileapp.py:428-430`), `pydal.get_default_represent` (`main.py:93`, **[Legacy]** no-op: the name is not used by the bundled pydal) |
| yatl | `template`, `sanitizer` (shims); `html` (`yatl.sanitizer`), `highlight`, `languages` (`xmlescape`) | Direct |
| rocket3 | `main.HttpServer.__init__` only (local, `main.py:752`, `:806`) | Lazy |

Only `main.py` touches rocket3. `anyserver.py:59`, `:66` still reference the removed `gluon.rocket` **[Legacy]**.

## Fan-in / fan-out (core modules)

Distinct core-module edges (contrib and submodules excluded). `(pkg) current` counts as `globals`, and `(pkg) *` as `__init__`. Format: **all edges / top-level only**.

| Module | Fan-in (all/top) | Fan-out (all/top) |
|---|---|---|
| settings | **15**/13 | 1/1 |
| utils | **14**/14 | 1/0 |
| storage | **14**/14 | 1/0 |
| http | 12/9 | 1/0 |
| fileutils | 11/11 | 6/5 |
| globals | 11/7 | **15**/12 |
| html | 8/8 | 9/5 |
| dal | 7/3 | 3/3 |
| restricted | 6/5 | 4/4 |
| validators | 5/5 | 0/0 |
| serializers | 5/4 | 3/3 |
| contenttype | 4/4 | 0/0 |
| compileapp | 4/2 | **16**/15 |
| main | 2/2 | **15**/14 |
| sqlhtml | 2/2 | 9/8 |
| shell | 3/2 | 8/7 |
| tools | 1/0 | 8/7 (plus the whole package via `*`) |
| widget | 0/0 | 8/8 |
| admin | 1/1 | 7/6 |

Who imports the hubs:
- `settings` ← admin, authapi, cache, compileapp, console, fileutils, globals, languages*, main, restricted, rewrite, shell, sqlhtml, tools*, widget.
- `storage` ← authapi, compileapp, fileutils, form, globals, html, restricted, rewrite, scheduler, serializers, settings, shell, sqlhtml, tools.
- `globals` ← authapi, cache*, compileapp, custom_import, form, html*, http*, main, scheduler*, shell, sqlhtml.

Unreferenced by other core modules: `digest` (no importer anywhere in the repo), `sql` (only `gluon/tests/test_appadmin.py:38`), `form` (only `gluon/tests/test_form.py:15`), `debug` (main* and admin controllers).

## Areas that should not be changed independently

| Coupled set | Why | Evidence |
|---|---|---|
| **`appadmin.py` ×3** | Byte-identical copies (md5 `6bd368ac…`) in `admin`, `welcome`, `examples`. `views/appadmin.html` already diverged: the admin copy has CSP nonces | `applications/*/controllers/appadmin.py`, `applications/*/views/appadmin.html` |
| **Session pickle format** | Every session backend saves with `pickle.dumps(self)`. The copyreg reducer turns that into global `gluon.globals.Session` (`globals.py:1757-1761`). Nested objects rely on reducers in `storage.py:145-149`, `html.py:762`, `:1366`, `languages.py:444`, `cache.py:59-63`. Load paths: `pickle`, or `SafeUnpickler` with `DEFAULT_SAFE_GLOBALS`, which does **not** list `gluon.globals.Session` or `gluon.storage.Storage` (`restricted.py:38-43`). So with `safe_unpickle=True` and no `pickle_allowed_classes`, a previously saved session is probably rejected and silently discarded (`globals.py:1318-1330` catches `Exception`) **[Suspected issue]**. No test round-trips a real saved session under `safe_unpickle=True` | `globals.py:1438`, `:1647`, `:1678`, `:1729` |
| **Cookie crypto** | `secure_dumps` (bytes, `utils.py:220-235`) ↔ `secure_loads` (expects bytes, `:238-284`) ↔ `secure_loads_deprecated` (`:314`) ↔ `SafeUnpickler` via local import (`:278`) ↔ `Session._try_store_in_cookie` (`globals.py:1619-1631`) / `connect` cookie branch (`:1270-1292`) | as cited |
| **Admin session files** | `fileutils.get_session`/`set_session` read and write *another app's* session file with `storage.load_storage`/`save_storage` (pickle of a plain `dict`, `storage.py:170-188`). They depend on `Session`'s file naming and location (`<app>/sessions/<id>`). `check_credentials`/`_check_admin_app_ownership` open the admin DB (`fileutils.py:475-510`) | `fileutils.py:440-465` |
| **Ticket format** | `TicketStorage` pickles to file or a DB `text` column (`restricted.py:143`, `:157`, `:177`). It loads with `TICKET_ALLOWED_CLASSES = {"gluon.html": {"XML", "XML_unpickle"}}` (`restricted.py:184`), which must follow the `XML` reducer (`html.py:762`) | as cited |
| **Compiled-app layout** | Writers: `compile_views`/`compile_models`/`compile_controllers` (`compileapp.py:505-575`, naming `controllers.<c>.<f>.pyc`), `w2p_pack(compiled=True)`/`tar_compiled` (`fileutils.py:282`, `:412`), `admin.app_compile`/`remove_compiled_application` (`admin.py:218-226`, `admin/controllers/default.py:549`). Readers: `read_pyc` with `MAGIC` and `MARSHAL_HEADER_SIZE` (`compileapp.py:54`, `:484-498`), `run_models_in` (name mangling `:613-615`), `run_controller_in` (`:680-682`), `run_view_in` (`:778`), `shell.py:102`, `:298-301`, `:316` | as cited |
| **Model ordering / `models_to_run`** | Default regexes (`compileapp.py:416-420`) ↔ sort key and path mangling (`:595-619`) ↔ appadmin bypass (`:619`) | as cited |
| **Rewrite ↔ `URL()`** | `html.URL` → `rewrite.url_out` (`html.py:295`) → `filter_url`/`map_url_out` (`rewrite.py:208`, `:786`, `:1521`). `THREAD_LOCAL.routes` is shared with `main` (`main.py:110`) and `compileapp` 404 messages (`compileapp.py:685`). Routes are loaded at import (`main.py:128`) and in `HttpServer` (`:776`). `routes_onerror` re-enters `wsgibase` (`main.py:592`) | as cited |
| **Injected namespace ↔ package `__all__`** | `_base_environment_` = `html.__all__` + `validators.__all__` + extras (`compileapp.py:391-402`). `gluon/__init__.__all__` (`:15-121`) is what `from gluon import *` gives modules (`tools.py:55`). The two lists are maintained separately | as cited |
| **`current` contract** | `build_environment` sets `globalenv, request, response, session, T, cache` (`compileapp.py:432-438`). `LOAD`/`LoadFactory` swap `current.request/response` (`compileapp.py:200-208`, `:307-315`). `main` clears `current` (`main.py:314`) and tests `hasattr(current, "request")` (`:484`) | as cited |
| **CLI options → runtime** | `console.py` option names → `widget.start` → `global_settings.cmd_options` read by `main` soft cron (`main.py:595`). The scheduler is started via `shell.run` with generated code (`widget.py:609-630`) and runs tasks through `shell.env` (`scheduler.py:514`) | as cited |
| **Shim modules** | `template`, `sanitizer`, `validators`, `dal`, `sql` must keep re-exporting the names old apps import, even when submodules move | tier 2 in doc 01 |

## gluon/contrib and applications (summary)

- **contrib → core**: 32 of 177 contrib `.py` files import non-contrib gluon modules. Most use `gluon` (package, 25 imports), `gluon.storage` (12), `gluon.tools` (8), `gluon.utils` (7), `gluon.html` (4). Heavy users: `redis_scheduler.py` (5), `memdb.py` (4), `generics.py` (4), and about 15 `login_methods/*`. Core → contrib edges are listed in the map above (`multipart`, `markmin`, `rss2`, `pyaes`, `minify`, `autolinks`, `pysimplesoap`, `plural_rules`, `dbg`, DB drivers…).
- **applications → core**:
  - `admin` mostly imports `fileutils` (11), `admin` (6), `utils` (5), `settings` (4), `tools`/`restricted`/`debug` (3 each), plus `compileapp`, `languages`, `rewrite`, `dal`, `contrib.pam`, `contrib.dbg`.
  - `welcome` imports `utils`, `fileutils`, `contenttype`, `tools`, `scheduler`, `restricted`, `languages`, `http`, `html`, `contrib.appconfig`.
  - `examples` imports `fileutils`, `utils`, `contenttype`, `template`, several contribs.
  - All three also use the injected namespace, which has no import lines.
- **handlers**: every handler does `from gluon.settings import global_settings` then `import gluon.main` (e.g. `handlers/wsgihandler.py:36-40`).

## Side effects

Importing any leaf module still triggers `gluon/__init__.py` → `main` import-time effects (doc 01). Module-level global mutations happen in `dal.py:21-47` and `main.py:93`, plus the copyreg registrations listed above.

## Related tests

`test_router`, `test_routes` (URL/rewrite), `test_compileapp` (compile/pack), `test_globals` (sessions), `test_utils` (secure_dumps/loads), `test_appadmin` (injected namespace), `test_html`, `test_sqlhtml`, `test_dal`.

## Known gaps in test coverage

- `test_restricted.py` (20 tests on SafeUnpickler, safe-unpickle sessions, TicketStorage) is **not imported** by `gluon/tests/__init__.py:1-28`, so the official runner and CI never run it.
- No test runs a compiled app through `run_models_in`/`run_controller_in`/`read_pyc`.
- No test checks import-order robustness (for example importing `gluon.dal` or `gluon.html` alone). No test for `scheduler.main()`.

## Open questions

1. Do external apps depend on the load order implied by `dal.py:17` (for example, expecting `gluon.dal` to make `current` available)? **[Unverified]**
2. Is the intended `safe_unpickle` usage to pass `pickle_allowed_classes` covering `gluon.globals.Session`? There is no in-repo caller with `safe_unpickle=True` except tests **[Unverified]**.

## Discrepancies with the technical reference

| Claim | Source |
|---|---|
| Reference §4 lists `sanitizer`, `template`, `validators` as implementations | They are shims (see the map) |
| `architecture-report.md` §5 originally showed "sqlhtml → … dal" (since corrected there) | The top-level edge is `dal → sqlhtml` (`dal.py:17`). `sqlhtml → dal` is local only (`sqlhtml.py:2307`) |
| `architecture-report.md` §5: "compileapp → … custom_import" | Local import (`compileapp.py:470`), done on every `build_environment` |
| `architecture-report.md` §2: "monkeypatches `pydal.get_default_represent`" | True, but it is a no-op against the bundled pydal |

## Modernization considerations

- Remove the inverted `dal → sqlhtml` top-level edge, for example by registering representers lazily. This needs characterization tests on `Rows.render`/`Rows.xml`.
- Replace function-level imports of `current` in `html.py` with one accessor to make the `html` ⇄ `globals` cycle explicit.
- Keep the coupled sets above in single, atomic changes, each with round-trip tests (session pickle, compiled app, `URL()` ↔ routes).
