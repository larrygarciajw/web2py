# 04 — Routing (`gluon/rewrite.py`)

## Purpose

This document describes how web2py maps an incoming URL to application/controller/function/args, and how it builds outgoing URLs (`URL()`). It covers how `routes.py` files are loaded, the two routing engines (pattern and parametric), error rewriting (`routes_onerror`), and static-file versioning.

All statements come from reading the source at commit `cb91b60c`. Nothing was executed.

Labels: **[Current]** / **[Compat]** / **[Legacy]** / **[Suspected issue]** / **[Unverified]**.

## Relevant source files

| File | Role |
|---|---|
| `gluon/rewrite.py` (1579 L) | The whole routing engine |
| `gluon/main.py:110-113`, `:128`, `:337`, `:394-411`, `:588` | Load at import, call `url_in`, missing-app handling, `try_rewrite_on_error` |
| `gluon/html.py:188-451` (`URL`) | Outgoing URL construction, which calls `url_out` (`:438`) |
| `gluon/compileapp.py:684-718`, `:787-791` | 404 bodies taken from `THREAD_LOCAL.routes.error_message` |
| `applications/admin/controllers/default.py:1918` (`reload_routes`), plus `:278`, `:296`, `:333` | Runtime `gluon.rewrite.load()` |
| `examples/routes.parametric.example.py`, `examples/routes.patterns.example.py`, `applications/welcome/routes.example.py` | Configuration examples |

## Main classes / functions

| Symbol | Line | Purpose |
|---|---|---|
| `THREAD_LOCAL` | `:36` | `threading.local()`. `.routes` holds the active params `Storage` for this thread. |
| `REGEX_URL` | `:53-55` | Pattern-mode parser for `/a/c/f.e/args` |
| `REGEX_ARGS` | `:56` | `[^\w/.@=-]`. In pattern mode, illegal characters in args are **replaced with `_`**. |
| `REGEX_VERSION` | `:41` | `^(_[\d]+\.[\d]+\.[\d]+)$`, the static version segment |
| `REGEX_AT`, `REGEX_ANYTHING`, `REGEX_REDIRECT` | `:38-40` | `$name`, `$anything`, and `NNN->url` in `routes_in` |
| `_router_default()` | `:59` | Default parametric router (`default_application="init"`, `acfe_match`, `file_match`, `args_match`, ...) |
| `_params_default(app)` | `:87` | Default pattern params (`routes_in/out/app/onerror/apps_raw`, `error_message*`, `logging="off"`) |
| `load()` | `:344` | Reads and `exec`s the routes files and builds `params`, `params_apps` and `routers` |
| `compile_regex(k, v, env)` | `:465` | Completes and compiles pattern keys |
| `load_routers(all_apps)` | `:504` | Post-processes the parametric routers |
| `url_in` / `url_out` | `:201` / `:208` | Dispatch: `routers` present → parametric, else pattern |
| `regex_select`, `regex_uri`, `regex_filter_in`, `regex_url_in`, `regex_filter_out` | `:635`, `:611`, `:653`, `:688`, `:754` | Pattern engine |
| `MapUrlIn`, `map_url_in` | `:917`, `:1476` | Parametric inbound |
| `MapUrlOut`, `map_url_out` | `:1280`, `:1521` | Parametric outbound |
| `try_rewrite_on_error` | `:256` | Used by `wsgibase` (`main.py:588`) |
| `try_redirect_on_error` | `:304` | **Not called anywhere in production code** (grep). It is used only in `test_routes.py:258`. **[Legacy]** |
| `filter_url`, `filter_err` | `:786`, `:889` | Helpers for tests and doctests |
| `get_effective_router` | `:1575` | Returns a copy of an app's router (tests) |

## Execution flow

### 1. Loading (`load`, `:344-462`)

- **When it runs:**
  - at import of `gluon.main` (`main.py:128`)
  - after `-f/--folder` changes the path (`main.py:776`)
  - from admin's `reload_routes` and some install paths (`admin/controllers/default.py:278,296,333,1920`)
- `load()` with `app=None` **resets** `params_apps`, `params`, `THREAD_LOCAL.routes` and `routers=None` (`:354-360`).
- **Sources:** `rdict` (unit tests), `data` (a string), or a file. The root file is `abspath("routes.py")` and the per-app file is `applications/<app>/routes.py` (`:369-375`). A missing file means return without changes.
- **Execution:** `exec(data, symbols)` with `symbols = dict(app=app)` (`:377-379`). Routes files are arbitrary Python, and the per-app file can read `app`, which `applications/welcome/routes.example.py:31` relies on. A `SyntaxError` is logged and re-raised (`:380-385`).
- **Symbols collected** into `p = _params_default(app)`:
  - `routes_app`, `routes_in`, `routes_out` go through `compile_regex` (`:389-392`).
  - `routes_onerror`, `routes_apps_raw`, `error_handler`, `error_message`, `error_message_ticket`, `default_application`, `default_controller`, `default_function` and `logging` are copied as is (`:393-405`).
  - `routers` is converted to `Storage` (`:406-410`).
  - Every other name is ignored.
- **Base (`app=None`):**
  - Installs `params`, and `THREAD_LOCAL.routes` *for the loading thread only* (`:413-414`).
  - Creates `routers.BASE` from `_router_default()` updated with the user `BASE` (`:418-425`).
  - Scans `applications/*` that have a `controllers/` directory (`:431-439`). With routers, it copies BASE into each app router and rejects BASE-only keys (`:440-449`).
  - Recursively loads any per-app `routes.py` (`:450-451`).
  - Finally runs `load_routers(all_apps)` (`:453-454`).
- **Per app:** `params_apps[app] = p` (`:457`). An app routes file can update only `routers[app]`, and only when the root file defines `routers` (`:458-460`).
- **[Suspected issue]** Reloading is not atomic. `routers` is set to `None` (`:360`) and rebuilt and mutated in place over several steps (`:418-454`, `:504-608`) while other threads may be running `url_in`. During that window a request could be routed in pattern mode, or see half-processed routers (for example `controllers` still `"DEFAULT"` or `domains` not yet tuple-keyed).

### 2. `load_routers` (`:504-608`)

- Apps named in `routers` but not installed are added to the routers (for unit tests) (`:507-520`). Unknown keys raise `SyntaxError` (`:522-524`).
- **Normalization:**
  - `controllers`: `"DEFAULT"` becomes the set of `controllers/*.py` names plus `static` and the default controller (`:548-557`).
  - `languages` becomes a set.
  - `functions`: a list becomes `{default_controller: set}`, and the `default_function` string is added for legacy compatibility (`:533-540`).
- BASE-only keys are popped from app routers. `domain` is mapped into `BASE.domains` (`:543-547`).
- `BASE.applications`: `"ALL"` becomes the list of installed apps, which is then turned into a set (`:559-567`).
- `_acfe_match`, `_file_match` and `_args_match` are compiled. `path_prefix` is split (`:569-581`).
- `BASE.domains` is rewritten to `{(host, port): (app, ctlr, fcn)}`. An unknown app raises `SyntaxError` (`:589-608`).

### 3. Dispatch

`url_in` (`:201-205`) and `url_out` (`:208-253`) choose the engine from the module-global `routers`. The two engines are exclusive in practice:
- With `routers`, `routes_in` and `routes_out` are ignored (`:203-204`, `:759-760`).
- `routes_app` is still consulted by `map_url_in` (`:1488`).

`url_out` then adds scheme, host and port if `host` is True, or if `host` is None and `scheme` or `port` is given (`:244-252`).

### 4. Pattern mode (`routes_in` / `routes_out`)

1. `regex_select(env, request)` (`:635-650`):
   - If root `routes_app` exists, `regex_uri` computes an app name and `THREAD_LOCAL.routes = params_apps.get(app, params)`.
   - Otherwise `THREAD_LOCAL.routes = params`.
   - **Per-app params (per-app `routes_in`/`routes_onerror`/`error_message`) are selected only through `routes_app`.** The `app=` argument is never passed by production callers (grep: `:697`, `:757`, `:842`).
2. `regex_uri` (`:611-632`) builds the key `"<remote_addr>:<scheme>://<host>:<method> <path>"` (host without port, method lowercase). The first matching regex wins. Its `custom_env` (the 3rd tuple element) is merged into the environ, then `regex.sub(value, key)` is applied.
3. `compile_regex` (`:465-501`):
   - Adds `^`/`$`.
   - A key without `:` gets the prefix `^.*?:https?://[^:/]+:[a-z]+ `. A key with `:` but no `://` gets the protocol/host/method part inserted. A path without a leading `/` raises `SyntaxError`.
   - `$anything` becomes `(?P<anything>.*)` and `$name` becomes `(?P<name>\w+)`. In the replacement, `$name` becomes `\g<name>`.
   - Compiled with `re.DOTALL`.
4. `regex_filter_in` (`:653-675`):
   - Saves `WEB2PY_ORIGINAL_URI`.
   - A result of the form `NNN->url` raises `HTTP(NNN, location=url)`. This is raised *before* `request.env` is lowercased.
   - A query in the rewritten path is merged in front of the original query.
   - `REQUEST_URI` is rebuilt.
5. `regex_url_in` (`:688-751`):
   - **Lowercases the environ into `request.env`** (`:701`).
   - Unquotes the path and turns `\` into `/`. One trailing `/` is stripped.
   - `REGEX_URL.match`, or 400 `invalid path` (`:711-713`).
   - **Static:** `c == "static"`:
     - No file gives 404.
     - Spaces become `_` (`:722`).
     - A first segment matching `REGEX_VERSION` is split off as the version (`:724-725`).
     - The path is resolved with `abspath` and must equal the static folder or start with `static_folder + os.sep`, otherwise 400 (`:726-732`).
     - `request.application` is **not** set for static files in this mode.
   - **Dynamic:**
     - a/c/f fall back to `routes.default_*` (`:738-740`).
     - The extension defaults to `html`.
     - If the app is in `routes_apps_raw`, `request.args = None` and the app parses `request.raw_args` itself (`:743-745`). **[Compat]**
     - Otherwise args come from `REGEX_ARGS.sub("_", raw_args).split("/")` (`:747-748`).
6. **Pattern-mode quirks, from static reading of `REGEX_URL`:**
   - `(?P<s>.*)` follows `f` and `.e` with no required `/`. So `/a/c/my-page` parses as function `my` with args `['-page']`. **[Unverified]** at runtime.
   - **[Suspected issue]** `/app/static/_1.2.3` (a version segment and no file) gives `items == ["_1.2.3"]`, and `version, filename = items` (`:725`) raises `ValueError`. That is not an `HTTP` exception, so `wsgibase` handles it in its bare `except` as a 500 "Framework" ticket.
7. `regex_filter_out` (`:754-783`):
   - Returns the URL unchanged if `routers` exists.
   - Builds the same key form from the **lowercased** `request.env` (`http_host`, `remote_addr`, `wsgi_url_scheme`, `request_method`). With no env it uses `":http://localhost:get "`.
   - The first matching `routes_out` rule wins, and the query is re-appended.

### 5. Parametric mode (`routers`)

`map_url_in` (`:1476-1518`) runs these steps in order:

1. `THREAD_LOCAL.routes = params` (`:1480`).
2. `MapUrlIn.__init__` (`:920-974`):
   - Normalizes `PATH_INFO` to `"/"+path` and sets `WEB2PY_ORIGINAL_URI`.
   - Strips one trailing slash.
   - `args` = path segments. They are **not unquoted** here; the WSGI server has already decoded `PATH_INFO`.
   - Works out host and port, with scheme defaults 443/80.
3. `sluggify()` (`:1482`, `:1226-1229`) copies the lowercased environ into `request.env`.
4. `map_prefix()` (`:976-986`) strips `BASE.path_prefix` only if the whole prefix matches.
5. `map_app()` (`:988-1067`). The application is chosen in this order:
   1. arg0 in `BASE.applications` (when not `exclusive_domain`)
   2. arg0 when `applications` is empty
   3. `domains[(host, port)]`
   4. `domains[(host, None)]`
   5. the same arg0 checks again without the `exclusive_domain` guard
   6. `BASE.default_application`

   Then:
   - `acfe_match` is checked, else 400.
   - An app not in `routers` gives 400 "unknown application", unless it is `THREAD_LOCAL.routes.default_application` and not `welcome` (`:1037-1045`). That exception lets `wsgibase` redirect a missing `init` app to `welcome` (`main.py:394`).
   - The rest of the router settings are copied onto `map`.
6. `params.routes_app` → `THREAD_LOCAL.routes = params_apps.get(app, params)` (`:1488-1489`). This is explained below.
7. With `app=True` (used by `regex_select` and `filter_url(app=True)`), return the app name (`:1491-1492`).
8. `map_root_static()` (`:1069-1088`): a single arg in `root_static` (`favicon.ico`, `robots.txt`) gives `applications/<app>/static/<file>`.
9. Language and controller order (`:1500-1510`): see the analysis of `:1502` below. In practice the order is always `map_language()` then `map_controller()`.
   - `map_language` (`:1090-1100`): arg0 in `languages` becomes the language, else `default_language`. The arg is popped only if it matched.
   - `map_controller` (`:1102-1118`): with hyphen mapping, arg0 is used if it is in `controllers` (or if no list is set), else `default_controller`. `acfe_match` is checked, else 400.
10. `map_static()` (`:1120-1177`):
    - Only for `controller == "static"`.
    - An optional `_x.y.z` version is taken from the first arg.
    - `file_match` is checked against the whole path if the pattern contains `/`, otherwise per segment with `""`, `.` and `..` rejected. A bad path gives 400.
    - With a language, `static/<lang>/<file>` is tried first, falling back to `static/<file>`.
11. `map_function()` (`:1179-1212`):
    - `functions[controller]` restricts the names. `default_function` may be a per-controller dict. A domain function takes priority.
    - `f.ext` is split.
    - `acfe_match` is checked for the function and the extension, else 400.
12. `validate_args()` (`:1214-1224`): every arg must match `args_match`, else **400**. Pattern mode *substitutes* the characters instead.
13. `update_request()` (`:1231-1260`):
    - Sets `request.application/controller/function/extension/args/uri_language`.
    - **Rewrites `env["REQUEST_URI"]`** to the canonical `/app[/lang]/c/f[.ext]/args?query` (hyphenated if `map_hyphen`).
    - `PATH_INFO` is left as received, so `request.url` (`main.py:385`) is the *incoming* path in this mode and the *rewritten* path in pattern mode. **[Current]**
    - Calls `sluggify()` again.

**Outbound: `MapUrlOut`** (`:1280-1473`):
- **Router choice:** the application's router if it has one, otherwise BASE. A cross-domain URL with `exclusive_domain` and no host raises `SyntaxError` (`:1335-1341`).
- **Language:** the explicit `language` is used, otherwise `request.uri_language`, and it is kept only if it is in `languages` (`:1343-1347`). `omit_lang` drops the default language (`:1354-1357`).
- **Omitting parts:** `omit_acf` drops the default app, controller and function, but keeps them when an omission would be ambiguous. It checks collisions against `applications`, `controllers` and `functions` (`:1359-1426`). Static URLs keep the app unless `map_static` is truthy, and keep the controller and function (`:1431-1437`).
- **Assembly:** `build_acf` handles hyphens and `path_prefix`. With `map_static is False` it emits `/app/static/<lang>/...` (`:1439-1465`).

### 6. Suspected issues at `:1489` and `:1502`

- **`:1489` is confirmed by reading.** `THREAD_LOCAL.routes = params_apps.get(app, params)` uses the *function parameter* `app`, which is `False` (from `url_in`) or `True` (from `regex_select` and `filter_url`). `params_apps` has only string keys (`:457`). `False` and `True` hash like `0` and `1`, so they never match. The expression therefore always returns `params`. The likely intent was `map.application`.
  - Consequence: in parametric mode, per-app `routes_onerror`, `error_message` and `error_message_ticket` from `applications/<app>/routes.py` are **never selected**. Only the root file's values are used.
  - Label: **[Suspected issue]**. The code path is certain. That it is unintended is inferred.
- **`:1502` is confirmed by reading.** `map.map_static is False`: `map` is a `MapUrlIn`, and `map_static` is a *method* on it (`:1120`). No instance attribute of that name is ever assigned (`__init__` `:920-974` and `map_app` `:1047-1067` copy other router fields, but not `map_static`). The bound method is never `False`, so the branch at `:1506-1507` is dead code.
  - Outbound, `MapUrlOut` does copy `router.map_static` (`:1323`), so with `map_static=False` it emits `/app/static/<lang>/file` (`:1452-1453`). Inbound, that URL is handled by the ordinary path, which resolves `static/<lang>/file` literally with no language fallback.
  - `test_router.py:1817-1820` **pins this current behavior**: `/examples/static/it-it/file` resolves to `static/it-it/file`. If the flipped branch were active, the same URL would fall back to `static/file`.
  - Label: **[Suspected issue]**, low impact.

### 7. Errors

- **`try_rewrite_on_error`** (`:256-301`):
  - Applies when status **≥ 399** and `routes_onerror` is set. Keys are matched against `"app/status"`, `"app/*"`, `"*/status"` and `"*/*"` in list order.
  - `"!"` means no rewrite.
  - The query string gets `code`, `ticket`, `requested_uri` and `request_url` (both `quote_plus`'d, `:280-285`).
  - An `http(s)://` target gives a 303 response.
  - Otherwise the function sets `__ROUTES_ONERROR__`, `PATH_INFO`, `QUERY_STRING` and `WEB2PY_STATUS_CODE` and returns `None`, and `wsgibase` recurses (`main.py:591-592`).
  - In parametric mode `requested_uri` is the *canonicalized* `REQUEST_URI` (`:1259`), not the client's.
- **`try_redirect_on_error`** (`:304-341`) and **`filter_err`** (`:889-910`) use `status > 399`, which is inconsistent with `>= 399`. **[Current]**
- **`error_handler`** (a dict with application, controller and function) is used only for a missing app folder (`main.py:396-405`).
- **`error_message` / `error_message_ticket`** are the bodies for the 400/404/500 responses, taken from `THREAD_LOCAL.routes` (`main.py:409`, `:556`; `compileapp.py:685-789`).

### 8. Interaction with `URL()` and static versioning

- `URL()` (`html.py:188`):
  - Takes the defaults from `current.request` when it exists (`:314-324`). Before `build_environment` there is no request, so `url_out(None, None, ...)` is used (for example `main.py:395`).
  - For `c == "static"`, the extension is cleared. If **both** `response.static_version` and `response.static_version_urls` are set, the version segment `_<version>` is inserted before the path (`:346-356`). Only an `x.y.z` numeric version is recognized inbound (`REGEX_VERSION`).
  - Calls `url_out(r, env, a, c, f, args, other, scheme, host, port, language)` (`:438-450`).
- Inbound, the version is stripped by the router (`:724`, `:1127-1129`). `wsgibase` then adds 10-year cache headers (`main.py:343-345`).

### 9. `request.env` lowercasing

Both engines copy the environ into `request.env` with `k.lower().replace(".", "_")` (`:701`, `:1228`). `Request.__init__` has already stored the raw keys and `global_settings` (`globals.py:315-317`), so `request.env` holds both key forms. Framework code reads the lowercase form, for example `http_x_forwarded_proto`, `wsgi_url_scheme` and `web2py_status_code`. **[Compat]**

## Dependencies

`gluon.http.HTTP`, `gluon.storage` (`Storage`, `List`), `gluon.settings.global_settings` (`applications_parent`), `gluon.fileutils` (`abspath`, `read_file`), `re`, `threading`, `urllib.parse`. The module has no dependency on `gluon.main`. The dependency goes the other way.

## Side effects

- It `exec`s `routes.py` files with full privileges at import and reload.
- It lists `applications/` and each `controllers/` directory at load time (`:433`, `:552`).
- It mutates the global `params`, `params_apps` and `routers`, `THREAD_LOCAL.routes`, and the WSGI `environ` (`PATH_INFO`, `QUERY_STRING`, `REQUEST_URI`, `WEB2PY_ORIGINAL_URI`, `domain_*`).
- Logging is controlled by `logging` in `routes.py` (`:117-134`).

## Compatibility constraints

- **[Compat]** Both engines, and `routes.py` as executable Python with the `app` symbol for per-app files.
- **[Compat]** Symbol names (`routes_in/out/app/onerror/apps_raw`, `error_handler`, `error_message*`, `default_*`, `logging`, `routers`) and router keys (`ROUTER_KEYS`, `:137-158`).
- **[Compat]** `$name`/`$anything` syntax, the `NNN->url` redirect in `routes_in`, and the 3-tuple custom env.
- **[Compat]** `routes_apps_raw` (`request.args=None`), `request.raw_args`, `request.uri_language`, and `env.web2py_original_uri`.
- **[Compat]** The legacy `functions` list form (`:533-538`) and the default `init`→`welcome` behavior.
- **[Compat]** `filter_url` and `filter_err`. They are used by the tests and by the doctest in `examples/routes.patterns.example.py:117-141`.

## Related tests

| File | Tests | Coverage |
|---|---|---|
| `gluon/tests/test_router.py` | 24 | Parametric mode: syntax errors (`:81`), null and default app, specific per-app file (`:172`), domains and `exclusive_domain` (`:611-1054`), raise cases, outbound incl. `map_static` (`:1121`), functions (`:1190`, `:1370`), `map_hyphen` (`:1439`), languages and language-static (`:1518`), `get_effective_router`, `filter_err`, static path validation (`:1881`), args (`:2002`), anchors, `path_prefix` (`:2117`), absolute URLs, `request_uri`, app/controller collision (`:2241`) |
| `gluon/tests/test_routes.py` | 12 | Pattern mode: null, query, `routes_app` per-app selection (`:147`), `default_application`, raise cases, `filter_err`, `try_redirect_on_error` URL encoding (`:248`), `routes_in` with host/method keys (`:264`), anchors, absolute URLs, `request_uri`, static prefix-sibling traversal (`:529`) |
| `gluon/tests/test_html.py:59-68` | – | `URL()` with `static_version` + `static_version_urls` |
| `gluon/tests/test_web.py:128` | – | End-to-end `_1.2.3` static request |

## Known gaps in test coverage

- `try_rewrite_on_error`, the function used in production, and the recursive `routes_onerror` dispatch are untested. The only onerror test targets the unused `try_redirect_on_error`.
- Per-app `routes_onerror` in parametric mode is untested, which is why `:1489` went unnoticed.
- `routes_apps_raw`, the `NNN->url` redirect, the 3-tuple custom env, `error_handler`, versioned static in pattern mode (including the `_1.2.3`-only case), and `load()` from real files have no tests.
- There is no concurrency test for `load()` during requests.

## Open questions

1. Is `map_static=False` inbound flipping (`:1500-1507`) used by any deployment? Fixing `:1502` would change `test_router.py:1817-1820`.
2. Should per-app `routes_onerror` be effective in parametric mode (`:1489`)? The documentation in `examples/routes.parametric.example.py:117-130` (commented `routes_onerror` at `:127`) presents `routes_onerror` only at root level.
3. `main.py:394` and `rewrite.py:1038` use `params.default_application`, the root pattern symbol with default `init`, even in parametric mode where `routers.BASE.default_application` is the documented setting. Their behavior diverges when only `BASE.default_application` is set. **[Unverified]** impact.

## Discrepancies with the technical reference

| Reference (§6, §16) | Source |
|---|---|
| Only a root `routes.py` is mentioned | Per-app `applications/<app>/routes.py` is also loaded (`:450-451`). In parametric mode it can only update `routers[app]`. |
| Parametric routing "adds a `/es/` prefix" | The default language is omitted from outgoing URLs (`omit_lang`, `:1354-1357`). Only non-default languages are prefixed. |
| `routes_onerror` rewrites "without altering the client URL" | This holds only for internal paths (recursive `wsgibase`). `http(s)://` targets produce a 303 (`:286-290`). Per-app `routes_onerror` is ignored in parametric mode (`:1489`). |
| The static version must be stripped by Nginx | web2py strips it itself (`:724`, `:1127`). `URL()` also requires `static_version_urls` (`html.py:352`). |
| Example `routes_out = [(x, y) for (y, x) in routes_in]` | This works only for rules without regex groups. `$name` in the *replacement* is converted to `\g<name>` (`:499-500`), but a regex key cannot be reversed automatically. **[Unverified]** for the specific example. |
| `examples/routes.parametric.example.py:85,93-94` defaults (`functions=None`, `file_match`, `args_match`) | The code defaults differ: `functions=dict()`, and `args_match=r"([\w@ =-]|(?<=[\w@ =-])\.)*$"` (`:67`, `:81-82`) |

## Modernization considerations (optional)

- Add characterization tests for `try_rewrite_on_error`, per-app parametric `routes_onerror`, and pattern-mode `/app/static/_1.2.3` before touching `:1489`, `:1502` or `:725`.
- Make `load()` build new structures and publish them with a single assignment, so that readers never see partial state.
