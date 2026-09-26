# 06 — Application Loading

## Purpose

Describes how an application under `applications/<app>/` is located, validated and prepared, and how its models, controllers and views are discovered, ordered, compiled and executed. It also covers packaging and installing apps and plugins (`.w2p`), and the scaffolding app `welcome`. The execution namespace itself is covered in `05-dynamic-execution-environment.md`.

Labels: **[Current]**, **[Compat]**, **[Legacy]**, **[Suspected issue]**, **[Unverified]**.

## Relevant source files

| File | Role |
|---|---|
| `gluon/main.py` | app existence, `DISABLED`, `create_missing_app_folders`, `serve_controller` |
| `gluon/rewrite.py` | global and per-app `routes.py` loading (`load`) |
| `gluon/compileapp.py` | `run_models_in`, `run_controller_in`, `run_view_in`, `compile_*`, `save_pyc`/`read_pyc` |
| `gluon/fileutils.py` | `listdir`, `w2p_pack`/`w2p_unpack`, `tar_compiled`, `create_welcome_w2p`, `create_app`, plugin pack/unpack, safe `_extractall` |
| `gluon/admin.py` | `app_pack`, `app_pack_compiled`, `app_cleanup`, `app_compile`, `app_create`, `app_install`, `plugin_pack`, `plugin_install`, `unzip` |
| `gluon/widget.py` | calls `create_welcome_w2p()` on startup |
| `gluon/tools.py` | `PluginManager` |
| `applications/welcome/` | reference app (`models/db.py`, `private/appconfig.ini`) |

## Main classes / functions

### Locating the application (`gluon/main.py`)
- `request.folder = abspath("applications", app)` (`main.py:373`). `fileutils.abspath` joins with `global_settings.applications_parent` (`fileutils.py:554-563`).
- **Missing folder** (`main.py:393-411`). If the app is the default app (and not `welcome`), the request redirects to `welcome/default/index`. If `routes.error_handler` is set, it redirects there. Otherwise the result is `HTTP 404 "invalid request"`.
- **`DISABLED` file** (`main.py:392`, `:412-420`). **Non-local** clients get 503 with `static/503.html` if present, or a built-in HTML body otherwise. **Local clients bypass it** (`not request.is_local`).
- **`create_missing_app_folders(request)`** (`main.py:425-430` → `fileutils.py:595-600`) creates `models, views, controllers, databases, modules, cron, errors, sessions, languages, static, private, uploads` (`fileutils.py:314-329`). This happens only once per folder per process, cached in `global_settings.app_folders` (`settings.py:28`). It is skipped on GAE. An `OSError` only prints a message.
- **App-level `routes.py`.** At startup, `rewrite.load()` scans `applications/`. For every non-dot directory that has a `controllers/` subfolder (`rewrite.py:433-439`), it builds a per-app router and, if `applications/<app>/routes.py` exists, calls `load(routes, appname)` (`rewrite.py:450-451`). Per-app params go into `params_apps[app]` (`:457`). Apps installed after startup are not seen until `gluon.rewrite.load()` runs again (admin calls it at `applications/admin/controllers/default.py:278, 296, 333, 1920`). **[Current]**

### Models: `run_models_in(environment)`
`gluon/compileapp.py:581-626`. **[Current]**

**Discovery.** If `<app>/compiled/` exists, **only compiled models** are considered. These are `listdir(cpath, r"models[_.][\w.-]+\.pyc$")` (`:577`, `:595-599`). Otherwise the source models are `listdir(models/, r"[\w-]+\.py$", sort=False)` (`:578`, `:601-604`). `listdir` walks recursively, skips dot-directories and dot-files, and matches the regex on the **basename** (`fileutils.py:175-184`).

**Ordering.**
- Source: `sorted(key="{:03d}".format(path.count(os.sep)) + path)`. Compiled: the same with `count(".")`.
- The result is **depth first, then byte-wise (ASCII) full-path order**. Uppercase sorts before lowercase, and digits sort before letters.

**Filtering.**
- `response.models_to_run` is set by `build_environment` (`compileapp.py:416-420`): `^\w+\.py$`, `^<c>/\w+\.py$`, `^<c>/<f>/\w+\.py$`.
- It is re-read **before every model**. If the list changed (compared with `!=` against a slice copy), the regex is rebuilt as `"|".join(list)` (`:607-611`). A model can therefore append to or replace the list, and later models see the change.
- For compiled models, the relative name is rebuilt as `model[len(cpath)+8:-4].replace(".", "/") + ".py"` (`:613-615`). For example, `models.default.x.pyc` becomes `default/x.py`.
- When `request.controller == "appadmin"`, **every model runs** regardless of the regex (`:619`). The shell `--force_migrate` reuses this hack by setting `c = "appadmin"` (`shell.py:266`).
- Quirk: if `response.models_to_run` is falsy (`None` or `[]`), the `if models_to_run:` guard (`:612`) skips **all remaining models**, the appadmin case included. The regex must be a list, because `[:]` and `"|".join` are applied to it.
- Quirk: `REGEX_MODEL` accepts `-` in names but the default filters use `\w+`. A model named `my-model.py` is listed yet never runs, except under appadmin.

**Execution.** `ccode = getcfs(model, model, read_pyc | compile2)`, then `restricted(ccode, environment, layer=model)` (`:621-626`).

### Controllers: `run_controller_in(controller, function, environment)`
`gluon/compileapp.py:668-731`. **[Current]**

`REGEX_EXPOSED = re.compile(r"^def\s+(_?[a-zA-Z0-9]\w*)\( *\)\s*:", re.MULTILINE)` (`:548`). The rule is applied only to source controllers, after `REGEX_LONG_STRING` (`:547`) strips every `"""…"""` / `'''…'''` block (`find_exposed_functions`, `:551-553`).

| Case | Exposed? |
|---|---|
| `def index():` at column 0 | yes |
| `def _private():` (one underscore) | **yes** |
| `def __x():` | no |
| `def f(a):`, `def f(a=1):`, `def f(*a):` | no (parentheses may hold only spaces) |
| `def f() -> dict:` | **no** (a return annotation breaks `\s*:`) |
| `async def f():`, an indented `def`, `def` inside a triple-quoted string | no |
| decorated `@auth.requires_login()` + `def f():` at column 0 | yes |

**Flow:**
1. **Compiled app** (`compiled/` exists): it loads `compiled/controllers.<c>.<f>.pyc` through `getcfs` + `read_pyc`. An `IOError` gives 404 "invalid function" (`:679-686`). Exposure is decided by **file existence** alone. `_TEST` is not available.
2. **`function == "_TEST"`**: it prepends paths to `sys.path` (`:687-696`), records `environment["__symbols__"]` (`:703`), and appends `TEST_CODE` (`:629-665`). That code checks `gluon.fileutils.check_credentials(request)` and raises 401 if it fails (`:632-633`), then runs doctests of every function not in `__symbols__`.
3. **Source**: `code = getcfs(filename, filename, read_file)`. A missing file gives 404 "invalid controller" (`:708-714`). A function not in `find_exposed_functions(code)` gives 404 "invalid function" (`:715-719`). Otherwise it appends `"\nresponse._vars=response._caller(<f>)"` (`:720`) and compiles once per `"<file>:<function>"` key (`:721-722`).
4. It calls `restricted(ccode, environment, layer=filename)` (`:724`).
5. **Post-processing** (`:725-731`): `vars = response._vars`; each callable in `response.postprocessing` is applied in order through `reduce`; if the result has a callable `.xml`, it becomes `vars.xml()`.

### Views: `run_view_in(environment)`
`gluon/compileapp.py:734-799`. **[Current]**
- **Default view.** `serve_controller` sets `response.view = "<c>/<f>.<ext>"` (`main.py:180-184`). The extension comes from the URL, with default `html` (`globals.py:328`). The controller may override it.
- **Generic permission.** `patterns = response.generic_patterns`, which defaults to `["*"]` (`globals.py:673`). The patterns are `fnmatch.translate`d and joined, then matched against `"<c>/<f>.<ext>"` (`:747-755`). A falsy value (`[]`) disables generic views.
- **Non-string view** (a file-like object): `parse_template(view, views/, context=env)` with layer `"file stream"` (`:756-758`).
- **Compiled app.** It uses the compiled views only if `views.<x>.pyc` exists or the source view does **not** exist (`:766`). The lookup order (`:763-780`) is:
  1. `views.<c>.<f>.<ext>.pyc`
  2. `views.generic.<ext>.pyc` (if generic is allowed)
  3. if `ext == "html"`: `views.<c>.<f>.pyc` (**[Compat]** old naming)
  4. if `ext == "html"` and generic is allowed: `views.generic.pyc` (**[Compat]**)

  A source view that exists in a compiled app therefore still runs from source.
- **Source.** If `views/<view>` is missing and generic is allowed, it falls back to `generic.<ext>` (`:783-785`). If that is still missing, the result is 404 "invalid view" (`:786-791`). Then `parse_template` → `compile2` → `restricted(..., scode=scode)` (`:793-797`), with **no caching**.
- It returns `response.body.getvalue()` (`:799`). The template writes through `response.write`.

### Compilation (`gluon/compileapp.py`)
| Function | Behavior |
|---|---|
| `compile_application(folder, skip_failed_views)` (`:818-827`) | `remove_compiled_application`, `mkdir compiled`, then models, controllers and views |
| `compile_models` (`:532-544`) | `models/<path>.py` → `compiled/models.<path with sep→.>.py` → `save_pyc` → deletes the `.py` |
| `compile_controllers` (`:559-574`) | For **each exposed function**, it writes the full controller source plus `response._vars=response._caller(<f>)` to `controllers.<c>.<f>.py`, compiles it and deletes it. Each file is a full copy of the controller. |
| `compile_views` (`:505-526`) | `parse_template` → `views.<path with sep→.>.py` → pyc. Failures either raise `Exception("… in <fname>")` or are collected when `skip_failed_views` is set. |
| `remove_compiled_application` (`:805-815`) | `rmtree(compiled)` and deletes `controllers/*.pyc`. `OSError` is ignored. |
| `save_pyc` (`:476-481`) | `py_compile.compile(f, cfile=f+"c")` |
| `read_pyc` (`:487-498`) | Raises `SystemError("compiled code is incompatible")` unless the data starts with `importlib.util.MAGIC_NUMBER` (the check is skipped on GAE). It then returns `marshal.loads(data[MARSHAL_HEADER_SIZE:])`. `MARSHAL_HEADER_SIZE = 16 if sys.version_info[1] >= 7 else 12` (`:484`). |

The same `.pyc` only works on the same CPython minor version, because the magic number differs. `admin.app_compile` (`admin.py:207-227`) wraps compilation and removes the partial `compiled/` folder on error.

### Packaging (`gluon/fileutils.py`, `gluon/admin.py`)
- `w2p_pack(filename, path, compiled=False)` (`fileutils.py:282-311`) tars files whose basename matches `^[\w.-]+$` into `<file>.tar`, gzips the tar to `filename`, then deletes the tar. `exclude_content_from=["cache","sessions","errors"]` is passed.
- `tar_compiled` (`:412-433`) skips symlinks and every non-`.pyc` file under `models*`, `views*`, `controllers*` and `modules*`.
- `w2p_unpack` (`:358-375`) gunzips `.w2p`/`.gz` to `.tar`, then calls `untar` → `_extractall` (`:220-255`). Extraction is safe: it rejects absolute names and `safe_path_join` traversal, device and FIFO members, and symlinks or hardlinks that escape the root. It deletes the tar afterwards.
- `admin.app_pack` (`admin.py:117-136`) calls `app_cleanup` first. That **deletes the app's errors, sessions and cache files** (`:161-204`). It then packs to `deposit/web2py.app.<app>.w2p`. `app_pack_compiled` (`:139-158`) packs to `deposit/<app>.w2p` without cleaning up.
- `admin.app_create` (`:230-263`) calls `mkdir` and `create_app(path)`, which is `w2p_unpack("welcome.w2p", path)` (`fileutils.py:378-379`). On failure it runs `rmtree`.
- `admin.app_install` (`:266-309`) writes the upload to `deposit/<app>.<w2p|tar.gz|tar>`, calls `mkdir` unless `overwrite`, then `w2p_unpack` and `fix_newlines` (the latter rewrites CRLF in every `.py`/`.html`). It returns the deposit name, or `False` on error.
- `admin.unzip` (`:429-458`) is used by `upgrade`. It is subfolder-filtered and validates each member with `_safe_extract_path`.

### `welcome.w2p`
`create_welcome_w2p()` (`fileutils.py:332-355`) is called on every `web2py.py` start (`widget.py:695`) and by `w2p_unpack` whenever the filename is `"welcome.w2p"` (`fileutils.py:359-360`). It (re)builds `welcome.w2p` only if the file is missing **or** a `NEWINSTALL` marker exists, in which case it deletes the marker afterwards. It creates the missing app folders under `applications/welcome` first. **The archive is not refreshed when `applications/welcome` changes** while `welcome.w2p` exists. **[Current]** The Makefile `src` target writes `NEWINSTALL`.

### Plugins
- **Naming convention.** `w2p_pack_plugin` collects `<app>/*/plugin_<name>.*` and `<app>/*/plugin_<name>/*` (glob, one directory level, added recursively) into `web2py.plugin.<name>.w2p` (`fileutils.py:382-401`). `w2p_unpack_plugin` requires the basename to start with `web2py.plugin.` (`:404-409`). `admin.plugin_install` validates the deposit name with `safe_deposit_path` (`admin.py:49-54`, `:352-384`).
- **`PluginManager`** (`gluon/tools.py:6488-6580`) is a per-thread singleton (`instances[thread id]`, `:6547-6561`). `PluginManager()` with no name **clears** all settings (`:6564-6565`), while `PluginManager('x', **defaults)` only fills missing keys. The lock inside `__new__` is freshly allocated on every call (`:6551`), so it provides no mutual exclusion. **[Suspected issue]** (low impact under the GIL). Instances persist across requests on the same thread.

### Welcome app as reference
`applications/welcome/models/db.py`:
- It enforces `REQUIRED_WEB2PY_VERSION = "3.0.10"` against `request.global_settings.web2py_version` (`:12-22`).
- `configuration = AppConfig(reload=True)` (`:33`). The config is read from `private/appconfig.ini`, or `appconfig.json` as a fallback (`gluon/contrib/appconfig.py:107-115`), and cached per app on the factory function (`:40-49`).
- It uses `DAL(configuration.get("db.uri"), …)` unless `GAE_APPLICATION` is set, in which case it uses `DAL("firestore")` (`:35-47`).
- `response.generic_patterns` is reset to `[]` and `"*"` is added only when `request.is_local` and not `app.production` (`:63-65`).
- `Auth(db, host_names=configuration.get("host.names"))` (`:95`).

## Execution flow
```
wsgibase → url_in (app/c/f/ext) → folder = applications/<app>
  missing → redirect / 404 ; DISABLED & !local → 503
  create_missing_app_folders (once per process)
  session.connect
  serve_controller → build_environment → run_models_in → run_controller_in → [run_view_in]
```

## Dependencies
`compileapp` ← `fileutils.listdir/read_file/write_file`, `cfs.getcfs`, `restricted`, yatl `parse_template`, stdlib `py_compile`, `marshal`, `importlib.util.MAGIC_NUMBER`. `admin` ← `fileutils`, `compileapp` (lazy import), `cache.CacheOnDisk`.

## Side effects
- Serving a request can create app folders, but only once per process.
- `compile_*` writes and deletes temporary `.py` files inside `compiled/`.
- `app_pack` deletes sessions, errors and cache.
- Startup writes `welcome.w2p` in the current working directory.
- `app_install`/`plugin_install` rewrite line endings of all `.py`/`.html` files in the target app.

## Compatibility constraints
- **[Compat]** The file layout `compiled/models.*.pyc`, `controllers.<c>.<f>.pyc` and `views.<path>.pyc`, plus the `models_*` and `views.<c>.<f>.pyc` legacy variants (`compileapp.py:577`, `:769-774`).
- **[Compat]** The exposure rules, including single-underscore exposure. Adding type hints (`-> dict`) to actions would un-expose them.
- **[Compat]** The model ordering and the mutable-mid-run `models_to_run`. The appadmin "run all models" exception.
- **[Compat]** The `generic_patterns` default `["*"]` at the framework level (welcome narrows it).
- **[Compat]** The `.w2p` format (a gzipped tar) and the `web2py.plugin.<name>.w2p` naming.

## Related tests
- `gluon/tests/test_compileapp.py`:
  - `TestPack.test_compile` (`:124-134`) covers compile, remove, pack (compiled and source) and unpack.
  - `test_admin_compile` (`:136-153`) covers `app_create`, `app_compile`, `app_cleanup` and `app_uninstall`.
  - `test_admin_test_runner_no_eval` (`:155-156`).
  - `test_admin_unzip_path_traversal` and the symlink case (`:182`, `:201`).
  - plugin_install path checks (`:40-101`).
- `gluon/tests/test_appadmin.py:224-228` covers the compiled index through `run_controller_in`/`run_view_in`.
- `gluon/tests/test_fileutils.py` covers untar symlink rejection.

## Known gaps in test coverage
- No direct test of `run_models_in` (ordering, `models_to_run` mutation, appadmin exception), `find_exposed_functions` / `REGEX_EXPOSED`, generic view fallback, `read_pyc` magic mismatch, the `DISABLED` 503, `create_missing_app_folders`, per-app `routes.py` discovery, `create_welcome_w2p`, `app_install`, `w2p_pack_plugin`, `PluginManager` (a `# TODO: class TestPluginManager` sits at `test_tools.py:2372`), or `tar_compiled` contents.

## Open questions
1. **[Suspected issue]** `listdir` compares `root` (a full path from `os.walk`) with `exclude_content_from` entries such as `"cache"` (`fileutils.py:183`), so the exclusion never matches. `app_pack` hides this by cleaning up first, but `app_pack_compiled`, `create_welcome_w2p` and `pythonanywhere.py:100` do not. The current `welcome.w2p` has only empty `sessions/`, `errors/` and `databases/` entries, because welcome had no content there.
2. **[Suspected issue]** `tar_compiled` drops every non-`.pyc` file under `modules*` (`fileutils.py:431-432`), and `compile_application` does not compile `modules/`. A compiled package may therefore ship without its importable app modules. **[Unverified]** at runtime.
3. **[Suspected issue]** `create_welcome_w2p` uses cwd-relative paths (`"welcome.w2p"`, `"applications/welcome"`), while `w2p_unpack` resolves `abspath("welcome.w2p")` against `applications_parent` (`fileutils.py:334-341` vs `:361`). They diverge if `web2py_path` differs from the cwd.
4. `MARSHAL_HEADER_SIZE` tests only the minor version (`compileapp.py:484`). The 12-byte branch is dead on Python 3.7+. **[Legacy]**
5. Compiled controllers duplicate the full controller source per exposed function. The size impact on large apps is **[Unverified]**.

## Discrepancies with the technical reference
| Reference | Source |
|---|---|
| §8 "strict alphabetical order" | depth first, then ASCII full-path order, filtered by the mutable `models_to_run`, with the appadmin exception (`compileapp.py:595-620`) |
| §7 functions "without required arguments" and not starting with `__` are exposed | the regex requires an empty parameter list (defaults count as parameters), a single `_` prefix is exposed, and a return annotation prevents exposure (`compileapp.py:548`) |
| §9 views compiled to bytecode | only in compiled apps. Source views are re-parsed per request. |
| §15 plugin view `views/plugin_<name>/<action>.html` | correct for controller `plugin_<name>`. Packing matches `*/plugin_<name>.*` and `*/plugin_<name>/*` only one level below the app root. |

## Modernization considerations (optional)
- Characterize `REGEX_EXPOSED` before any type-hinting effort in apps.
- Fix and test `exclude_content_from` (compare `root[n:]` or the basename).
- Consider caching parsed source views in `getcfs`, keyed on the view and all extended/included files.
