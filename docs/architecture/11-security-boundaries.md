# 11 — Security boundaries and controls

## Purpose

This document lists web2py's trust boundaries and the controls that enforce them, with evidence from source code. It describes weaknesses factually and gives no exploitation guidance. Nothing was executed to write it. Some claims depend on deployment (reverse proxy, session backend) and are marked accordingly.

Labels: **[Current]**, **[Compat]**, **[Legacy]**, **[Suspected issue]** (static reading, not proven), **[Unverified]**.

## Relevant source files

| Area | Files |
|---|---|
| Request parsing, client identity | `gluon/main.py`, `gluon/rewrite.py`, `gluon/globals.py` (`Request`) |
| Sessions, cookies, crypto | `gluon/globals.py` (`Session`), `gluon/utils.py`, `gluon/restricted.py` (`SafeUnpickler`), `gluon/storage.py` |
| CSRF, XSS, URL signing | `gluon/html.py`, `gluon/form.py`, `gluon/sqlhtml.py`, `gluon/authapi.py`, `gluon/packages/yatl/yatl/sanitizer.py`, `gluon/serializers.py` |
| Auth | `gluon/tools.py`, `gluon/authapi.py`, `gluon/packages/pydal/pydal/validators.py` (`CRYPT`, `LazyCrypt`) |
| Code execution | `gluon/restricted.py`, `gluon/compileapp.py`, `gluon/rewrite.py`, yatl `template.py`, `gluon/shell.py`, `gluon/utils.py:safe_eval_expression` |
| Files / archives | `gluon/admin.py`, `gluon/fileutils.py`, `gluon/utils.py:safe_path_join`, `gluon/recfile.py` |
| Admin / appadmin | `applications/admin/models/access.py`, `applications/admin/controllers/{default,webservices,debug}.py`, `applications/*/controllers/appadmin.py` (byte-identical) |
| Policy | `SECURITY.md`, `CHANGELOG.md` |

## Trust boundaries (overview)

| # | Boundary | Untrusted input | Main controls |
|---|---|---|---|
| B1 | HTTP client → `wsgibase` | Path, query, body, headers, cookies | URL regexes, static containment, `REGEX_SESSION_FILE`, IP validation |
| B2 | Reverse proxy → web2py | `X-Forwarded-For`, `X-Forwarded-Proto`, `Host` | **Trusted unconditionally** (see B2 below) |
| B3 | Session store → process | Pickled bytes (file/DB/cookie) | Signed/encrypted cookies. Optional `SafeUnpickler` |
| B4 | App data → HTML | Values written by views | `xmlescape` default, sanitizer, `SAFEJSON`, optional CSP |
| B5 | Browser → state-changing action | Cross-site requests | formkey, `URL` signatures, `SameSite=Lax` |
| B6 | Operator/admin → server | Code, files, archives | Password, channel check, path containment |
| B7 | Filesystem/DB → process | Tickets, routes, parameters, views | Ticket `SafeUnpickler`. Other files are trusted and `exec`'d |

## Main classes / functions

### B1 — Request input parsing

| Control | Evidence | Notes |
|---|---|---|
| Pattern-mode URL regex | `rewrite.py:53-55` `REGEX_URL` | a/c/f are `\w+`. Extension is `[\w.]+` |
| Pattern-mode args | `rewrite.py:56`, `:746-748` | Characters outside `[\w/.@=-]` become `_`. **`.` and `..` segments survive** in `request.args` **[Current]** |
| Parametric args | `rewrite.py:82` `args_match`, `validate_args` `:1214-1224` | A dot must follow a legal char, so `..` is rejected with HTTP 400 |
| Parametric static | `rewrite.py:81` `file_match`, `map_static` `:1120-1177` | Regex per path. Empty/`.`/`..` elements rejected when `file_match` has no `/` |
| Pattern-mode static containment | `rewrite.py:723-732` | `os.path.abspath` + `startswith(static_folder + os.sep)`. **`abspath`, not `realpath`**: symlinks inside `static/` are followed **[Current]** |
| Session id | `globals.py:1188` `REGEX_SESSION_FILE`, `:1302-1310` | Regex + `safe_path_join` (realpath) |
| Upload name | `globals.py:1017-1020` + pydal `REGEX_UPLOAD_PATTERN` (`helpers/regex.py:52-54`) | `table.field.uuid[.b16name].ext`, taken from the last arg |

### B2 — Client identity (proxy headers)

| Item | Evidence | Behaviour |
|---|---|---|
| `get_client` | `main.py:137-157` | The **first** regex match in `X-Forwarded-For` wins. Otherwise `REMOTE_ADDR`. Invalid IP → HTTP 400 (`:155-156`) |
| `request.is_local` | `main.py:376-378` | `remote_addr in local_hosts and client == remote_addr` |
| `request.is_https` | `main.py:381-383` | `wsgi_url_scheme`, **or `X-Forwarded-Proto` in (https, HTTPS)**, or `HTTPS=on` |
| Session file name | `globals.py:1244`, `:1334` | `"<client>-<uuid>"`, so the client IP (from XFF) is embedded in the file name |

- **[Current]** No trusted-proxy configuration exists. `request.client` is client-controlled whenever the deployment does not strip or overwrite `X-Forwarded-For`.
- **[Suspected issue]** Behind a same-host reverse proxy (`REMOTE_ADDR` = loopback) that *appends* to `X-Forwarded-For`, a client-supplied leading loopback address would make `client == remote_addr`. Then `is_local` becomes true (`main.py:376-378`). `is_local` gates welcome's generic views (`welcome/models/db.py:63-65`), the admin/appadmin channel check, and the `DISABLED` bypass (`main.py:412`). This depends on the deployment. **[Unverified]**
- **[Current]** `is_https` trusts `X-Forwarded-Proto` whether or not a proxy exists (already listed in the architecture report).

### B3 — Sessions

| Aspect | Evidence | Notes |
|---|---|---|
| Framework call | `main.py:461-462` | `session.connect(request, response)` uses defaults, so `safe_unpickle=False` |
| Opt-in restricted unpickle | `globals.py:1203-1204`, `:1278-1291`, `:1320-1327`, `:1393-1399` | `safe_load(s)` with `pickle_allowed_classes`. **Default is unrestricted `pickle.load(s)`** **[Compat]** |
| Cookie backend | `utils.py:220-283` | AES (`pad(key)[:32]`) + HMAC-SHA256 over the ciphertext, compared with `compare` (`:268`). One-colon payloads go to `secure_loads_deprecated` (HMAC-MD5, `:314-355`) **[Compat]** |
| File backend | `globals.py:1296-1343`, `:1707-1737` | `recfile` + `portalocker.LOCK_EX` held for the whole request (`:1318`, `:1726`) |
| DB backend | `globals.py:1348-1415` | `record_id:unique_key`. The key is checked by an SQL equality query (`:1377-1384`). Blob pickled data |
| Client binding | `globals.py:1199`, `:1313`, `:1386-1388` | `check_client=False` by default |
| Change detection | `globals.py:1438-1439`, `:1640-1650` | md5 of the pickled session |
| Cookie flags | `globals.py:1503-1517` | `HttpOnly` unless `httponly_cookies` is false. `SameSite=Lax` by default. **`secure` only after `session.secure()`** (`:1609-1610`), which `request.requires_https()` calls (`globals.py:595-602`) |
| `renew` | `globals.py:1444-1499` | New file name or new DB `unique_key` |

The cookie-session round trip (bytes into `SimpleCookie`, then `str.count(b":")`) is suspected broken (architecture report §9.2). It is not re-verified here beyond reading `globals.py:1619-1636` and `utils.py:238-248`.

### B4 — XSS controls

| Control | Evidence |
|---|---|
| Default escaping `{{=x}}` → `Response.write(escape=True)` → `xmlescape` | yatl `template.py:654`, `globals.py:739-743`, `html.py:135-153` |
| Bypass of escaping by design: `XML`, `SafeString` (`URL()`, `SAFEJSON`), any `.xml()`, `SCRIPT`/`STYLE` content | `html.py:628-751`, `:181-185`, `:1528-1576` |
| `XML(sanitize=True)` → yatl `XssCleaner` (tag/attr allowlist, schemes http/https/ftp/mailto, `quoteattr`) | `html.py:693`, `sanitizer.py:76-241` |
| `SAFEJSON`, `ASSIGNJS`, `generic.json` → `JSONEncoderForHTML` | `html.py:156-165`, `:2975-2995`, `serializers.py:149-184` |
| CSP (opt-in): nonce, `default-src 'self'`, `base-uri`, `form-action`, `object-src 'none'`, directive validation | `globals.py:135-139`, `:679-737`. Nonce on `SCRIPT`/`STYLE` (`html.py:1519-1526`, `:1551-1558`) and `include_files` (`globals.py:888-905`) |
| Admin CSP report-only | `admin/models/access.py:219-222` |

### B5 — CSRF and URL signing

| Mechanism | Evidence | Properties |
|---|---|---|
| `FORM`/`SQLFORM` `_formkey` | `html.py:2193-2201`, `:2237-2244` | One-time. Last 10 kept. `compare`. **Skipped when `session=None`** |
| `gluon/form.py:Form` | `form.py:172-184`, `:214-221` | Per-form key, **reusable**. `hmac.compare_digest`. `csrf=False` option |
| `AuthAPI` | `authapi.py:44` | "No builtin CSRF protection whatsoever" |
| `URL(hmac_key / user_signature)` | `html.py:394-420` | HMAC-SHA1 (`simple_hash` → `hmac.new(key+salt, ...)`, pydal `validators.py:4423-4425`) over `/a/c/f.ext/args?sorted(vars)` |
| Per-login key | `authapi.py:944-949` | `session.auth.hmac_key = web2py_uuid()` |
| `verifyURL` | `html.py:454-577` | Missing `_signature` → False. Constant-time `compare` (`:577`) |
| Grid | `sqlhtml.py:2800-2812` | Only the path is signed (`hash_vars=False`). `view` is allowed for anonymous users |
| Admin | `admin/controllers/default.py:66-67`, `:1103`, `:1355`, `:1562`, `:579` | Mix of `session.token` (compared with `==`, only when `request.vars` is non-empty), `URL.verify(hmac_key=session.hmac_key)`, and `FORM.confirm` |

### Password hashing and comparisons

| Item | Evidence |
|---|---|
| `CRYPT` default `pbkdf2(1000,20,sha512)`, salted | pydal `validators.py:4626` |
| `LazyCrypt.__eq__` final `temp_pass == stored_password` (not constant-time). The algorithm is taken from the stored hash, and unsalted legacy hashes are recognised by length | `validators.py:4504-4536` **[Compat]** |
| Admin password in `parameters_<port>.py` as a `CRYPT` hash. `<random>` = 8 chars from `secrets` | `main.py:603-634` |

Constant-time comparisons (`hmac.compare_digest` directly or through `utils.compare`, `utils.py:85-95`): `FORM` formkey (`html.py:2198`), `verifyURL` (`html.py:577`), `secure_loads` (`utils.py:268`), `secure_loads_deprecated` (`:335`), `Form` (`form.py:183`), JWT signature (`tools.py:1399`).

Plain `==` comparisons: admin `verify_password` (`access.py:64`), `LazyCrypt` (`validators.py:4536`), admin `session.token` (`default.py:1103,1355,1562`), 2FA code (`tools.py:3372-3374`).

### B6/B7 — Code-execution surfaces (by design unless noted)

| Surface | Evidence | Input trust |
|---|---|---|
| `restricted()` = plain `exec`, **not a sandbox** | `restricted.py:304-330` | App code |
| Routes files `exec` | `rewrite.py:377-379` | Operator files |
| Template include/extend `eval`, render `exec` | yatl `template.py:455`, `:982`. `compileapp.py:797` | View files (plus view context) |
| Admin `parameters_<port>.py` executed via `restricted` | `admin/models/access.py:34-35` | Operator file |
| Shell / `-R` / `-K` code strings | `shell.py:41`, `:301-317`, `:332-334`. `widget.py:609-618` | Operator |
| appadmin query/orderby → `safe_eval_expression` (AST allowlist, no calls except DAL query methods and `_select`, `__builtins__=None`) | `utils.py:579-715`. `appadmin.py:107-111`, `:225` | Authenticated admin |
| appadmin `eval_in_global_env` (`exec("_ret=%s")`) only with `request.args[0] in databases` | `appadmin.py:86-96` | Name from an allowlist |
| `SQLFORM.smartdictform` `eval(open(filename).read(), {"__builtins__": {}})` | `sqlhtml.py:2286-2288` | App-chosen file. An empty-builtins `eval` is not a sandbox |
| Admin `debug.execute` / `debug.callback` → debugger | `admin/controllers/debug.py:28-35`, `:116-127` | Authenticated admin. No per-request token |
| Admin `webservices` `write_file`, `install`, `attach_debugger` | `webservices.py:50-101` | Basic auth with the admin password |
| Scheduler: any model-level callable invocable through the `scheduler_task` row | `scheduler.py:526-536` | DB writers |

### Tickets

- Store: `pickle.dump(s)` to `errors/` or the DB (`restricted.py:137-167`). Load: `safe_load(s)` with `TICKET_ALLOWED_CLASSES = {"gluon.html": {"XML", "XML_unpickle"}}` (`:184-211`). **[Current]**
- The snapshot includes frame locals (`restricted.py:409`) and `BEAUTIFY` of `request`, `response`, `session` (`:413-414`). Tickets can therefore hold cookies, headers, session contents and credentials present in locals. File tickets are written before rollback (`main.py:542-544`).

### Admin application

| Control | Evidence | Notes |
|---|---|---|
| Channel check | `access.py:23-29` | https **or** `trusted_lan_prefix` match on **`request.client`** **or** `is_local`. Otherwise "insecure channel". (appadmin uses `remote_addr` instead, `appadmin.py:24-28`.) `request.env.trusted_lan_prefix` comes from `global_settings` (copied into `request.env` by `Request.__init__`, `globals.py:317`; commented example at `settings.py:51`) or from the server environ |
| Password file | `access.py:31-50` | Missing → admin disabled |
| `verify_password` | `access.py:53-67` | PAM option. Sets `session.hmac_key` on success |
| Brute-force | `access.py:74-129`, `default.py:153-183` | `private/hosts.deny` keyed on **`request.client`**. 5 attempts / 3600 s. `sleep(2**n)` |
| Session expiry | `access.py:136-143`, `models/0.py:1` | 60 min inactivity |
| Webservices | `access.py:164-171` | Basic auth. `verify_password` without `hosts.deny`. 10 s sleep on failure. Always 403 in `MULTI_USER_MODE` |
| `attach_debugger` default `authkey='secret password'` | `webservices.py:82` | Also uses `unicode` (`:87`), which raises `NameError` on Python 3 **[Legacy]** |
| File access | `admin.py:84-114` (`safe_path`, `check_app_path`, `join_app_path`) | **`abspath`/`normpath`, not `realpath`**. `safe_path` allows anything under `applications/` or `deposit/` |
| App install / upload | `admin.py:266-309` → `w2p_unpack` → `fileutils._extractall` | Rejects absolute, traversal, device/FIFO and escaping links (`fileutils.py:220-255`) |
| Zip / upgrade | `admin.py:429-458` (`_safe_extract_path`), `:461-510` | Upgrade uses **plain `http://web2py.com`** with no signature check, and an unimported `urlopen` (`:504`), so it fails **[Legacy]** |
| Git / URL install | `default.py:287-305` | `git.Repo.clone_from` / `urllib.request.urlopen(url)` with an admin-supplied URL |
| Open redirect | `default.py:146` | `prevent_open_redirect(send)` (`tools.py:135+`) |

### appadmin access (`applications/*/controllers/appadmin.py:22-50`)

1. https → secure cookie. Else `trusted_lan_prefix` on `REMOTE_ADDR`. Else it requires `is_local` or `is_shell`, **except for `manage`** (`:22-28`).
2. `manage` requires `check_credentials` or membership in the manager role (`:30-43`).
3. Other functions require the admin session (`check_credentials`, `fileutils.py:510-537`). That function reads the admin session file with an **unrestricted `pickle.load`** (`storage.load_storage`, `storage.py:170-178`), limits it to 1 h, and checks multi-user ownership (`fileutils.py:475-507`).

### Path containment helpers

| Helper | Evidence | Resolution |
|---|---|---|
| `utils.safe_path_join` | `utils.py:566-576` | `realpath` (symlink-aware) |
| `fileutils._extractall` | `fileutils.py:220-255` | Members through `safe_path_join`. Link targets through `abspath` |
| `admin.safe_path`, `check_app_path`, `join_app_path`, `is_within_root` | `admin.py:84-114` | `abspath` |
| `admin._safe_extract_path`, `safe_deposit_path` | `admin.py:41-54` | `safe_path_join` / basename check |
| Pattern-mode static | `rewrite.py:723-732` | `abspath` |

### Host allowlist

`Auth.url(scheme=True)` refuses to use the `Host` header unless `settings.host` or `host_names` is set (`tools.py:1839-1872`). `select_host` does a glob match (`:1880-1898`). `Auth.__init__` pins `settings.host` to the validated request host whenever `host_names` is given (`:1959`, `:2018`). Welcome sets `host.names = localhost:*, 127.0.0.1:*, *:*, *` (`private/appconfig.ini:13`, `models/db.py:95`). `*` matches any Host, so in welcome the allowlist does not restrict the host. **[Current]**

### Upload / download

`Response.download` (`globals.py:994-1041`) forgets the session, matches `REGEX_UPLOAD_PATTERN`, and calls `field.retrieve`. Authorization happens only when the field has `authorize=` (pydal `objects.py:2544-2549`). The default is None, so any upload is served to anyone who knows its name (the name contains a random uuid). It sends `Content-Disposition: attachment` by default.

## Execution flow

Per request: B1 parsing (`rewrite.url_in`) → static serve (no session) → client identity (B2, `main.py:367-384`) → `session.connect` (B3) → models/controller/view under `restricted` (B6/B7) → B4 escaping at render → commit → session store with cookie flags (`main.py:529`, `globals.py:1519-1532`) → ticket on error (B7).

## Dependencies

pydal (`CRYPT`, `simple_hash`, `Field.retrieve`, `validate_and_insert`), yatl (sanitizer, template), `pydal.contrib.portalocker`, AES via `gluon/contrib/pyaes` or PyCryptodome (`utils.py:53-83`), stdlib `hmac`, `pickle`, `secrets`.

## Side effects

Admin writes `private/hosts.deny` and session files. Successful admin login writes `session.hmac_key`. Tickets persist request/session data to disk or DB. `upgrade`/`app_install` write under `deposit/` and `applications/`.

## Compatibility constraints

- **[Compat]** Unrestricted pickle sessions by default. `secure_loads_deprecated` (HMAC-MD5). `LazyCrypt` unsalted hashes. PBKDF2 1000 iterations as the default for new hashes.
- **[Compat]** `SameSite=Lax` default and the `session.samesite(False)` opt-out. `secure` is opt-in.
- **[Compat]** `request.client`/`is_local`/`is_https` semantics are used by apps for authorization decisions.
- **[Compat]** Admin `parameters_<port>.py` format (`password="<hash>"`) and `pam_user:` prefix.

## Related tests

| Test | Covers |
|---|---|
| `test_appadmin.py:697-800` | `safe_eval_expression` blocking (calls, subscript, dunder, lambda, comprehensions, f-strings, walrus, ternary). `:198` host-header spoofing. `:466` path validation. `:657` multi-user ownership |
| `test_fileutils.py:51-170` | untar: traversal, absolute, escaping symlink/hardlink, special files (symlink cases skipped on Windows baseline) |
| `test_compileapp.py:40-78`, `:155`, `:182-215` | plugin filename traversal, admin test runner without `eval`, admin unzip traversal |
| `test_tools.py:2020-2060` | `Auth.url` host allowlist. `:2811` open redirect. `:2906-3020` CAS service allowlist. `:2312-2400` CSV formula neutralization |
| `test_form.py:28-110` | `Form` CSRF |
| `test_html.py:1187-1315` | MARKMIN XSS. `:267` `XML` sanitize. `:357` `XML` pickle as text. `:446` CSP nonce |
| `test_restricted.py:15-140`, `:226`, `:373` | `SafeUnpickler`, ticket allowlist, legacy session unpickle |
| `test_globals.py:257`, `:317-470`, `:690` | `include_files` escaping, CSP validation, attachment filenames |
| `test_utils.py:191` | `secure_loads_deprecated` opt-in |
| `test_routes.py:529`, `test_router.py:1881` | Static sibling-prefix traversal, parametric static path |
| `test_webservices.py:45-70`, `test_recfile.py:76-200` | `safe_apath` escapes. recfile confinement |

## Known gaps in test coverage

- No test of `get_client`/`is_local`/`is_https` with proxy headers. No test for pattern-mode `..` args.
- No cookie-session round trip. No test for default (unrestricted) unpickle of file/DB sessions beyond `test_restricted.py:226`.
- No admin controller tests for `access.py` (channel check, `hosts.deny`, webservices Basic auth), `debug`, or `upgrade`.
- No test for `FORM.accepts(session=None)` or the grid `user_signature` exceptions.
- No test for `check_credentials` reading a crafted admin session file.

## Open questions

1. Is it intended that `trusted_lan_prefix` is matched against different client identities (admin: `request.client`, derived from `X-Forwarded-For`; appadmin: `remote_addr`)? The value itself is read from `global_settings` via `request.env` (`globals.py:317`).
2. Is `debug.execute`/`callback` meant to rely only on the admin session and `SameSite=Lax`? Lax cookies are sent on top-level GET navigations, and `request.vars` includes GET vars. **[Unverified]** impact, because a debugger session must be active.
3. Is following symlinks under `static/` and in admin paths (`abspath` checks) intended?

## Discrepancies with the technical reference

| Reference (§17 and elsewhere) | Source |
|---|---|
| "`URL()` and request parsing reject `../` in args and vars" | Parametric mode rejects `..` in args. Pattern mode keeps `.`/`..` segments (`rewrite.py:56`, `:746-748`). Vars are not validated |
| "CSRF: every `form.process()` validates a one-time token" | Not for `gluon/form.py:Form` (reusable), `AuthAPI` (none), or `FORM.accepts(session=None)` |
| "Tracebacks never disclosed" | True for users. But tickets store locals and request/session dumps (`restricted.py:409-414`), and admin shows them |
| §18 "Pickle risk if cookie or DB compromised" | Accurate. `safe_unpickle` exists but is opt-in, and admin `check_credentials` always uses `pickle.load` |
| Omitted: CSP, `safe_unpickle`, `SAFEJSON`, `Auth` host allowlist, formula neutralization | Present (see `CHANGELOG.md:1-49`) |

`SECURITY.md` only states the reporting channel (email) and a 72-hour response target. It lists no concrete supported version numbers.

## Findings from static reading

- **[Suspected issue]** Admin brute-force lockout is keyed on `request.client` (`access.py:113-128`), which comes from `X-Forwarded-For` (`main.py:145`). Without a proxy that overwrites XFF, the counter is per claimed address rather than per peer. The webservices path does not use the counter (`access.py:164-171`).
- **[Suspected issue]** `AppConfig.get` returns a one-shot `map` iterator for comma lists (`contrib/appconfig.py:73-74`). Welcome passes it as `host_names`, and `Auth` stores it (`tools.py:2019`). `select_host` indexes `host_names[0]` when there is no `Host` header (`tools.py:1893-1894`), which fails on a `map`, and a second iteration sees an exhausted iterator.
- **[Suspected issue]** `TAG_unpickler` performs a nested unrestricted `pickle.loads` (`html.py:1349-1350`). Adding it to any `SafeUnpickler` allowlist defeats the restriction.
- **[Current]** `request.env.trusted_lan_prefix` is compared with `request.client` in admin (`access.py:25-26`) but with `remote_addr` in appadmin (`appadmin.py:24-28`). When `global_settings.trusted_lan_prefix` is set (it reaches `request.env` through `globals.py:317`), the admin prefix match is therefore XFF-controlled.

## Modernization considerations (optional)

- Before any change: characterization tests for proxy-header handling, cookie sessions, `check_credentials`, and admin `access.py`.
- Candidates behind opt-in flags: a trusted-proxy list, `safe_unpickle=True` by default, constant-time admin comparisons, a higher PBKDF2 iteration count for new hashes, and `realpath`-based containment in `admin.py`.
