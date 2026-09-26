# 03 — HTTP Request Lifecycle

## Purpose

This document describes how one HTTP request goes through `gluon.main.wsgibase`, from the WSGI call to the iterable that is returned. It covers how the result is carried as an `HTTP` exception, the transaction (commit/rollback) semantics, session persistence order, static-file short-circuiting and `routes_onerror` re-entry.

Every statement comes from reading the source at commit `cb91b60c`. None of it was executed.

Labels: **[Current]** is behavior verified by reading. **[Compat]** is kept for old apps. **[Legacy]** is obsolete. **[Suspected issue]** is a likely defect based on static reading only. **[Unverified]** could not be confirmed.

## Relevant source files

| File | Role in the lifecycle |
|---|---|
| `gluon/main.py` | `wsgibase` (`:285-600`), `serve_controller` (`:160-223`), `get_client` (`:137`), `LazyWSGI` (`:226`) |
| `gluon/rewrite.py` | `fixup_missing_path_info` (`:181`), `url_in` (`:201`), `try_rewrite_on_error` (`:256`), `THREAD_LOCAL.routes` (`:36`) |
| `gluon/globals.py` | `Request` (`:291`), `Response` (`:649`), `Session` (`:1156`), `current` |
| `gluon/http.py` | `HTTP` exception and `HTTP.to()` (`:93-190`), `redirect()` (`:193`) |
| `gluon/streamer.py` | `stream_file_or_304_or_206` (`:51`), `streamer` (`:30`) |
| `gluon/compileapp.py` | `build_environment` (`:405`), `run_models_in` (`:581`), `run_controller_in` (`:668`), `run_view_in` (`:734`) |
| `gluon/restricted.py` | `restricted()` (`:304`), `RestrictedError.log` (`:256`) |
| `gluon/packages/pydal/pydal/connection.py` | `close()` (`:148`), `close_all_instances` (`:205`), which implement the commit and rollback |

## Main classes / functions

| Symbol | Location | Notes |
|---|---|---|
| `wsgibase(environ, responder)` | `main.py:285` | The WSGI app. It has three nested `try` levels (see below) and can call itself recursively for `routes_onerror`. |
| `serve_controller` | `main.py:160` | Runs models, the controller and the view, then **always ends with `raise HTTP(...)`** (`:223`). |
| `get_client(env)` | `main.py:137` | Returns the client IP. It uses the first IP-like token of `X-Forwarded-For`, then `REMOTE_ADDR`, and raises `HTTP(400)` if the result is invalid (`:155-156`). |
| `LazyWSGI` | `main.py:226` | `request.wsgi`, which exposes `environ`, `start_response` and `middleware` for embedding WSGI apps. |
| `HTTP` | `http.py:93` | An exception that carries status, body, headers and cookies. It is used for both success and errors. |
| `HTTP.to()` | `http.py:126` | Calls `responder(status, headers)` and returns the body iterable. |
| `Request.body` (property) | `globals.py:487-499` | Lazy. The first access copies `wsgi.input` into a `TemporaryFile` (`copystream_progress`, `:257`). |
| `Request.get_vars`, `post_vars`, `vars` | `globals.py:532-551` | Lazy parsing. `post_vars` reads the body (JSON, multipart, urlencoded; `:347-485`). |
| `Response.stream` | `globals.py:918` | For a `str` path it calls `stream_file_or_304_or_206`, which **always raises**. For file-like objects it returns a generator. |
| `Response.download` | `globals.py:994` | Calls `session.forget`, then resolves an upload field and calls `self.stream(...)`. |

The nesting of `try` blocks in `wsgibase` was checked by indentation:

```
try:                         # main.py:324  -> finally  (:583)
    try:                     # main.py:325  -> except:  (:560)  (bare)
        try:                 # main.py:326  -> except HTTP (:475), except RestrictedError (:534)
```

An exception raised **inside** the `except HTTP` or `except RestrictedError` handlers is caught by the bare `except:` at `:560`. The same applies to a failing session store and to a non-HTTP error in the static branch. **[Current]**

## Execution flow

### Steps with line references (`gluon/main.py`)

1. **Reset thread state.** `current.__dict__.clear()` (`:314`). `current.request` is *not* set again here. It is set later, in `build_environment` (`compileapp.py:434`). **[Current]**
2. **Construct objects.** `Request(environ)` (`:315`) copies the raw environ into `request.env` and then `env.update(global_settings)` (`globals.py:315-317`). `Response()` (`:316`) sets `status=200` and `X-Powered-By: web2py` (`globals.py:657-661`). `Session()` (`:317`).
3. **`fixup_missing_path_info(environ)`** (`:336`, `rewrite.py:181`). This fills in `PATH_INFO`/`QUERY_STRING` from `REQUEST_URI` (fcgi), `REQUEST_URI` from `PATH_INFO`, and `HTTP_HOST` from `SERVER_NAME:SERVER_PORT`.
4. **`url_in(request, environ)`** (`:337`) chooses parametric or pattern routing (see doc 04). It sets `request.application/controller/function/extension/args` and copies environ into `request.env` with **lowercased, dot→underscore keys** (`rewrite.py:701`, `:1227-1229`). As a result `request.env` holds both raw (`PATH_INFO`) and lowercased (`path_info`) keys. **[Current]**
5. `response.status = env.web2py_status_code or response.status` (`:338`). The value is non-empty only on a `routes_onerror` re-entry (`rewrite.py:298`).
6. **Static branch** (`:340-346`):
   - `QUERY_STRING` starting with `attachment` sets `Content-Disposition: attachment` (`:341-342`).
   - A versioned URL (`_x.y.z`) sets `Cache-Control: max-age=315360000` and `Expires: Thu, 31 Dec 2037` (`:343-345`).
   - `response.stream(static_file, request=request)` → `stream_file_or_304_or_206` **always raises `HTTP`**: 200, 206, 304, 403, 404 or 416 (`streamer.py:66-144`).
   - In `except HTTP`, `if static_file: return http_response.to(responder, env=env)` (`:478-479`). This skips the body close, session, DB commit, cookies, `session._unlock`, `routes_onerror` and soft cron. The `finally` at `:583` still runs. **[Current]**
7. **Local hosts** (`:353-367`). Computed once and cached in `global_settings.local_hosts` (loopback, hostname, FQDN and its resolved addresses).
8. **Request attributes** (`:368-386`):
   - `client = get_client(env)`. The first IP-like token of `X-Forwarded-For` wins (`:145`).
   - `ajax` comes from `X-Requested-With`, and `cid` from `web2py-component-element`.
   - `is_local = remote_addr in local_hosts and client == remote_addr` (`:376-378`).
   - `is_https` is true if any of `wsgi_url_scheme`, **`http_x_forwarded_proto`** or `env.https=="on"` says so (`:381-383`).
   - `request.url = environ["PATH_INFO"]` (`:385`). This is the *post-rewrite* `PATH_INFO` in pattern mode and the *incoming* path in parametric mode (see doc 04).
   - `parse_content_type()` (`:386`).
9. **Application checks** (`:392-420`):
   - If the folder is missing and `app == rwthread.routes.default_application` (and it is not `welcome`), `redirect(URL("welcome","default","index"))` (`:394-395`).
   - Otherwise, if `routes.error_handler` is set, redirect to it with `args=app` (`:396-405`).
   - Otherwise raise `HTTP(404, ..., web2py_error="invalid application")` (`:407-411`).
   - If a `DISABLED` file exists and the client is not local, return 503 with `static/503.html` or a built-in page (`:412-420`).
10. **`create_missing_app_folders(request)`** (`:425-430`). `OSError` is only printed.
11. **`request.wsgi = LazyWSGI(...)`** (`:442`). Reading `request.wsgi.environ` replaces `environ["wsgi.input"]` with `request.body` (`:236`).
12. **Cookies** (`:448-455`). The `Cookie` header is split on `;` and each piece is `load`ed. Invalid cookies are ignored one by one.
13. **`session.connect(request, response)`** (`:461-462`), unless `env.web2py_disable_session` is set. That value comes only from the WSGI environ key `WEB2PY_DISABLE_SESSION` after lowercasing. File sessions hold an exclusive lock until `_unlock` runs (see the session doc).
14. **Debugger hook** (`:468-472`). This runs if `global_settings.debugging` is set and the app is not `admin`. The flag becomes True as soon as `gluon.debug` is imported (`debug.py:209`).
15. **`serve_controller`** (`:474` → `:160-223`):
    1. `environment = build_environment(...)` (`:176`) sets `current.request/response/session/T/cache` (`compileapp.py:432-438`).
    2. `response.view = "c/f.ext"` (`:180-184`).
    3. `run_models_in(environment)` (`:191`).
    4. `response._view_environment = copy.copy(environment)` (`:192`). This is a **shallow snapshot taken after the models**, so names that the controller defines at module level are not visible to the view unless it returns them.
    5. `page = run_controller_in(...)` (`:193`). The action is called as `response._caller(function)` with no arguments (`compileapp.py:720`).
    6. If `page` is a dict: `response._vars = page`, update the view environment, then `run_view_in` (`:194-197`).
    7. GC runs every 100 requests unless `env.web2py_disable_garbage_collect` is set (`:199-205`). The module-global counter is not locked, which is harmless.
    8. Default headers are added with `setdefault`: `Content-Type` by extension, no-cache `Cache-Control`, `Expires`=now and `Pragma` (`:211-221`).
    9. **`raise HTTP(response.status, page, **response.headers)`** (`:223`).
16. **`except HTTP as hr`** (`:475-532`):
    - Static: early return (step 6).
    - `if request.body: request.body.close()` (`:481-482`). This *evaluates the lazy property*, so an unread body is copied to a temp file just so it can be closed. **[Current]**
    - `if hasattr(current, "request")` (`:484`). This block runs **only if `build_environment` ran**. When `HTTP` was raised earlier (url_in 400, missing app, `DISABLED` 503, `get_client` 400, anything inside `session.connect`), the code skips the session store, commit, component headers and `cookies2headers`. **[Current]**
    - `session._try_store_in_db` (`:489`). This happens **before** the commit, so the session row is inside the app's transaction.
    - Commit (`:495-500`):
      - `response.do_not_commit is True` → `close_all_instances(None)`.
      - Else if `response.custom_commit` is set → `close_all_instances(response.custom_commit)`.
      - Else `close_all_instances("commit")`.
    - `session._try_store_in_cookie_or_file` (`:507`). This happens **after** the commit, as the comment at `:503-505` says.
    - `request.cid` → `web2py-component-content: replace` (`:510-513`). For ajax requests, `web2py-component-flash` and `web2py-component-command` are set from `response.flash` and `response.js` (`:515-523`).
    - `session._fixup_before_save()` (`:529`) sets HttpOnly/Secure/SameSite, or deletes the cookie if the session was forgotten (`globals.py:1519-1531`). Then `http_response.cookies2headers(response.cookies)` (`:530`).
    - `ticket = None` (`:532`).
17. **`except RestrictedError as e`** (`:534-558`):
    - Close the body.
    - If `not request.tickets_db`, log the ticket **before** the rollback (`:543-544`).
    - Roll back through `response._custom_rollback()` or `close_all_instances("rollback")` (`:546-549`).
    - If `request.tickets_db` is set, log the ticket **after** the rollback (`:551-552`).
    - Return `HTTP(500, error_message_ticket, web2py_error="ticket ...")`.
    - The session is **not** saved and response cookies are **not** emitted.
18. **Bare `except:`** (`:560-581`):
    - Close the body.
    - Roll back, suppressing any error from the rollback itself.
    - `RestrictedError("Framework", "", "", locals()).log(request)`, falling back to `"unrecoverable"`.
    - Return 500.
    - It catches `BaseException`, including `SystemExit` and `KeyboardInterrupt`. **[Current]**
19. **`finally`** (`:583-585`) closes `response.session_file`.
20. **`session._unlock(response)`** (`:587`). Not reached on the static early return. Static requests never lock a session anyway.
21. **`try_rewrite_on_error`** (`:588-592`, `rewrite.py:256`). Status ≥ 399 plus a matching `routes_onerror` entry means one of:
    - `"!"` → no change.
    - An `http(s)://` target → a new `HTTP(303)`.
    - Otherwise `PATH_INFO`/`QUERY_STRING`/`WEB2PY_STATUS_CODE` are rewritten on the **same environ** and `wsgibase(new_environ, responder)` is called recursively. `__ROUTES_ONERROR__` limits this to one level.
22. **Soft cron** (`:594-598`) runs when `global_settings.web2py_crontype == "soft"`.
23. **`return http_response.to(responder, env=env)`** (`:600`).

### `HTTP.to()` (`gluon/http.py:126-166`)

- Status: a known int becomes `"NNN TEXT"` (`defined_status`, `:28-70`). An unknown int becomes `"NNN UNKNOWN ERROR"`. A string must match `^\d{3} [0-9A-Z ]+$`, otherwise it becomes `"500 INTERNAL SERVER ERROR"`.
- `Content-Type` defaults to `text/html; charset=UTF-8`.
- **For 4xx only**, an empty body becomes the status line and `Content-Length` is set (`:140-146`). Other statuses get no `Content-Length` from `to()`. **[Current]**
- List-valued headers such as `Set-Cookie` become repeated headers. **All** headers are emitted, including `web2py_error`, which is sent to the client as a response header (`:147-152`; for example `main.py:410`, `:557`). **[Current]**
- `HEAD` returns `[b""]` (`:154-155`).
- A `str` body is UTF-8 encoded. An iterable body is returned as is (streaming). Anything else goes through `str()`. A controller that returns `None` therefore produces the body `"None"` (static reading of `compileapp.py:727-731` and `http.py:162-166`). **[Unverified]** at runtime.
- `cookies2headers` (`:120-124`) *replaces* `Set-Cookie` with `str(morsel)[11:]`, which strips `"Set-Cookie:"` and leaves a leading space.
- Header values have CR/LF stripped in `__init__` (`:111-117`).

### `redirect()` (`gluon/http.py:193-227`)

- `javascript:`, `vbscript:` and `data:` targets are replaced by `/` (`:206-209`). CR/LF are percent-encoded.
- `client_side=True` with an ajax request raises `HTTP(200, web2py-redirect-location=...)` (`:211-213`).
- Otherwise it raises `HTTP(how=303, body, Location=...)`.
- **`redirect("")` without `client_side` returns `None` and does not redirect** (`:222-227`). **[Current]**

### Sequence diagram

```mermaid
sequenceDiagram
    participant S as WSGI server
    participant W as main.wsgibase
    participant R as rewrite
    participant G as globals (Request/Session)
    participant C as compileapp
    participant D as pydal BaseAdapter
    S->>W: environ, start_response
    W->>G: Request(environ), Response(), Session()
    W->>R: fixup_missing_path_info, url_in
    alt static file
        W->>W: response.stream -> raise HTTP(200/206/304/4xx)
        W-->>S: http_response.to()  (early return)
    else dynamic
        W->>G: cookies, session.connect (file lock)
        W->>C: build_environment (sets current.*), models, controller, view
        C-->>W: raise HTTP(status, page)   (success is an exception)
        W->>G: _try_store_in_db
        W->>D: close_all_instances("commit" | custom | None)
        W->>G: _try_store_in_cookie_or_file, _fixup_before_save
        W->>W: cookies2headers
        opt RestrictedError
            W->>D: close_all_instances("rollback") (ticket before/after)
        end
        W->>G: finally: close session_file; _unlock
        W->>R: try_rewrite_on_error
        opt routes_onerror internal path
            W->>W: wsgibase(new_environ)  (recursive, once)
        end
        W-->>S: http_response.to()
    end
```

## Transaction semantics

`close_all_instances(action)` (`connection.py:205-221`) walks **every DAL instance created on the current thread**. These are registered in `THREAD_LOCAL._pydal_db_instances_` by `DAL.__new__` (`pydal/base.py:199-225`). For each one it calls `adapter.close(action)` and then clears the registry. A callable `action` is also called once more as `action(None)` (`:220-221`).

| Outcome | DB action | Evidence |
|---|---|---|
| Normal page (`raise HTTP(200, page)`) | commit | `main.py:500` |
| `redirect()` (303) | **commit** | `http.py:216`, `main.py:475-500` (no status check) |
| User `raise HTTP(4xx/5xx)` in model, controller or view | **commit** | `restricted.py:316-317` re-raises `HTTP`. `main.py:475-500` has no status check. |
| 404 for a missing controller, function or view, *after the models ran* | **commit** | `compileapp.py:684-718`, `:787-791` |
| `HTTP` raised before `build_environment` (url_in 400, missing app, 503, bad client IP) | none (block skipped) | `main.py:484`, `compileapp.py:434` |
| `response.do_not_commit = True` | `close(None)`: no commit and no rollback. The connection is closed, or **pooled with an open transaction** if `pool_size` is set. | `connection.py:167-201`. **[Suspected issue]** in the pooled case. |
| `response.custom_commit = f` | `f(adapter)` for each adapter, then `f(None)` | `connection.py:171-173`, `:220-221` |
| `RestrictedError` | `response._custom_rollback()` (called **with no arguments**) or rollback | `main.py:546-549` |
| Any other exception, including one raised inside the `except HTTP` handler after the commit | rollback, which is a no-op if the commit already ran. Response is 500. | `main.py:560-574` |
| Commit fails in the per-adapter call (`commit` string action, or `custom_commit(adapter)`) | **The exception is swallowed**, the connection is dropped, and the response is still the success response | `connection.py:170-178` (`except Exception: succeeded = False`). **[Current]**, pinned by `test_c_transactions.py` (C4-silent) |
| A callable `custom_commit` raises in the final `custom_commit(None)` call | **Not swallowed**: the call at `connection.py:220-221` is unguarded, so the exception escapes the `except HTTP` handler into the bare `except` (`main.py:560-581`). Response is 500 with a "Framework" ticket | **[Current]**, pinned by `test_c_transactions.py` (C4-final) |
| Static file | none | `main.py:478-479` |

Notes:

- The asymmetry between `custom_commit` and `_custom_rollback` is **[Current]**. `Response.__init__` sets `_custom_commit = None` (`globals.py:671`), but `main.py:497` reads the public `custom_commit`. That attribute resolves to `None` through `Storage` unless the app sets it. The two hooks also have different call signatures.
- The DB session row is written before the commit (`main.py:489`). File and cookie sessions are written after it (`:507`). If the per-adapter commit fails silently (see the table above), the DB session update is lost without any error while the session cookie is still sent (pinned by `test_c_sessions_components.py`, C7).

## Dependencies

- `gluon.rewrite` (url_in, THREAD_LOCAL.routes, try_rewrite_on_error)
- `gluon.globals` (Request, Response, Session, current)
- `gluon.compileapp`
- `gluon.restricted`
- `gluon.http`
- `gluon.streamer`
- `gluon.fileutils` (`create_missing_app_folders`, `abspath`)
- `gluon.newcron` (soft cron)
- `gluon.debug` (optional)
- `pydal.base.BaseAdapter`, which provides `close_all_instances`

## Side effects

- Import of `gluon.main`: `create_missing_folders()` (`:58-61`), locale `C` (`:79`), logging config (`:81-84`), pydal monkeypatch (`:93`) and `load_routes()` (`:128`).
- Per request:
  - folders are created (`:426`)
  - the body is copied to a temp file when `Content-Length` is set (`globals.py:263-272`)
  - the session file is locked and written
  - tickets are written to `errors/` or the DB
  - `global_settings.local_hosts` is cached on first use (`:365`)
  - GC runs every 100 requests
- `routes_onerror` re-entry reuses and mutates the original `environ` (`rewrite.py:294-298`).

## Compatibility constraints

- **[Compat]** Success delivered as `raise HTTP`. `HTTP` is public API that apps catch and raise.
- **[Compat]** `response.custom_commit`, `response._custom_rollback` and `response.do_not_commit` names, and commit-on-any-`HTTP`. Apps rely on `raise HTTP(4xx)` after DB writes being committed.
- **[Compat]** `request.wsgi` (`LazyWSGI`), `web2py-component-*` headers (`web2py.js` depends on them), and `WEB2PY_DISABLE_SESSION`/`WEB2PY_USE_WSGI_FILE_WRAPPER`/`WEB2PY_DISABLE_GARBAGE_COLLECT` environ switches.
- **[Compat]** `routes_onerror` recursive dispatch, and the `code`/`ticket`/`requested_uri`/`request_url` query variables.
- **[Compat]** `?attachment` static query and `_x.y.z` static versioning.

## Related tests

| Test | Covers |
|---|---|
| `gluon/tests/test_http.py` (`TestHTTP.test_status_message`, `TestRedirect.*`, `TestContentDisposition.*`) | status text, redirect escaping and unsafe schemes, Content-Disposition |
| `gluon/tests/test_globals.py:716`, `:769` | `stream_file_or_304_or_206` range, with and without the wsgi file wrapper |
| `gluon/tests/test_globals.py:644-714` | `Response.stream` attachment filenames |
| `gluon/tests/test_globals.py:540-642`, `:890-921` | cookie flags and session loading by client |
| `gluon/tests/test_globals.py:970-1086` | multipart `post_vars` parsing |
| `gluon/tests/test_web.py:128` `testStaticCache` | end-to-end static serving and `_1.2.3` cache headers (real server) |
| `gluon/tests/test_web.py:94` `testRegisterAndLogin` | end-to-end dynamic request, session and redirect |
| `gluon/tests/test_main.py:13` | `save_password` only. The module is **not** imported by `gluon/tests/__init__.py`. |

## Known gaps in test coverage

- No unit test calls `wsgibase` directly. There is no characterization of:
  - the commit/rollback matrix above
  - the `hasattr(current,"request")` gating
  - the ticket-before/after-rollback ordering
  - exceptions raised inside the `except HTTP` handler
- `try_rewrite_on_error` (the function actually used) is untested. Only the unused `try_redirect_on_error` is tested (`test_routes.py:248`).
- `LazyWSGI`, the `DISABLED`/503 path, missing-app redirect and `error_handler`, soft cron, and the debugger hook have no tests.
- The `HEAD` handling and `web2py_error` header emission in `HTTP.to()` have no tests.

## Open questions

1. What happens when the request has an invalid `Content-Length`? `Request.body` raises `HTTP(400)` on every access (`globals.py:268-270`, not cached). If the app never reads the body, `main.py:481` raises inside `except HTTP`. The bare `except` at `:561` then raises again, and the `HTTP` escapes `wsgibase` without commit, rollback or `close_all_instances`. **[Suspected issue]**. Whether the WSGI server lets such a request through is **[Unverified]**.
2. Can a spoofed `X-Forwarded-For` make `is_local` true behind a proxy? `get_client` takes the *first* `X-Forwarded-For` entry. Behind a local reverse proxy that appends to the header, a client-sent `X-Forwarded-For: 127.0.0.1` gives `client == remote_addr == 127.0.0.1`, so `is_local` is True (`main.py:145`, `:376-378`). This bypasses the `DISABLED` check and other `is_local` gates. **[Suspected issue]**, depending on the deployment.
3. On `routes_onerror` re-entry, `wsgi.input` has already been consumed by the first pass. The error handler would see an empty body. **[Unverified]**
4. The `do_not_commit` + connection pool case: does pydal roll back pooled connections on reuse? No such rollback was found in `connection.py:83-108`. **[Suspected issue]**

## Discrepancies with the technical reference

| Reference (`web2py_technical_reference-v2.md` §2, §16) | Source |
|---|---|
| `current` is assigned when Request, Response and Session are instantiated | `current` is cleared at `main.py:314`. It is set only in `build_environment` (`compileapp.py:432-438`). |
| The action is called as `function(*request.args, **request.vars)` | It is called with no arguments: `response._caller(f)` → `f()` (`compileapp.py:720`, `globals.py:669`) |
| "db.commit() on all connections" on success only | Commit also happens on redirects and on any user-raised `HTTP`, including 4xx/5xx. The commit uses `close_all_instances`. pydal swallows commit errors raised in the per-adapter call, but an exception from the final `custom_commit(None)` call produces a 500 with a ticket. |
| Static versioning gives `max-age=31536000`, and Nginx must strip `/_1.2.3/` | web2py sets `max-age=315360000` (`main.py:344`) and strips the version itself (`rewrite.py:724`, `:1127-1129`). `URL()` adds the version only if `response.static_version_urls` is also set (`html.py:352-356`). |
| (Already in architecture-report §11) static via `stream_file_or_304`; ticket after rollback | Confirmed: `stream_file_or_304_or_206`, and file tickets are logged before the rollback |

## Modernization considerations (optional)

- Add characterization tests for `wsgibase` (WSGI-level, fake `environ`) before touching the control flow. The commit matrix and the session-order rules are the most important to pin.
- The commit error being swallowed in pydal is a submodule behavior. Any fix has to be made in gluon (for example by checking a status) or upstream.
