# 02 — Startup and Bootstrap

## Purpose

This document describes how web2py starts, from `python web2py.py ...` or from `import gluon` in a handler, up to the moment when Rocket3 accepts requests or the CLI mode (shell, scheduler, cron, tests) takes over. It covers import-time side effects, the CLI option layer, the branch order of `gluon/widget.py:start()`, the built-in HTTP server wrapper, and the shell environment builder.

Labels: **[Current]** is present behaviour. **[Compat]** is kept for old apps or scripts. **[Legacy]** is obsolete. **[Suspected issue]** is a likely defect found by static reading only. **[Unverified]** means it could not be confirmed. Nothing here was executed. All claims come from reading the source.

## Relevant source files

| File | Role |
|---|---|
| `web2py.py` | CLI entry. Handles `-f`, `chdir`, `sys.path`, then calls `gluon.widget.start()` |
| `gluon/__init__.py` | `import_packages()`. Eagerly imports `compileapp`, `dal`, `globals`, `html`, `http`, `main`, `sqlhtml`, `validators` |
| `gluon/settings.py` | The `global_settings` `Storage` singleton |
| `gluon/main.py` | Import-time side effects, `HttpServer`, `appfactory`, `save_password` |
| `gluon/fileutils.py` | `create_missing_folders`, `add_path_first`, `abspath`, `create_welcome_w2p`, `check_credentials` |
| `gluon/console.py` | argparse CLI (`console`, `parse_args`, `load_config`) |
| `gluon/widget.py` | `start()`, `start_schedulers`, `run_system_tests`, Tk `web2pyDialog` |
| `gluon/shell.py` | `run`, `env`, `exec_environment`, `test`, `parse_path_info`, `die` |
| `gluon/newcron.py` | `hardcron`, `softcron`, `extcron`, `stopcron`, thread pools |

## Main classes / functions

| Symbol | Location | Notes |
|---|---|---|
| `main()` | `web2py.py:8` | Resolves the base path (`sys.frozen` → exe dir, py2exe **[Legacy]**). Handles `-f/--folder` before argparse (`:20-35`), then `os.chdir(path)` (`:37`) and puts `path` first on `sys.path` (`:39`) |
| `import_packages()` | `gluon/__init__.py:137` | For `pydal`, `yatl`, `rocket3`: inserts `gluon/packages/<pkg>` at `sys.path[0]` if absent, then `sys.modules[pkg] = builtins.__import__(pkg)` (`:144`) |
| `MESSAGE` | `gluon/__init__.py:128` | The "cloned without `--recursive`" hint. Raised as `RuntimeError` on any `ImportError` (`:145-146`) |
| `global_settings` | `gluon/settings.py:15` | `Storage`, so missing keys read as `None`. `settings` alias (`:16`) **[Compat]** |
| `console(version)` | `gluon/console.py:64` | Builds the parser. Returns an argparse `Namespace`. Stores a deep copy with `password="******"` in `global_settings.cmd_options` (`:752-754`) |
| `parse_args(...)` | `gluon/console.py:818` | Deprecation warnings, consistency checks, `-L` config reload |
| `load_config(file, opt_map)` | `gluon/console.py:776` | One `ast.literal_eval` per line (`:807`). The file is never executed |
| `start()` | `gluon/widget.py:660` | Dispatches the CLI mode |
| `start_schedulers(options)` | `gluon/widget.py:621` | Scheduler bootstrap |
| `run_system_tests(options)` | `gluon/widget.py:50` | `os.execv` / `os.execvpe` into `python -m unittest -c gluon.tests` |
| `HttpServer` | `gluon/main.py:722` | Rocket3 wrapper. `start()` at `:817`, `stop()` at `:829` |
| `appfactory` | `gluon/main.py:637` | Access log plus optional cProfile per request |
| `save_password` | `gluon/main.py:603` | Writes `parameters_<port>.py` |
| `run` / `env` / `exec_environment` | `gluon/shell.py:216` / `:108` / `:68` | Shell, script and programmatic environments |

### `global_settings` keys (who sets them)

| Key | Set at | Value |
|---|---|---|
| `db_sessions` | `settings.py:18-22` | `True` if `os.mkdir` is missing, otherwise `set()`. Forced `True` by `handlers/gaehandler.py:54` |
| `gluon_parent`, `applications_parent` | `settings.py:24-26` | `$web2py_path` or `os.getcwd()` at import time. `applications_parent` is overridden by `HttpServer(path=)` (`main.py:774`) |
| `app_folders` | `settings.py:28` | Cache of app folders already created (`fileutils.py:597-600`) |
| `debugging` | `settings.py:30`; `debug.py:209` | Set to `True` when `gluon.debug` is imported |
| `is_pypy`, `is_jython`, `is_source`, `is_py2` (`False`) | `settings.py:32-47` | `is_jython` and `is_py2` are **[Legacy]** |
| `web2py_version` | `main.py:125` | `gluon.version.VERSION` |
| `local_hosts` | `main.py:353-365` | Computed lazily on the first request |
| `cmd_options` | `console.py:754` | Only set when the CLI is used. It is `None` under handlers |
| `web2py_crontype` | `widget.py:766,781,785`; handlers; `anyserver.py:70,348` | `external` / `soft` / `hard` / `none` |
| `web2py_runtime_handler`, `web2py_runtime_gae`, `web2py_runtime` | `handlers/*.py` | See the import-order issue below |
| `trusted_lan_prefix` | only a commented example at `settings.py:51` | Not set by default. When set, it reaches `request.env.trusted_lan_prefix` because `Request.__init__` copies `global_settings` into `request.env` (`globals.py:317`). Admin compares it with `request.client` (from `X-Forwarded-For`); appadmin compares it with `remote_addr` (see doc 11) |

## Execution flow

### 1. Import-time bootstrap (`import gluon`, any submodule)

1. `gluon/__init__.py:149` runs `import_packages()`. It does not alias names: `sys.modules[pkg]` is simply the module that `__import__` returned. Because the vendored paths go to `sys.path[0]`, the submodules win over pip-installed `pydal`, `yatl` and `rocket3`, unless one of them was already imported (then `__import__` returns the cached module). **[Current]**
2. Any `ImportError`, including one raised *inside* pydal for a missing third-party dependency, produces the "submodule not cloned" message (`__init__.py:145-146`). **[Current]**
3. `gluon/__init__.py:151-158` imports `compileapp`, `dal`, `globals`, `html`, `http`, `main`, `sqlhtml` and `validators`. So importing *anything* from `gluon`, including `gluon.settings`, first executes the whole of `gluon/main.py` module level.
4. `gluon/main.py` module level runs these side effects:
   - `web2py_path = global_settings.applications_parent` (`:56`) **[Compat]**
   - `create_missing_folders()` (`:58-61`, `fileutils.py:582`) creates `applications/`, `deposit/`, `site-packages/` and `logs/` under `gluon_parent` (skipped on GAE). It also calls `add_path_first` for `gluon_parent`, `site-packages` and `""`, which reorders `sys.path` and calls `site.addsitedir` (`fileutils.py:603-609`). `OSError` is swallowed with a `print`.
   - If `not global_settings.web2py_runtime_handler` (`:68`): it imports `gluon.messageboxhandler` (Tkinter), sets `logging.gluon = gluon` (`:74`) and calls `locale.setlocale(LC_CTYPE, "C")` (`:79`).
   - `logging.config.fileConfig(abspath("logging.conf"))`, with `logging.basicConfig()` on any exception (`:81-84`). No `logging.conf` is shipped: it is git-ignored (`.gitignore:22`) and only `examples/logging.example.conf` exists. By default the fallback `basicConfig()` therefore applies. **[Current]**
   - It monkeypatches `pydal.get_default_represent = lambda value: value` (`:93`).
   - It imports `newcron`, `compileapp`, `globals`, `rewrite` and others. It then runs `load_routes()` (`:128`), which executes `routes.py` if present (`rewrite.py:344`, `exec` at `:379`).

**[Suspected issue] `web2py_runtime_handler` has no effect.** Every handler does `from gluon.settings import global_settings` and then sets the flag (for example `handlers/wsgihandler.py:29-31`). That import already executed `gluon/__init__.py:156` → `gluon/main.py:68` while the flag was still `None`. So the Tkinter import and the locale change always happen, and `main.py:68` is the only reader of the flag (grep). The same ordering means `gaehandler.py:53` sets `web2py_runtime_gae` *after* `create_missing_folders()` has already run with the GAE check off.

### 2. `web2py.py` → `widget.start()` branch order (`gluon/widget.py:660-925`)

| # | Condition | Action | Exits? |
|---|---|---|---|
| 0 | always | `console()` parses the CLI (`:664`). Checks that `multiprocessing` is importable if `-X` or more than one `-K` (`:666-670`, **[Legacy]** Py2.6 guard) | — |
| 1 | `-G/--GAE` | Copies `examples/app.example.yaml` → `app.yaml` if `app.yaml` is absent, and `handlers/gaehandler.py` → `./gaehandler.py` (`:672-688`). **[Suspected issue]** `examples/app.example.yaml` no longer exists (deleted in commit `53405bb4`), and `content` is `bytes` while the `.replace` arguments are `str` (`:679-680`). The branch only avoids crashing because a tracked `app.yaml` already exists. The copied `gaehandler.py` is Py2-only (see 12-deployment) | return |
| 2 | always | Sets the `web2py` and root logger levels (`:690-692`). `create_welcome_w2p()` (`:695`, `fileutils.py:332`) packs `welcome.w2p` if it is missing or `NEWINSTALL` exists | — |
| 3 | `--run_system_tests` | `run_system_tests` → `os.execv(sys.executable, [..,"-m","unittest",("-v"),"-c","gluon.tests"])` (`:83`), or `os.execvpe("coverage", ...)` with `--with_coverage` (`:79`). On Windows `execv` spawns a detached child and the parent exits 0 (baseline.md) | process replaced |
| 4 | `-Q` | Removes stdout/stderr `StreamHandler`s from all loggers and replaces `sys.stdout` with `NullFile` (`:701-728`). Otherwise prints the banner and the pydal `DRIVERS` (`:730-737`) | — |
| 5 | `-T` | `shell.test()` doctests (`:739-742`) | return |
| 6 | `-S` | Sets `sys.argv = [run or ""] + args`, then calls `shell.run(...)` with `-P/-B/-M/-R/--cron_job/--force_migrate/--fake_migrate` (`:744-757`) | return |
| 7 | always | Resizes the cron pools: `newcron.dancer_size(min_threads)`, `launcher_size(cron_threads)` (`:760-761`) | — |
| 8 | `-C` | `web2py_crontype="external"` and `newcron.extcron()` (`:763-768`) | return |
| 9 | `-K` without `-X` | `start_schedulers()` (`:770-776`) | return |
| 10 | `-Y` | `--soft_cron` → `web2py_crontype="soft"` (the tick happens in `wsgibase`, `main.py:593-597`). Otherwise `"hard"` and `newcron.hardcron(...).start()`. The constructor runs the `@reboot` crondance synchronously (`newcron.py:83-90`) | — |
| 11 | (`not --no_gui` and password `<ask>`) or `-t` | Tries `tkinter.Tk()`. On failure it sets `no_gui` (`:793-803`). If a root exists, it runs `web2pyDialog` (`widget.py:115`), which builds its own `HttpServer` (`:510`), then `sys.exit()` (`:805-830`) | exit |
| 12 | `-X` and `-K` | Runs `start_schedulers` in a `threading.Thread` (`:834-836`) | — |
| 13 | password `<ask>` | `getpass.getpass("choose a password:")` (`:841-842`) | — |
| 14 | always | Chooses ip/port (the first `--interface` wins), prints the URL and the kill hint, patches `linecache.getline` (`:874-893`), then `main.HttpServer(...)` (`:895`) and `.start()` (`:917`). `KeyboardInterrupt` → `server.stop()`, then joins the scheduler thread | blocks |

`start_schedulers` (`widget.py:621-657`): with exactly one `-K` app and no `-X`, it calls `shell.run(app, True, True, None, False, code, False, True)` in-process. Otherwise it starts one `multiprocessing.Process` per app, 0.7 s apart. The generated code is `current._scheduler.loop()`, optionally after setting `group_names` (`:609-618`). So the app's models must assign `current._scheduler`.

### 3. CLI option layer (`gluon/console.py`)

Key options and their defaults (argparse `default=`):

| Option | Default | Notes |
|---|---|---|
| `-f/--folder` | `os.getcwd()` (`:193-200`) | Also handled early in `web2py.py:20-35` |
| `-L/--config` | — | Must be an existing file |
| `-a/--password` | `"<ask>"` (`:223-230`) | Accepts `<recycle>`, `<random>`, `<pam_user:USER>` (see `save_password`) |
| `-D/--log_level` | `WARNING` | Name, or deprecated integer 0-100 |
| `-i/--ip`, `-p/--port` | `127.0.0.1`, `8000` | Ignored if `--interface` is given |
| `-k/-c/--ca_cert` | — | SSL key, cert and CA. Must exist |
| `--interface` | `[]` | `IP,PORT[,KEY,CERT[,CA]]`, repeatable |
| `-d` / `-l` | `httpserver.pid` / `httpserver.log` | |
| `--min_threads` / `--max_threads` | `None` | |
| `-q` / `-o` / `--socket_timeout` | `5` / `10` / `5` | The `HttpServer` default for `socket_timeout` is `1`, but the CLI passes `5` |
| `-F/--profiler_dir` | — | Enables per-request cProfile in `appfactory` |
| `-K` / `-X` | `[]` / `False` | `APP[:GROUP...]`, legacy comma form accepted |
| `-Y`, `--soft_cron`, `-C`, `--crontab`, `--cron_threads` | | `--cron_job` is internal and hidden |
| `-S`, `-M`, `-R`, `-A`, `-B`, `-P`, `--force_migrate`, `--fake_migrate` | | `-A` is `REMAINDER` and must come last |
| `-T`, `--run_system_tests`, `--with_coverage`, `-v` | | |
| `-G/--GAE` | — | |

- **Deprecated aliases [Compat]:** `deprecated_opts` has **16 entries** (`console.py:74-91`). They are `--debug`, `--nogui`, `--ssl_private_key`, `--ssl_certificate`, `--interfaces`, `-n`, `--numthreads`, `--minthreads`, `--maxthreads`, `-z`, `--shutdown_timeout`, `--profiler`, `--run-cron`, `--softcron`, `--cron` and `--test`. There are also 26 hidden hyphenated spellings in `_omitted_opts` (`:99-126`). The architecture report's "~32" matches neither count exactly.
- **Checks in `parse_args` (exit 2):** `-R` needs `-S`; `-A` needs `-R`; `-X` needs `-K`; `--soft_cron` needs `-Y` (`:858-865`). `-S` conflicts with `-X/-K/-Y/-C/-T/--run_system_tests` (`:866-876`). `-B` conflicts with `-P`. `-C` conflicts with `-Y/-T/--run_system_tests`. `-T` conflicts with `--run_system_tests`. `-K`/`--crontab` values naming missing apps are dropped with a warning, and the program dies if none are left (`:844-852`).
- **`-L` config file:** `load_config` reads lines `name = <literal>` for the keys in `opt_map` (`:904-954`), evaluates them with `ast.literal_eval`, converts them back into CLI tokens, and **re-parses them without the original CLI args** unless `--add_options` is set (`:960-979`). `folder`, `GAE`, `cron_job`, `fake_migrate` and the deprecated names cannot be set from the file. With no PEP 263 header the file is opened as `ascii` (`:797`).
- **[Suspected issue] `-t/--taskbar` crashes.** `parse_args` binds `os` as a loop variable (`for o, os in dict(...)`, `:867`, `:880`), so `os` is local for the whole function. A `symtable` check confirms `os` is local in `parse_args`. Line `:854` (`options.taskbar and os.name != "nt"`) therefore raises `UnboundLocalError` whenever `-t` is given.
- The help text for `-X` says "require --K" (`:590`). That is a typo for `-K`.

### 4. `HttpServer`, `appfactory`, `save_password`, `stop`

- `HttpServer.__init__` (`main.py:727-815`) validates that `interfaces` is a list of tuples. `widget` always passes `path=options.folder`, so it always runs `chdir`, calls `load_routes()` a **second** time, runs `add_path_first` again and reloads `logging.conf` if it exists (`:770-781`). It then calls `save_password(password, port)` (`:782`) and sets the module globals `rocket3.SERVER_NAME` and `SOCKET_TIMEOUT`. For SSL, a missing module, cert or key logs a warning and the server **continues on plain HTTP** (`:789-803`). Finally it builds `rocket3.Rocket3(..., method="wsgi", app_info={"wsgi_app": appfactory(wsgibase, ...)}, handle_signals=False)` (`:804-815`).
- `appfactory` (`:637-719`) always wraps `wsgibase`. It writes a CSV-like access line with `REMOTE_ADDR` (not `request.client`) to `httpserver.log`, and swallows all logging errors. `profilerfilename` raises `BaseException("Deprecated API")` (`:653-654`).
- `save_password(password, port)` (`:603-634`) writes `parameters_<port>.py` as Python source (admin later executes it with `restricted`, `applications/admin/models/access.py:33-35`):
  - `<random>`: 8 characters from `secrets.choice`, printed to stdout, stored as `CRYPT()` hash.
  - `<recycle>`: keeps an existing file. If there is none, it writes `password=None`.
  - `<pam_user:X>`: stores the literal `pam_user:X`.
  - `""`: writes `password=None`, which disables admin.
- `start()` (`:817-827`) installs SIGTERM/SIGINT handlers that call `stop()`, writes the pid file and runs `Rocket3.start()`.
- `stop()` (`:829-845`) calls `newcron.stopcron()` only for **soft** cron, unlinks the pid file, then `os.kill(os.getpid(), signal.SIGKILL)` inside a bare `except`. `stoplogging` is unused. **[Suspected issue]** Windows has no `signal.SIGKILL`, so on Windows `stop()` silently does not terminate the process. The Rocket server itself is never stopped explicitly. **[Unverified]** how Rocket3 then exits on Windows.

### 5. Shell environment (`gluon/shell.py`)

- `env(a, import_models, c, f, dir, extra_request)` (`:108-196`) builds a fake `Request({})`: `http_host` comes from `cmd_options` ip/port or `127.0.0.1:8000`, and `remote_addr="127.0.0.1"`. It **monkeypatches `gluon.fileutils.check_credentials` to always return `True` for the rest of the process** (`:174-177`). This affects attribute-style callers (`compileapp.py:632`, admin `access.py:42`, `appadmin.py:41,45`). It does not affect `tools.py:64`, which imported the name directly. It optionally runs `run_models_in` and exits 1 on `RestrictedError`.
- `run(appname, ...)` (`:216-402`) parses `a/c/f?x=y`. It offers to create a missing app (not for cron or scheduler jobs). `--force_migrate` patches `DAL.__init__` globally (`:265-279`). It executes the controller, preferring `.pyc` for cron jobs, then `exec("print( %s())" % f)` (`:308`). It then runs `startfile` (`execfile` or `read_pyc`), inline `python_code` (scheduler) or `scripts/migrator.py`. It commits with `BaseAdapter.close_all_instances("commit")` **only if `import_models`**, and rolls back on exceptions, re-raising `SystemExit` (`:314-359`). Otherwise it starts bpython, IPython or `code.interact`.
- `exec_environment(pyfile, ...)` (`:68-105`) is the programmatic loader. It prefers `pyfile + "c"` if present, and uses `build_environment(..., store_current=False)`.
- `raw_input = input` (`:44`) and `execfile` (`:38`) are Py2 shims. **[Compat]**
- **[Suspected issue] `-T` doctests:** `test()` references the undefined Py2 name `ClassType` (`shell.py:494`). This line is reached for every function or class found, so doctest runs should raise `NameError`.
- **[Suspected issue]** In `run()`, if the controller `.py` is missing, `read_pyc(pycfile)` runs even when the `.pyc` is also missing. The `else: die(errmsg)` branch at `:303-304` is unreachable.

### 6. Cron at startup (brief)

`newcron` has global pools `_dancer = SimplePool(5, SoftWorker)` and `_launcher = SimplePool(5)` (`newcron.py:392-403`). `grow` ignores `None`. Hard cron is a daemon thread that ticks each minute. Soft cron runs after each request in `wsgibase`. External cron (`-C`) runs once. Jobs are subprocesses of `web2py.py` (`Worker.run`, `:257-300`).

## Dependencies

- stdlib: argparse, ast, logging.config, locale, multiprocessing, threading, signal, getpass, linecache, tkinter (optional), code/readline (shell)
- Submodules: `rocket3.Rocket3` (`gluon/packages/rocket3/rocket3/__init__.py:549`), pydal (`DRIVERS`, `BaseAdapter`), yatl
- Optional: IPython, bpython, coverage

## Side effects

| When | Effect |
|---|---|
| Any `import gluon*` | mkdir `applications/ deposit/ site-packages/ logs/`, `sys.path` reordering plus `site.addsitedir`, Tkinter import, `LC_CTYPE=C`, logging config, pydal monkeypatch, `routes.py` exec |
| `web2py.py` | `os.chdir(path)`; `welcome.w2p` created; `NEWINSTALL` deleted |
| Server start | `parameters_<port>.py` written, `httpserver.pid`, `httpserver.log`, second `load_routes()`, global `rocket3.SERVER_NAME` |
| `-S`/`-K`/cron job | `check_credentials` globally replaced; optional `DAL.__init__` patch; `.pythonhistory` in the app folder |
| `-Q` | `sys.stdout` replaced for the process |

## Compatibility constraints

- Keep the `global_settings`/`settings` alias, `main.web2py_path`, and the `Storage` semantics of `global_settings` (many call sites rely on `None` for unset keys).
- Keep the 16 deprecated CLI aliases, the hyphen spellings, the legacy `-K app1,app2` form and integer `-D` levels.
- Keep the `parameters_<port>.py` format (Python assignment executed by admin) and the special password tokens.
- Keep the `import_packages()` path precedence. Apps do `import pydal` / `from gluon.dal import ...`.
- `web2pyDialog` (Tk GUI) is still the default when no `-a` is given and Tk is available. **[Legacy]** but reachable.

## Related tests

| Test | Covers | Run by suite? |
|---|---|---|
| `gluon/tests/test_main.py:13` `test_save_password_random` | `save_password("<random>")` | **No** (not imported in `gluon/tests/__init__.py`) |
| `gluon/tests/test_web.py:23-45` | Real `web2py.py -a testpass` subprocess, port 8000 | Yes |
| `gluon/tests/test_cron.py` (`test_1_Token`, `test_2_crondance`, `test_3_SimplePool`) | newcron, spawns `web2py.py` | Yes |

## Known gaps in test coverage

- No tests at all for `console.py` (parsing, conflicts, `load_config`, deprecated warnings, the `-t` crash), `widget.start()` branch order, `import_packages`, `shell.run/env/exec_environment/test`, `HttpServer`/`stop()`, `appfactory`, or `save_password` `<recycle>`/`<pam_user:>`.
- Import-time side effects in `main.py` are untested, as is the `web2py_runtime_handler` ordering.

## Open questions

1. Is the `web2py_runtime_handler` flag meant to be set before `import gluon`? No handler can currently do that without bypassing the package `__init__`.
2. How does the Rocket3 server shut down on Windows when `stop()` cannot SIGKILL? **[Unverified]**
3. Does anyone rely on `-L` discarding the other CLI args when `--add_options` is not set?
4. `applications/admin/controllers/toolbar.py:2` does `from gluon.settings import global_settings, read_file`, but `gluon/settings.py` defines no `read_file`. `:16` reads `cmd_options.profiler_filename`, an option that no longer exists (`--profiler_dir`). **[Suspected issue]** The toolbar controller cannot load.

## Discrepancies with the technical reference

| Reference (§5) | Source |
|---|---|
| "`web2py.py` initialises `global_settings`" | `global_settings` is populated by `gluon/settings.py` at import and later by `main.py`, `console.py` and `widget.py`. `web2py.py` only does `chdir`/`sys.path` |
| Lists `-S/-M/-R/-K/-X` only | 40+ options, config-file loading, 16 deprecated aliases, and conflict rules |
| `wsgihandler.py` "adjusts sys.path, sets cwd, exposes wsgibase" | True, but it also sets `web2py_runtime_handler` too late to matter (see above) |
| `exec_environment` in compileapp (§14.3) | It is in `gluon/shell.py:68` (already noted in the architecture report) |
| `-X` runs the scheduler "in the same process" | `-X` starts a thread that spawns one `multiprocessing.Process` per app (`widget.py:634-647`) |

## Modernization considerations (optional)

- Move the `gluon/main.py` side effects (folders, locale, logging, routes) into an explicit `bootstrap()` called by `web2py.py` and the handlers. That would make `web2py_runtime_handler` meaningful and imports pure.
- Add characterization tests for `console.parse_args` (including `-t`), `load_config` and `save_password` tokens before touching the CLI.
- Scope the `check_credentials` monkeypatch in `shell.env` to the shell/scheduler process explicitly, or replace it with a flag.
