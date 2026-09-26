# 08 — Auth, Sessions and Cache

## Purpose

This document describes three state-keeping subsystems: the per-user **session** (`gluon.globals.Session`), **authentication/authorization** (`gluon.authapi.AuthAPI`, `gluon.tools.Auth`), and the **cache** (`gluon.cache`). It covers storage backends, serialization, locking, cookie handling, login flows and cache key composition. Admin-app authentication is covered only briefly here; doc 11 covers it in depth.

Every statement comes from reading the source at commit `cb91b60c`. Nothing was executed.

Labels: **[Current]** is behavior verified by reading. **[Compat]** is kept for old apps. **[Legacy]** is obsolete. **[Suspected issue]** is a likely defect based on static reading only. **[Unverified]** could not be confirmed.

## Relevant source files

| File | Role |
|---|---|
| `gluon/globals.py` | `Session` (`:1156-1754`), `pickle_session` (`:1757-1761`) |
| `gluon/utils.py` | `secure_dumps` (`:220`), `secure_loads` (`:238`), `*_deprecated` (`:291`, `:314`), `web2py_uuid` (`:421`), `safe_path_join` (`:566`), `compare` (`:85`) |
| `gluon/restricted.py` | `SafeUnpickler` (`:47`), `safe_load`/`safe_loads` (`:108-115`), `DEFAULT_SAFE_GLOBALS` (`:39`) |
| `gluon/recfile.py` | Hashed sub-folder file layout used by sessions and the disk cache |
| `gluon/authapi.py` | `AuthAPI` (`:29`) |
| `gluon/tools.py` | `AuthJWT` (`:1241`), `Auth` (`:1617`) |
| `gluon/html.py` | `URL(..., user_signature/hmac_key)` (`:394-418`), `verifyURL` (`:454-577`) |
| `gluon/packages/pydal/pydal/validators.py` | `LazyCrypt` (`:4452`), `CRYPT` (`:4542`) |
| `gluon/cache.py` | `CacheInRam` (`:178`), `CacheOnDisk` (`:288`), `CacheAction` (`:530`), `Cache` (`:555`), `lazy_cache` (`:794`) |
| `gluon/contrib/redis_session.py`, `memdb.py`, `redis_cache.py`, `memcache/`, `gae_memcache.py` | Optional backends |
| `gluon/contrib/login_methods/` | 22 alternate login modules |
| `applications/welcome/models/db.py`, `private/appconfig.ini` | Reference Auth/DB configuration |
| `applications/admin/models/access.py`, `gluon/fileutils.py` | Admin password check; `check_credentials` (`:510`) |

## Main classes / functions

### Session storage selection (`Session.connect`, `globals.py:1190`)

`wsgibase` calls `connect` once with no backend (`main.py:461-462`). Models may call it again. Selection order (`:1256-1268`):
1. `cookie_key` set → `"cookie"`.
2. else `db` set → `"db"`.
3. else `"file"`. If `global_settings.db_sessions` is `True` or contains `masterapp`, it **returns immediately**. This lets the framework's first call defer to a later DB `connect` from the model. `db_sessions` is a process-wide `set` (`settings.py:21-22`), filled at `:1346-1347` and pruned at `:1662-1666`. **[Current]**

The cookie names are `session_id_<masterapp>` and `session_data_<masterapp>` (`:1241-1242`). `masterapp` lets several apps share one session store (SSO). **[Current]**

### File backend [Current]

- Validates the cookie against `REGEX_SESSION_FILE = r"^(?:[\w-]+/)?[\w.-]+$"` (`:1188`, `:1302`), then builds the path with `safe_path_join(<apps>/<masterapp>/sessions/<id>)` (`:1306-1311`).
- `check_client`: the prefix of the file name (client IP with `:`→`.`) must equal the current client (`:1312-1314`).
- Opens the file with `recfile.open(..., "rb+")` and takes `portalocker.LOCK_EX` (`:1315-1319`). **The lock is held until `_try_store_in_file` finishes or `_unlock`/`_close` runs** (`main.py:583-587`), so concurrent requests on one session are serialized. `session.forget()` releases the lock early (`:1615-1617`).
- Loads with `pickle.load` or `safe_load` (`:1320-1327`). Any exception yields a fresh session (`:1330-1331`).
- New id: `"<client>-<web2py_uuid()>"` (`:1333-1334`).
- **[Suspected issue]** `separate = separate and (lambda s: s[-2:])` (`:1335`) replaces any user-supplied callable with the default. The docstring (`:1216-1219`) says a function is accepted. This is already noted in `architecture-report.md` §9.17.
- **[Suspected issue]** `renew()` decides whether to keep the `separate` prefix with `session = response.session` (`:1450`) and `if session and response.session_id[2:3] == "/"` (`:1464`). Nothing in gluon assigns `response.session` (grep), so `session` is always `None`. The check also inspects the newly generated id, which has no prefix yet. As a result `renew()` silently drops the `xx/` sub-folder for apps that use `separate=True`.
- Writing (`_try_store_in_file`, `:1707-1737`): skipped if there is no id, `_forget` is set, or `_unchanged`. Otherwise it creates the sub-folder, opens `"wb"` and locks it for new sessions, writes the pickle, truncates, and in `finally` closes the file and calls `save_session_id_cookie`.

### DB backend [Current]

- Table `web2py_session_<masterapp>` (`:1358-1371`) with fields `locked` (bool), `client_ip`, `created_datetime`, `modified_datetime`, `unique_key`, `session_data` (`blob`). `migrate` is used only when `masterapp == request.application` (`:1354-1357`).
- The cookie value is `"<record_id>:<unique_key>"`. Lookup uses `table(record_id, unique_key=unique_key)` (`:1376-1384`), plus `client_ip` if `check_client` (`:1385-1388`).
- There is **no row locking**: `locked` is always written as `0`, and the `update_record(locked=True)` line is commented out (`:1390`, `:1683`). Concurrent requests use last-writer-wins. **[Current]**
- Stored by `_try_store_in_db` (`:1652-1699`) **before** the request commit (`main.py:488-489`). A `do_not_commit` response or a later commit failure therefore also discards the session write.
- On GAE-flagged runtimes `request.tickets_db = db` (`:1352-1353`).
- The redis backend (`contrib/redis_session.py:25`) and memcache/GAE backend (`contrib/memdb.py:125`) plug into this same code path. They are duck-typed DAL look-alikes that expose `define_table`, `Field`, `get` and `table(id, unique_key=…)`. `RedisSession(with_lock=True)` provides locking that the SQL backend lacks.

### Cookie backend

- Load: `secure_loads(cookie_value, cookie_key, compression_level, …)` (`:1271-1293`). `response.session_id = True` (`:1294`).
- Save: `_try_store_in_cookie` (`:1619-1638`) calls `secure_dumps(dict(self), key, …)` and assigns the result to `response.cookies[session_data_name]` (`:1631`).
- `secure_dumps` returns **bytes**, `b"hmac256:" + sig + b":" + b64(IV+AES-CBC(pickle))` (`utils.py:220-235`). The HMAC key is `sha256(encryption_key)` when no `hash_key` is given.
- `secure_loads` begins with `data.count(b":")` (`utils.py:247`).
- **[Suspected issue] Cookie sessions probably cannot round-trip.** `http.cookies.SimpleCookie` converts a non-str value with `str()`, which produces the text `"b'hmac256:…'"`. The browser sends back that text, and `SimpleCookie` gives it to `secure_loads` as a `str`. Calling `str.count(b":")` raises `TypeError`, and the call is not inside a `try` in `connect`. The existing tests (`test_globals.py:601-629`) only write the cookie and check its attributes. No test reads it back. Earlier noted in `architecture-report.md` §9.2.
- **[Suspected issue]** When the data is unchanged, and on every request through `_try_store_in_db`'s early exit (`:1657-1670`), `save_session_id_cookie` (`:1549-1571`) emits `session_id_<app>=True`, because `response.session_id` is the boolean `True` in cookie mode (`:1564-1565`). `connect` guards this with `isinstance(..., str)` (`:1430`), but `save_session_id_cookie` has no such guard.
- Legacy `secure_loads_deprecated` (HMAC-MD5, space padding) is accepted when the value has exactly one `:` (`utils.py:248-256`). **[Compat]**

### Serialization

- Every backend uses `pickle.HIGHEST_PROTOCOL`. `Session` pickles as `(Session, (dict,))` through `copyreg` (`globals.py:1757-1761`), `Storage` pickles as `(Storage, (dict,))` (`storage.py:145-149`), and `lazyT` is flattened to `str` (`languages.py:440-444`).
- `connect(safe_unpickle=False)` is the default (`:1203`), which means **unrestricted `pickle.load(s)`** for file and DB, and `secure_loads(..., safe_unpickle=False)` for cookies (`:1286-1291`). **[Compat]**
- `SafeUnpickler` (`restricted.py:47-105`) allows a fixed set of builtins, `decimal.Decimal`, `datetime.*`, `uuid.UUID` and `pydal.objects.Row/Rows` (`:39-44`), plus `pickle_allowed_classes`.
- **[Suspected issue]** `gluon.globals.Session` and `gluon.storage.Storage` are **not** in the default whitelist. With `safe_unpickle=True` and no `pickle_allowed_classes`, every file or DB session that web2py itself wrote (a pickled `Session` holding `Storage` objects such as `session.auth`) should raise `UnpicklingError`. That error is swallowed (`:1330`, `:1402-1409`), so the result is a new, empty session on every request. The tests only cover malicious payloads and the legacy path (`test_restricted.py:183-272`), not a legitimate round-trip.
- Change detection: `connect` stores `md5(pickle(self))` (`:1438-1439`). `_unchanged` recomputes it and caches the pickle in `response.session_pickled` (`:1640-1650`). New sessions that contain only internal keys (`_last_timestamp`, `_secure`, `_start_timestamp`, `_same_site`) are treated as unchanged (`:1641-1646`).

### Cookie flags

`_fixup_before_save` (`:1519-1531`, called at `main.py:529`) deletes the id cookie if the session is forgotten. Otherwise it applies `_set_cookie_security_attrs` (`:1503-1517`) to the id and data cookies: `HttpOnly` unless `session.httponly_cookies` is falsy, `secure` if `session.secure()` was called, and `SameSite=Lax` by default. `session.samesite(False)` disables SameSite. **[Current]** `renew(clear_session)` (`:1444`) issues a new file id, or a new `unique_key` for DB sessions. For cookie sessions it does nothing (`:1454-1455`).

### Auth

| Aspect | Evidence | Label |
|---|---|---|
| `AuthAPI` is a dict-in/dict-out core with no forms. Its docstring says **"No builtin CSRF protection whatsoever"** | `authapi.py:44` | [Current] |
| On construction, an expired `session.auth` causes `session.renew(clear_session=True)`. `last_visit` is refreshed only when `(now-last_visit).seconds > expiration//10` | `authapi.py:122-134`; same code in `tools.py:1933-1945` | [Current] |
| **[Suspected issue]** `timedelta.seconds` ignores whole days. With `long_expiration` (30 days, "remember me") a gap such as 2 days + 10 s gives `.seconds == 10`, so `last_visit` may not be refreshed and the session can expire earlier than the sliding window implies | `authapi.py:127`, `tools.py:1938` | [Suspected issue] |
| Base tables: `auth_user`, `auth_group`, `auth_membership`, `auth_permission`, `auth_event` | `authapi.py:263-593` | [Current] |
| `auth_cas` is defined `if settings.cas_domains`, and `Auth.__init__` **always** sets `cas_domains=[host]`, so `auth_cas` is created by default | `tools.py:1961`, `:2515-2534` | [Current] |
| `auth_token` only with `define_tables(enable_tokens=True)` | `tools.py:2535-2560` | [Current] |
| `log_event` inserts into `auth_event` unless `logging_enabled` is off or the description is empty. `lazyT` descriptions are logged untranslated | `authapi.py:595-616` | [Current] |
| Password field validator `CRYPT(key=settings.hmac_key, min_length=password_min_length)`. `hmac_key` defaults to `None`, and `password_min_length` defaults to 4 | `authapi.py:308-310`, `:62`; `tools.py:2009` | [Current] |
| `CRYPT` default `digest_alg="pbkdf2(1000,20,sha512)"`, salted | `pydal/validators.py:4626` | [Current] |
| `LazyCrypt.__eq__` ends with a plain `temp_pass == stored_password`, which is not constant-time. Unsalted legacy hashes are recognized by length | `pydal/validators.py:4504-4536` | [Compat] |
| `Auth.get_or_create_key()` writes `alg:uuid` to `private/auth.key` (not atomic, file handles not closed). It is **not** called by welcome, so welcome runs with `hmac_key=None` | `tools.py:1828-1837`; `welcome/models/db.py:95` | [Current] |
| On login, `_update_session_user` removes the password and callables from the user row and stores `session.auth = Storage(user, last_visit, expiration, hmac_key=web2py_uuid())` | `authapi.py:934-950` | [Current] |
| `login_user` calls `session.renew` when `renew_session_onlogin` is set | `authapi.py:952-960` | [Current] |
| `login_bare(username, password)` validates through the field's `CRYPT` and compares against the stored hash. For unknown users it tries the other `settings.login_methods` | `tools.py:2727-2746` | [Current] |
| `Auth.login` (form flow) | `tools.py:2983-3450` | [Current] |
| 2FA: a 6-digit code from `secrets.randbelow(900000)+100000`, sent by email or replaced by `two_factor_methods` / `two_factor_onvalidation` (TOTP hooks). `None` codes are rejected. The attempt limit is `auth_two_factor_tries_left` (3). The comparison is a plain `==` on strings | `tools.py:3276`, `:3350-3410`, `:3372-3374` | [Current] |
| "Remember me" sets `session.auth.expiration = long_expiration` and `response.session_cookie_expires` | `tools.py:3420-3429`, `:2051-2053` | [Current] |
| `requires(condition, requires_login, otherwise)` is the base decorator. It returns 401 for ajax, 403 for basic/REST, and otherwise redirects to `login_url?_next=`. `requires_login`, `requires_membership`, `requires_permission` and `requires_signature` wrap it | `tools.py:4634-4768` | [Current] |
| **[Suspected issue]** `requires_signature(hash_extension=…)` ignores its argument and always passes `hash_extension=True` | `tools.py:4752-4768` (`:4765`) | [Suspected issue] |
| URL signing: `URL(user_signature=True)` uses `session.auth.hmac_key` (per login). Signature is `simple_hash(..., digest_alg="sha1")` (HMAC-SHA1). `verifyURL` compares with `compare()` (constant-time) | `html.py:394-418`, `:501-577` | [Current] |
| Impersonation pickles the whole session into `session.auth.impersonator`. Restoring runs `session.clear()` (which deletes the file or row) and then `session.update(pickle.loads(...))` | `tools.py:4577`, `:4585-4590` | [Current] |
| `AuthJWT` ("Experimental!"): HS256/384/512 only, `compare()` on the signature, `max_header_length` 4 KiB | `tools.py:1241-1339`, `:1397-1399` | [Current] |
| **[Suspected issue]** With `salt` set, `generate_token` formats the **bytes** secret (`"%s$%s" % (b"key", salt)` → `"b'key'$salt"`), while `load_token` formats the **str** secret (`"key$salt"`). The two HMAC keys differ, so salted tokens should always fail verification. There is no test that uses `salt` | `tools.py:1382-1389` vs `:1408-1415` | [Suspected issue] |
| `login_methods` contrib: basic, cas, email, ldap, pam, x509, saml2, oauth10a/20, openid, janrain/rpx, loginza, oneall, loginradius, dropbox, linkedin, browserid, motp, freeipa, gae_google, extended_login_form | `gluon/contrib/login_methods/` | [Legacy] mostly |

### `Auth.url` and host allowlist

- `Auth.__init__` calls `select_host(request.env.http_host, host_names)`, which returns **the request's own Host** if it matches any glob, otherwise raises 403. `settings.host` is pinned to that value only when `host_names` is given (`tools.py:1880-1897`, `:1959`, `:2014-2019`).
- `Auth.url(scheme=True)` without `settings.host` and without `host_names` raises 500 instead of trusting the Host header (`tools.py:1839-1875`).
- Welcome passes `host_names=configuration.get("host.names")` (`welcome/models/db.py:95`), whose value is `localhost:*, 127.0.0.1:*, *:*, *` (`private/appconfig.ini:13`). Because `*` matches any Host, `settings.host` becomes whatever Host the client sent, and absolute reset and verify links follow it. **[Current]**, earlier noted in the report §9.6.
- **[Suspected issue]** `AppConfig.get` returns a one-shot `map` object for comma-separated values (`contrib/appconfig.py:73-74`). `select_host` consumes it during `Auth.__init__`, and `settings.host_names` keeps the exhausted iterator. A later `select_host` call (from `Auth.url` when `settings.host` is unset) would find no match and return 403. `host_names[0]` on a `map` raises `TypeError` when there is no Host header (`tools.py:1893-1894`). The tests use plain lists (`test_tools.py:1972-2078`).

### Admin authentication (brief; see doc 11)

`applications/admin/models/access.py` requires HTTPS, a local client or a `request.env.trusted_lan_prefix` match (`:23-29`). It loads `parameters_<port>.py` through `restricted()` (`:31-35`). `verify_password` compares `_config['password'] == CRYPT()(password)[0]` (`:64`), which is non-constant-time through `LazyCrypt.__eq__`, and on success sets `session.hmac_key`. Other apps check admin rights with `gluon.fileutils.check_credentials` (`fileutils.py:510-537`), which **reads and writes admin's session file directly** through `storage.load_storage`/`save_storage` (`fileutils.py:440-465`, `storage.py:170-188`). That is an unrestricted `pickle.load`, and it rewrites the file as a plain `dict`.

### Cache

| Component | Behavior | Evidence |
|---|---|---|
| `Cache(request)` | `ram = CacheInRam`, `disk = CacheOnDisk`. On `web2py_runtime_gae` both are `MemcacheClient` | `cache.py:567-587` |
| `CacheInRam` | Class-level `meta_storage[app]` dict and **one process-global lock** for all apps. Stores references (no copy). `f()` runs **outside** the lock, so concurrent misses each compute the value. Optional psutil-based eviction | `cache.py:187-285` |
| `CacheInRam` stats | `hit_total` is incremented on every call, including misses | `cache.py:251`, `:264` |
| `CacheOnDisk.PersistentStorage` | **One pickle file per key** through `recfile` (hashed sub-folders) under `<app>/cache/`. Per-key thread lock plus a `portalocker.LOCK_EX` retry loop. On Windows, keys are base32-encoded | `cache.py:301-423` |
| `CacheOnDisk.__call__` | Holds the key lock **and the global stats-key lock** while `f()` runs, so computations for all keys in a process are serialized | `cache.py:449-504` |
| `cache.action(...)` | GET only. The key is `md5("__".join([path_info, response.view, session_id \| user-agent info, query_string, T.accepted_language]))` plus an optional prefix. It sets `Cache-Control`/`Expires` only for 1xx/2xx/3xx (or `valid_statuses`). A cached value is deleted when its status is not valid | `cache.py:589-742` |
| `@cache(key, time, model)` | `CacheAction`. The default key is `name:repr(args):repr(kwargs)`. A given key supports `%(name)s/%(args)s/%(vars)s` | `cache.py:530-552`, `:744-780` |
| `lazy_cache` | Uses `current.cache` at call time. The default key is `repr(f)` | `cache.py:794-813` |
| redis / memcache contrib | `RedisCache` pickles values (`contrib/redis_cache.py:183-213`). `contrib/memcache/__init__.py:12-13` does `import cPickle` / `import thread` and **cannot be imported on Python 3** | [Legacy] |

Notes on the cache:
- **[Suspected issue]** In `CacheInRam.__call__`, `destroyer(item[1])` runs while the global lock is held and without `try/finally` (`cache.py:245-252`). An exception in `destroyer` would leave the lock held, and every `cache.ram` call in the process would then block.
- **[Suspected issue]** `cache.action(session=True)` puts `response.session_id` in the key. With cookie sessions that value is the constant `True` (`globals.py:1294`), so all users would share one "per-session" cache entry.
- **[Suspected issue]** `lazy_cache` without a `key` uses `repr(f)`, which has no `%(args)s` placeholder, so **all argument combinations share one entry** (`cache.py:806`, `:541-547`). `repr(f)` also contains the memory address, so with `cache.disk` the key differs between processes. The docstring says the key is "generated from the function name".
- The `CacheAbstract` docstring still describes `.shelve`/gdbm files (`cache.py:100-111`). **[Legacy]** The implementation is not shelve-based.
- A `copyreg` reducer for `pydal.objects.Row` is registered at import time (`cache.py:59-63`).

## Execution flow

Per request (see doc 03 for the full pipeline):
1. `session.connect(request, response)` (`main.py:462`) loads the session and, for the file backend, locks it. Models may call `connect` again with `db`/`cookie_key`, and the first call's lock is released (`globals.py:1238`).
2. Models build `Auth(db, …)`. The constructor checks `session.auth` expiry and may call `renew`. `auth.define_tables()` defines the tables.
3. Controller decorators (`auth.requires_*`) run when the action is called.
4. On success: `_try_store_in_db` → DB commit → `_try_store_in_cookie_or_file` → `_fixup_before_save` → `cookies2headers` (`main.py:488-530`).
5. On error: no session store. The file is closed and unlocked in `finally` (`main.py:583-587`).

## Dependencies

`globals.Session` → `utils` (crypto, uuid, `safe_path_join`), `restricted` (SafeUnpickler), `recfile`, `pydal.contrib.portalocker`, `settings.global_settings`. `AuthAPI` → `pydal.objects`, `validators` (`CRYPT`, `IS_*`), `storage`, `globals.current`. `Auth` adds `html`, `sqlhtml.SQLFORM`, `Mail`, `contrib.login_methods.*`, `serializers`. `cache` → `recfile`, `portalocker`, `pydal.objects.Row`, optional `psutil`, and `contrib.gae_memcache`.

## Side effects

- Session files are created under `applications/<app>/sessions/` in hashed sub-folders. Cleanup is external (`scripts/sessions2trash.py`).
- A DB session table and the Auth tables are created, including `auth_cas` by default.
- `Auth.get_or_create_key` writes `private/auth.key`. Admin writes `private/hosts.deny` (`access.py:79-108`).
- `CacheOnDisk` creates `<app>/cache/`. `CacheInRam` memory grows without bound unless psutil and `max_ram_utilization` are configured.
- Process-wide state: `global_settings.db_sessions`, `CacheInRam.meta_storage`, and `copyreg` registrations.

## Compatibility constraints

- Pickle formats for sessions, cache values and impersonation must stay readable. Existing session files, DB rows and cookies (including the `secure_loads_deprecated` format) are in the wild. **[Compat]**
- Cookie names `session_id_<app>`/`session_data_<app>`, the DB table schema, the `record_id:unique_key` format, and file-name prefixes (client IP, used by `check_client`) are all persisted formats.
- The `safe_unpickle=False` default and `LazyCrypt`'s acceptance of legacy unsalted hashes both exist for old data.
- The Auth table and field names, `settings`/`messages` keys (locked `Settings`), `hmac_key` semantics, and the signature format (`simple_hash` sha1) must stay stable.
- `cache.ram(key, f, time_expire)` semantics, including `f=None` to delete and `time_expire=None` for no expiry.

## Related tests

| Module | Coverage |
|---|---|
| `test_globals.py` | Cookie flags for id and data cookies (`:540-629`), forget (`:631`), `check_client` for file and DB (`:848-931`) |
| `test_restricted.py` | `SafeUnpickler`; malicious session file with `safe_unpickle=True` (`:183`); legacy unpickle of custom classes (`:226`); `secure_loads` blocking an RCE payload (`:274`) |
| `test_utils.py:133-160` | `secure_dumps`/`secure_loads` round-trip at the bytes level, including deprecated and compression paths |
| `test_authapi.py` | 8 tests: login, logout, register, profile, change_password, verify_key |
| `test_tools.py` | `TestAuth` (`:1035`, incl. `test_login_bare` `:1318`, `test_impersonate` `:1441`), `TestAuthJWT` (`:428`), `TestAuthTokenLogin` (`:1834`), `TestAuthHostHeaderPoisoning` (`:1972`), `TestAuthTwoFactor` (`:2079`), `TestCASServiceAllowlist` (`:2859`) |
| `test_cache.py` | `CacheInRam`, `CacheOnDisk`, corrupt disk file, prefix, regex clear, DAL select cache |
| `test_redis.py` | Redis session and cache. **Skipped** in the baseline (no redis library) |
| `test_fileutils.py:168-212` | `get_session`/`set_session` for cross-app admin sessions |
| `test_web.py` | Real server register and login on welcome (file sessions, end to end) |

## Known gaps in test coverage

- No cookie-session **round-trip** test (store, then connect with the returned cookie).
- No test loads a legitimate session with `safe_unpickle=True`. No tests for `separate`, `renew` on file or DB sessions, DB-session concurrency, or `masterapp` sharing.
- `requires`, `requires_membership`, `requires_permission`, `requires_signature` and `login` are TODO (`test_tools.py:1379`, `:1553-1561`). No JWT `salt` test. No "remember me" or long-expiration test.
- `cache.action`, `Cache` and `lazy_cache` are TODO (`test_cache.py:117-121`). No concurrency test for `CacheInRam` or `CacheOnDisk`.
- `test_redis` never ran in the Windows baseline. The memcache contrib is not imported by any test.
- Wildcard `host_names` and `AppConfig`-style `map` values are not covered.

## Open questions

1. Are cookie sessions used anywhere in production on Python 3? The static reading says they would fail on the second request.
2. Should `safe_unpickle=True` automatically whitelist `gluon.globals.Session` and `gluon.storage.Storage`?
3. Is the process-wide `CacheInRam` lock a measurable bottleneck under Rocket's thread pool?
4. Is `auth_cas` always being created intentional? It follows from `cas_domains` defaulting to `[host]`.
5. Does any app rely on `renew()` dropping the `separate` sub-folder?

## Discrepancies with the technical reference

| Reference (`web2py_technical_reference-v2.md` §12, §17, §18) | Source |
|---|---|
| Session cookie is `session_id_<appname>` | It is `session_id_<masterapp>` in lower case. Cookie mode adds `session_data_<masterapp>` (`globals.py:1241-1242`) |
| File sessions lock the file | True. The exclusive lock covers the whole request (`globals.py:1318`, `main.py:583-587`) |
| Cookie sessions: `connect(..., cookie_key='secret')` works | The API exists, but the round-trip is suspected broken (bytes vs str, see above) |
| Cache: `cache.disk` (shelve implied by the code docstring) | One pickle file per key with portalocker (`cache.py:288-423`) |
| Auth tables: exactly 5 | 5, plus `auth_cas` (created by default) and `auth_token` (opt-in) |
| CSRF: every `form.process()` checks a one-time `_formkey` | True for `FORM`/`SQLFORM`. `AuthAPI` has none (`authapi.py:44`) |
| §18: sessions use pickle, so there is RCE risk | Correct. An opt-in `SafeUnpickler` exists (`restricted.py:47`) but is off by default and appears to reject web2py's own `Session` pickles |
| Reference omits | `AuthAPI`, `AuthJWT`, 2FA, `host_names`, `safe_unpickle`, `SameSite` defaults, `lazy_cache`, `cache.action` key rules |

## Modernization considerations

- First write characterization tests for the cookie-session round-trip, `safe_unpickle=True` with real session data, `renew` with `separate`, `lazy_cache` keys, and JWT `salt`.
- Decode `secure_dumps` output to `str` before storing it in the cookie, and accept `str` in `secure_loads`, keeping bytes compatibility.
- Add `Session`/`Storage` to the default safe whitelist, then consider making `safe_unpickle=True` the default after a migration period.
- Wrap `CacheInRam` critical sections in `with self.locker:`, and stop holding the stats lock during `f()` in `CacheOnDisk`.
- Remove the `*` entries from welcome's `host.names`, and have `AppConfig.get` return lists.
- Use `hmac.compare_digest` for 2FA codes and `LazyCrypt`. Raise PBKDF2 iterations for new hashes while still accepting old hashes.
