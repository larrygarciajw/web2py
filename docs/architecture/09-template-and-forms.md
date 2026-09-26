# 09 — Templates, HTML helpers and forms

## Purpose

This document describes how web2py renders views and builds and processes HTML forms. It covers the yatl template engine as web2py uses it, the `gluon/html.py` helpers (escaping, `URL` signing, pickling), and the three form layers: `html.FORM`, `gluon/form.py:Form` and `gluon/sqlhtml.py:SQLFORM` with its grid.

Status labels: **[Current]** is behaviour of the present code. **[Compat]** is kept for old apps. **[Legacy]** is obsolete. **[Suspected issue]** is a likely defect found by static reading and not proven by a test. **[Unverified]** means the claim could not be confirmed. Nothing was executed to write this document.

## Relevant source files

| File | Role |
|---|---|
| `gluon/template.py` | 1-line shim: `from yatl.template import parse_template, render` |
| `gluon/packages/yatl/yatl/template.py` | Template engine (submodule, 1029 lines) |
| `gluon/packages/yatl/yatl/sanitizer.py` | `XssCleaner` / `sanitize` used by `XML(sanitize=True)` |
| `gluon/sanitizer.py` | 1-line shim: `from yatl.sanitizer import sanitize` |
| `gluon/compileapp.py` | `run_view_in`, `compile_views`, `read_pyc`, `save_pyc` |
| `gluon/globals.py` | `Response.write`, `Response.render`, `delimiters`, `generic_patterns`, CSP nonce |
| `gluon/restricted.py` | `compile2`, `restricted` (plain `exec`) |
| `gluon/html.py` | Helpers, `xmlescape`, `URL`, `verifyURL`, `FORM`, `BEAUTIFY`, `MENU`, `ASSIGNJS`, `SAFEJSON` (3001 lines; its own implementation, not yatl's `helpers.py`) |
| `gluon/form.py` | Newer, minimal `Form` class (259 lines) |
| `gluon/sqlhtml.py` | `SQLFORM`, widgets, formstyles, `grid`, `smartgrid`, `SQLTABLE`, exporters (4521 lines) |
| `gluon/validators.py` | 9-line re-export of `pydal.validators` |
| `gluon/utils.py` | `compare`, `csv_safe`, `csv_safe_text`, `md5_hash` |
| `applications/welcome/views/generic.*` | Fallback views (html, json, xml, csv, load, rss, ics, map, pdf, jsonp) |

## Main classes / functions

### Template engine (yatl)

| Symbol | Evidence | Notes |
|---|---|---|
| `DEFAULT_DELIMITERS = ("{{", "}}")` | `yatl/template.py:29` | Overridden by `response.delimiters` (`globals.py:674`, default `("{{","}}")`) in `parse_template` (`template.py:816-820`) and `render` (`:931-935`) |
| `file_reader` | `template.py:32-38` | Converts `OSError` into `RestrictedError(filename, "", "Unable to find the file")` |
| `Node`, `SuperNode`, `BlockNode`, `Content` | `template.py:54-244` | Parse tree. `Content.blocks` maps block names to nodes. `output_aux` substitutes overriding blocks (`:83-97`) |
| `TemplateParser` | `template.py:247-784` | Splits the text on `r_tag` (`:316`), builds nodes, handles `extend`/`include`/`block`/`end`/`super`, then `reindent` |
| `TemplateParser.reindent` | `template.py:353-429` | Converts flat code into indented Python (details below) |
| `TemplateParser._get_file_text` | `template.py:437-472` | **`eval(filename, context)`** (`:455`) of the include/extend argument |
| `parse_template` | `template.py:790-831` | Used by web2py. Returns generated Python source (`str`) |
| `render` | `template.py:864-988` | Standalone render. **`exec(code, context)`** (`:982`). Uses `gluon.globals.Response` when importable (`:938-942`) |
| `DummyResponse`, `NOESCAPE` | `template.py:834-857` | Only used when gluon is not importable. `NOESCAPE` is injected into the context only in that case (`:945-946`) |
| `template` decorator | `template.py:991-1029` | Standalone decorator, not used by gluon |

### Helpers (`gluon/html.py`)

| Symbol | Evidence | Notes |
|---|---|---|
| `xmlescape(data, quote=True)` | `html.py:135-153` | Calls `data.xml()` if available, otherwise `html.escape(str(data), quote)` via `local_html_escape` (`:36-50`) |
| `SAFEJSON` | `html.py:156-165` | `SafeString(serializers.json(obj))`. JSON encoder `JSONEncoderForHTML` escapes `& < >`, U+2028 and U+2029 (`serializers.py:149-181`) |
| `SafeString` | `html.py:181-185` | `str` subclass whose `.xml()` returns itself, so it is not escaped. `URL()` returns one (`:450`) |
| `URL` | `html.py:188-450` | Builds URLs, handles `static_version` (`:348-355`), HMAC signing (`:394-420`), a CRLF check (`:435-436`), then `rewrite.url_out` (`:438`) |
| `verifyURL` / `URL.verify` | `html.py:454-580` | Recomputes the HMAC and compares with `compare` (`:577`) |
| `XmlComponent` | `html.py:585-625` | Abstract root |
| `XML` | `html.py:628-751` | Unescaped text. `sanitize=False` by default (`:641`). Sanitizes via yatl `sanitize` (`:693`) |
| `XML_pickle` / `XML_unpickle` | `html.py:754-762` | `copyreg` registration. Pickles plain text |
| `DIV._xml` / `DIV.xml` | `html.py:1000-1057` | Attribute **values** are escaped (`:1034`). Components are escaped with `xmlescape` (`:1037`). Attribute **names** are not escaped |
| `TAG_pickler` / `TAG_unpickler` | `html.py:1349-1366` | Nested `pickle.dumps` / **`pickle.loads`** of a `DIV` copy |
| `SCRIPT`, `STYLE` | `html.py:1515-1576` | Contents **not escaped** (`:1530-1537`). Adds the CSP nonce when `response._csp_enabled` (`:1521-1525`) |
| `BEAUTIFY` | `html.py:2526-2610` | Recursively renders dict/list into tables. Skips `_`-prefixed keys and lambdas. Recursion capped by `level` (default 6) |
| `MENU` | `html.py:2613-2727` | Nested `UL`/`LI`/`A`, or a mobile `SELECT` with an inline `onchange` |
| `ASSIGNJS` | `html.py:2975-2995` | `var k = <json>;` for each kwarg, returned as `XML`. Key names are not validated |

### Forms

| Symbol | Evidence | Notes |
|---|---|---|
| `FORM.accepts` | `html.py:2165-2248` | CSRF formkey check, validation traversal, rotation of the key |
| `FORM.validate` / `FORM.process` | `html.py:2279-2372`, `:2374-2408` | `validate` defaults to `dbio=False` (`:2315`). `process` defaults to `dbio=True` (`:2404`) |
| `FORM.confirm` | `html.py:2431-2446` | Builds a form and calls `.process()` |
| `gluon/form.py:Form` | `form.py:98-259` | Reusable per-form CSRF key stored in `session._formkeys` |
| `FormStyleDefault` | `form.py:18-90` | Table formstyle for `Form` |
| `SQLFORM` | `sqlhtml.py:1401` | `widgets` (`:1457`), `formstyles` (`:1479-1490`), `__init__` (`:1518`, ~356 lines), `createform` (`:1874`), `accepts` (`:1909`, ~363 lines) |
| `SQLFORM.dictform` / `smartdictform` | `sqlhtml.py:2272-2296` | `smartdictform` **`eval`s a file** with `{"__builtins__": {}}` (`:2286-2288`) |
| `SQLFORM.factory` | `sqlhtml.py:2298-2327` | Clones the fields into a `DAL(None)` table named `no_table` |
| `SQLFORM.grid` | `sqlhtml.py:2593-3730` | Single static method of about 1137 lines |
| `SQLFORM.smartgrid` | `sqlhtml.py:3731-4028` | About 297 lines. Wraps `grid` |
| `ExportClass` and `Exporter*` | `sqlhtml.py:4343-4521` | CSV/TSV exporters pass their output through `csv_safe_text` |
| Formstyle functions | `sqlhtml.py:1082-1400` | `table3cols`, `table2cols`, `divs`, `inline`, `ul`, `bootstrap`, `bootstrap3_*`, `bootstrap4_*` |

## Execution flow

### 1. View selection and rendering (`compileapp.run_view_in`, `compileapp.py:734-799`)

1. `serve_controller` sets `response.view = "c/f.ext"` (`main.py:180-184`), copies the environment after the models run (`:192`), and renders only when the controller returns a `dict` (`:194-197`).
2. `generic_patterns` are translated with `fnmatch.translate` and matched with **`regex.search`** against `"c/f.ext"` (`compileapp.py:747-755`).
3. A non-string `response.view` (a stream) is parsed directly, with layer `"file stream"` (`:756-758`).
4. If `compiled/` exists, the code looks for `views.<c>.<f>.<ext>.pyc`, then `views.generic.<ext>.pyc`, then the legacy `views.<c>.<f>.pyc` / `views.generic.pyc` for html (`:761-781`). Code loads through `getcfs(...read_pyc)` (`:778`).
5. Otherwise it falls back to `generic.<ext>` when allowed (`:783-785`), raises HTTP 404 when the file is missing (`:786-791`), and runs `parse_template(...)` → `compile2` (`:793-795`). **[Current]** Non-compiled views are re-parsed and re-compiled on every request, with no cache.
6. `restricted(ccode, environment, layer, scode)` `exec`s the generated code (`:797`, `restricted.py:304+`). The page is `response.body.getvalue()` (`:799`).

`Response.render(view, vars)` (`globals.py:745-772`) re-enters `run_view_in` with a temporary body and view.

### 2. Template parsing (`TemplateParser.parse`, `template.py:561-784`)

- Text outside tags becomes `\n{writer}({text!r}, escape=False)` (`:757`). Here `writer` is `"response.write"` (`:281`).
- `{{=expr}}` becomes `\n{writer}(expr)`, which uses the default `escape=True` (`:651-655`).
- Multi-line code blocks: a line that starts with `=` inside a code tag is also converted to a writer call, and a trailing `\` continues it (`:737-752`).
- `{{block name}}` … `{{end}}` pushes and pops a `BlockNode` (`:657-681`). `{{super}}` / `{{super name}}` creates a `SuperNode` that a child template fills (`:683-699`, `:763-780`).
- `{{include "f"}}` parses the file inline (`:474-490`). A bare `{{include}}` marks where child content goes (`:708-714`).
- `{{extend "f"}}` is deferred to the end of parsing (`:716-720`, `:782-784`). Nodes seen before the `extend` (`pre_extend`) stay first. Child blocks that the parent defines replace the parent's blocks. Everything else goes into the parent's `{{include}}` slot (`:492-559`).
- Include/extend filenames are **Python expressions evaluated with `eval`** in the view context, with `response` added from `current` (`:449-455`). An empty result skips the include/extend (`:458-459`, `:498`).
- Custom `lexers` receive `(parser, value, top, stack)` (`:640-649`).

### 3. Re-indentation rules (`reindent`, `template.py:353-429`)

| Rule | Regex / condition | Effect |
|---|---|---|
| Line ends with `:` (not a comment) | `:417` | Indent the next line |
| `pass` | `re_pass` `:273` | Dedent after this line |
| `return/continue/break/raise` | `re_unblock` `:271` | Dedent and set a one-line "credit" |
| `elif/else:/except/finally:` | `re_block` `:268` | Put this line one level back |
| Final `k > 0` / `k < 0` | `:424-427` | `RestrictedError` "missing/too many pass" |

**[Current]** Every block that ends with `:` (including `def`, `with`, `class`) must be closed with `pass`. `match`/`case` are not in `re_block`.

### 4. Escaping chain

`{{=x}}` → `Response.write(x, escape=True)` (`globals.py:739-743`) → `xmlescape(x)` (`html.py:135`). This returns `x.xml()` unchanged for helpers, `XML`, `SafeString` (so also `URL()` and `SAFEJSON`) and `lazyT` (`languages.py:422-423`, which escapes unless it is markmin). Other values go through `html.escape(str(x), quote=True)`. Helpers escape their own children (`html.py:1037`), except `SCRIPT`/`STYLE` (`:1530-1537`) and `XML`. **[Current]**

### 5. FORM CSRF (`FORM.accepts`, `html.py:2165-2248`)

1. With a `session`, the key name is `_formkey[<formname>]` (`:2195`). The submitted `_formkey` must match one of the stored keys, compared with `compare` (constant-time) (`:2198`). The matched key is removed, so it is one-time (`:2201`).
2. `_formname` must equal `formname` (`:2202`).
3. When `record_hash` is set (by `SQLFORM.accepts` with `detect_record_change=True`, an md5 of the record, `sqlhtml.py:1949-1953`), the formkey prefix must equal the hash (`html.py:2205-2210`).
4. After validation, a new key (`record_hash:uuid` or `uuid`) is appended and only the **last 10** keys are kept (`:2237-2244`). This happens on success and on failure.
5. With `session=None`, the CSRF check is skipped entirely. **[Current]**

### 6. `gluon/form.py:Form`

It validates in `__init__` on any non-GET request (`form.py:166-213`). The key is created once per `formname` and **reused** across submissions (`:215-221`). The comparison uses `hmac.compare_digest`, and an explicit `None` check prevents an empty/None bypass (`:176-184`).

### 7. SQLFORM specifics

- The formname defaults to `"%(tablename)s/%(record_id)s"` (`sqlhtml.py:1913`, `:1982-1985`). A submitted `id` that differs from the record raises `SyntaxError("user is tampering...")` (`:2077-2082`).
- Deletion needs `self.deleted` (from `delete_this_record`) **and** `self.custom.deletable`, which is set only when `record and deletable` (`:2020`, `:2087`, `:1811-1812`).
- A string `formstyle` is resolved through `SQLFORM.formstyles` (`:1877-1878`). The default is `response.formstyle = "table3cols"` (`globals.py:675`). Welcome sets `"bootstrap4_inline"` (`welcome/models/db.py:70`).
- Grid access with `user_signature=True`: create/edit/delete are enabled only for logged-in users (`sqlhtml.py:2701-2705`, `wenabled` at `:2702`). A request is allowed when (a) the args equal the base args, (b) `URL.verify(..., user_signature=True, hash_vars=False)` passes, or (c) the action is `view` **and the user is not logged in** (`:2800-2812`). Vars are never signed (`hash_vars=False`, `:2785`, `:2794`).
- Exports: `_export_type` selects from `exportManager` (`:3097-3140`). CSV/TSV output is neutralized by `csv_safe_text` (`sqlhtml.py:4422,4439,4457,4473`; `utils.py:107-156`, prefixes `= + - @ \t \r`, numeric literals kept). HTML/XML/JSON exporters are not affected.
- Validators: all field `requires` objects come from `pydal.validators` through `gluon/validators.py`. `SQLFORM.factory` applies `default_validators` (`sqlhtml.py:2321-2324`).

### 8. Welcome generic views

| View | Behaviour | Evidence |
|---|---|---|
| `generic.html` | `extend 'layout.html'` + `BEAUTIFY(response._vars)` | `generic.html:1,10,12` |
| `generic.json` | `XML(serializers.json(response._vars))` (HTML-safe JSON) | `generic.json:1` |
| `generic.xml` | `XML(serializers.xml(..., quote=False))`. `< > &` are still escaped by `xml_rec` | `generic.xml:1`, `serializers.py:124-146` |
| `generic.load` | Single value written with escaping, otherwise `BEAUTIFY` | `generic.load:30` |
| `generic.csv` | `response.write(str(content), escape=False)`, **no formula neutralization** | `generic.csv:16` |
| `generic.jsonp` | Refuses with 501 when used as a generic view | `generic.jsonp:10` |
| `generic.pdf` | `response.render(...)` or `BEAUTIFY` → `pdf_from_html` | `generic.pdf:1-11` |

The framework default is `generic_patterns = ["*"]` (`globals.py:673`). Welcome resets it to `[]` and allows `"*"` only when `request.is_local and not production` (`welcome/models/db.py:63-65`).

## Dependencies

- yatl submodule: `template.py` imports `gluon.globals.current` and `gluon.restricted.RestrictedError` when available (`template.py:41-51`).
- `html.py` imports `yatl.sanitizer`, `gluon.utils.compare/web2py_uuid`, `gluon.validators.simple_hash` (pydal), and lazily `gluon.rewrite.url_out` and `gluon.globals.current` (`html.py:27-33`, `:295`).
- `sqlhtml.py` depends on pydal (`Field`, `Table`, `Rows`, `default_validators`, `smart_query`), `gluon.html`, `gluon.serializers`, `gluon.utils` (`sqlhtml.py:17-80`).
- `form.py` first tries web3py-style imports (`gluon.current`, `gluon.helpers`, `gluon.url`) and falls back through a bare `except` (`form.py:7-15`). **[Legacy]**

## Side effects

- `render()` and `run_view_in` execute arbitrary Python from view files. **[Current]**
- `_get_file_text` may add `response` to the caller's context dict (`template.py:450-451`).
- `FORM.accepts` / `SQLFORM.accepts` / `Form.__init__` write to `session` (formkeys). `SQLFORM.accepts` and `Form` write to the DB when `dbio=True`.
- `compile_views` writes `compiled/views.*.pyc` and deletes the temporary `.py` (`compileapp.py:521-525`).
- `verifyURL` pops `_signature` from `request.get_vars` and restores it only on the normal return path (`html.py:517`, `:572`).
- `SQLFORM.smartdictform` writes `repr(session[name])` to a file (`sqlhtml.py:2295`).

## Compatibility constraints

- **[Compat]** `gluon.template` exports only `parse_template` and `render`. `TemplateParser` must be imported from `yatl.template`.
- **[Compat]** Compiled-view names `views.<path>.pyc` and the legacy `views.<c>.<f>.pyc` / `views.generic.pyc` lookups (`compileapp.py:769-773`).
- **[Compat]** `copyreg` pickling of `XML` and `__tag_div__` (used by `session.flash = T(...)`/helpers in sessions and by tickets).
- **[Compat]** Formstyles back to `table3cols`. `FORM.accepts(request_vars, session, formname, ...)` signature. `SQLFORM.grid` keyword surface (about 50 keyword parameters, `sqlhtml.py:2594-2648`).
- **[Compat]** `response.delimiters` switching, and the `{{extend}}`/`{{include}}`/`{{block}}` semantics above.
- **[Compat]** Old apps may depend on `generic.*` views being served when `generic_patterns` allows it.

## Related tests

| Module | Scope | Run by suite |
|---|---|---|
| `gluon/tests/test_html.py` (85) | Helpers, `URL`, `verifyURL`, `XML` sanitize/pickle, `TAG` pickle, CSP nonce, `FORM.xml`, `add_button` escaping, `BEAUTIFY`, `MENU`, MARKMIN XSS, `ASSIGNJS`, `SAFEJSON` | yes |
| `gluon/tests/test_form.py` (7) | `gluon/form.py` CSRF only (`test_form.py:28-110`) | yes |
| `gluon/tests/test_sqlhtml.py` (95) | Widgets, formstyles, `SQLFORM` init/accepts/factory/dictform, grid/smartgrid, exporters incl. formula neutralization, export filename encoding | yes |
| `gluon/tests/test_appadmin.py` | Calls `run_view_in` through appadmin views (`test_appadmin.py:15,87,94`) | yes |
| `gluon/tests/test_globals.py` | `include_files`/`include_meta` escaping, CSP | yes |
| `gluon/packages/yatl/tests/test_template.py` (3), `test_helpers.py` | Template engine | **no** (submodule suite not run) |

## Known gaps in test coverage

- No web2py test for `TemplateParser` itself: reindent rules, `extend`/`block`/`super`, dynamic include `eval`, delimiters, the "missing pass" errors.
- `compile_views` evaluates include/extend expressions **at compile time** with an empty context (`compileapp.py:513`, no `context=`). This is untested.
- `generic_patterns` matching with `search()` (not anchored at the start) is untested.
- `gluon/form.py`: `helper()` caching, `clear()`, `__str__`, deletion and upload paths are untested.
- FORM key rotation beyond 10 keys, `session=None` bypass, and the `record_hash`/`detect_record_change` path have no dedicated tests (`test_sqlhtml.py` never mentions `detect_record_change`).
- Grid `user_signature` rules (the `view` exception for anonymous users) have no dedicated test.
- `generic.csv` output (no neutralization) is untested.

## Open questions

1. Should `parse_template` honour its `reader` argument for the top-level file? It always uses `file_reader` (`template.py:811`), while include/extend use `self.reader`.
2. Is it intended that `_get_file_text` catches `OSError` (`template.py:467-470`) even though the default `file_reader` already converts `OSError` to `RestrictedError` (`:37-38`)? The "Unable to open included view file" message can then only come from custom readers.
3. Do any apps rely on generic-pattern matching being unanchored? For example, pattern `f.json` also matches `c/xf.json` because of `regex.search` (`compileapp.py:751-753`).
4. Is `URL(..., encode_embedded_slash=True, hmac_key=...)` verifiable? `URL` signs the per-arg-quoted `other` (`html.py:372-376`, `:404`), while `verifyURL` re-quotes the joined args without `safe=""` (`html.py:522`). **[Unverified]**

## Discrepancies with the technical reference

| Reference (`web2py_technical_reference-v2.md`) | Source |
|---|---|
| §9: `gluon.template` is the parser/compiler | `gluon/template.py` is a 1-line re-export of yatl (`parse_template`, `render` only) |
| §9: "templates compile to bytecode" | Only with `compile_application`. Otherwise views are re-parsed on each request (`compileapp.py:793-795`) |
| §9: `{{=x}}` escaped via `xmlescape`; raw needs `XML` | True, but also `SafeString`, `URL()`, `SAFEJSON`, `lazyT`, and any object with `.xml()` bypass escaping. `SCRIPT`/`STYLE` children are raw |
| §11: `_formkey` is an "encrypted token bound to the session" | It is a random `web2py_uuid()` stored in the session list (`html.py:2237-2244`). It is not encrypted |
| §11: `process()` injects the hidden fields | They are emitted by `FORM.hidden_fields()`/`xml()` (`html.py:2258-2277`) whenever `formkey`/`formname` are set by `accepts` |
| §17: CSRF token is single-use for "every form" | One-time for `FORM`/`SQLFORM`. **Reusable** for `gluon/form.py:Form`. Skipped when `session=None` |
| §11: `IS_STRONG`, `CRYPT` in `gluon.validators` | They live in `pydal/validators.py`. `gluon/validators.py` re-exports them |
| Reference omits | `gluon/form.py`, `SAFEJSON`, `ASSIGNJS`, CSP nonce on `SCRIPT`/`STYLE`, grid CSV formula neutralization |

## Findings from static reading

- **[Suspected issue]** `Form.helper()` returns the local `cached_helper`, which is unbound on the second call. So calling `form.xml()` twice would raise `UnboundLocalError` (`form.py:236-250`).
- **[Suspected issue]** `Form.clear()` is declared without `self` (`form.py:230`), so calling it raises `TypeError`.
- **[Suspected issue]** `Form.__str__` returns `bytes` (`form.py:258-259`), so `str(form)` raises `TypeError` on Python 3.
- **[Suspected issue]** `Form` deletes the record whenever `_delete` is posted (with a valid key), without checking `self.deletable` (`form.py:211-213`). `SQLFORM` does check `custom.deletable` (`sqlhtml.py:2087`).
- **[Suspected issue]** `TAG_unpickler` calls a nested unrestricted `pickle.loads` (`html.py:1349-1350`). If an app adds it to a `SafeUnpickler` allowlist (`pickle_allowed_classes`), the restriction is bypassed. It is not in the default ticket allowlist (`restricted.py:184`).
- **[Current]** `xmlescape` docstring says `quote` defaults to False, but it is True (`html.py:135-141`). `bytes` values are rendered as `"b'...'"` (`html.py:47-49`).

## Modernization considerations (optional)

- Add characterization tests for `TemplateParser` inside the web2py suite (yatl tests are not run). Pin the reindent rules and the extend/include/block semantics before touching `run_view_in`.
- Consider caching parsed non-compiled views keyed by mtime, as `cfs` already does for models.
- Split `SQLFORM.grid` into testable units only after pinning its URL/signature behaviour.
