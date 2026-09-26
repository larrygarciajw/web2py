# web2py Modernization Baseline

This document describes the state of the repository before any
modernization or refactoring changes are made. No framework source code
or test files were modified to produce it.

Baseline date: 2026-09-26

## Environment

| Item | Value |
|---|---|
| Operating system | Windows 10 Home, build 10.0.19045.7725 |
| Python | 3.14.7 (tags/v3.14.7:823f032, Aug 5 2026) [MSC v.1944 64 bit (AMD64)] |
| Python install | `C:\Users\garcialnn\AppData\Local\Python\pythoncore-3.14-64\python.exe` (invoked via WindowsApps alias) |
| Git commit | `cb91b60cb889e17a67c97434db1382089c70bce0` |
| Branch | `ai/bootstrap-analysis` |
| web2py | `3.3.3-stable+timestamp.2026.04.28.08.03.04` (`gluon/version.py`); note `gluon/__init__.py` declares `__version__ = "3.0.3"` |

## Submodules

| Submodule | Commit | Tag / describe | `__version__` |
|---|---|---|---|
| `gluon/packages/pydal` | `6fd518e09ac4fcf64408abb2259222251c870356` | `v3.20260520.0-12-g6fd518e0` | `1.20260520.0` |
| `gluon/packages/yatl` | `de225419002952c2c9554c14db605a121550a2ea` | `v20260805.1` | `20260805.1` |
| `gluon/packages/rocket3` | `4154030489ebab15b96d1f90a6f288cf4f64dd23` | `v20241225.1` | `20241225.1` |

## Optional test dependencies (not installed)

`redis`, `tornado`, `coverage`, `pycryptodome` (`Crypto`), `PyYAML`, `ldap`,
`psycopg2`, `pymysql`, `gunicorn` — none importable in this environment.
No database or Redis server was provided; tests used the default
`sqlite:memory`.

## Tests

### Commands

Official command (from `Makefile` / `gluon/widget.py:run_system_tests`):

```
W2P_SKIP_SCHEDULER_TESTS=1 python web2py.py --run_system_tests -v
```

Environment variables: `W2P_SKIP_SCHEDULER_TESTS=1`. `DB` not set
(defaults to `sqlite:memory`). Working directory: `D:\web2py`.

**Windows execution issue (environment, not a test result):**
`run_system_tests` replaces itself with `os.execv(sys.executable,
[..., "-m", "unittest", "-v", "-c", "gluon.tests"])` (`gluon/widget.py:83`).
On Windows `os.execv` spawns a new process and the parent exits
immediately (exit code 0, ~1 s). The calling shell therefore cannot wait
for the tests; in this tooling environment the detached child was
terminated and the output was truncated at
`test_languages.TestLanguagesParallel.test_reads_and_writes_no_mp`
(reproduced twice: plain Bash invocation and PowerShell
`Start-Process -Wait`). No summary line was produced by those runs.

To obtain a complete result, the exact command that the official runner
`execv`s was executed directly:

```
W2P_SKIP_SCHEDULER_TESTS=1 python -m unittest -v -c gluon.tests
```

All numbers below come from this run. The partial official runs were
consistent with it up to the truncation point (same single ERROR, same
skips).

### Results

| Metric | Value |
|---|---|
| Tests executed (`Ran`) | 487 |
| Passed | 473 |
| Failed | 0 |
| Errors | 1 |
| Skipped | 13 (reported by unittest; one is a class-level skip) |
| Expected failures / unexpected successes | 0 / 0 |
| unittest time | 18.854 s |
| Wall-clock time | ~20 s |
| Exit code | 1 |

### Pre-existing errors

1. `gluon.tests.test_contribs.TestContribs.test_pam_authentication_requires_account_approval` — ERROR

   ```
   File "gluon/contrib/pam.py", line 20, in <module>
     LIBPAM = CDLL(find_library("pam"))
   TypeError: LoadLibrary() argument 1 must be str, not None
   ```

   On Windows `ctypes.util.find_library("pam")` returns `None` (no PAM
   library exists), and `gluon/contrib/pam.py` calls `CDLL` at import
   time. The test imports the module without a platform guard. This is a
   platform/environment incompatibility of the test; it does not
   demonstrate a defect in the PAM approval logic. Not verified on Linux
   in this baseline.

### Pre-existing failures

None.

### Skipped tests

| Test | Reason |
|---|---|
| `test_tools.TestExpose.test_expose_inside_state_floow_symlink_out` | requires symlinks |
| `test_fileutils.TestFileUtils.test_untar_rejects_preexisting_escaping_symlink_directory` | symlink creation requires additional privileges |
| `test_compileapp.TestPack.test_admin_unzip_rejects_preexisting_escaping_symlink_directory` | symlink creation requires additional privileges |
| `test_recfile.TestRecfile.test_path_argument_rejects_symlink_escapes` | `WinError 1314` (symlink privilege not held) |
| `test_languages.TestLanguagesParallel.test_reads_and_writes` | multiprocessing tests unavailable (the `_no_mp` variant ran instead) |
| `test_redis.TestRedis` (`setUpClass`) | Redis library not available — whole class skipped |
| `test_serializers.TestSerializers.testYAML` | no YAML serializer available |
| `test_serializers.TestSerializers.testYAMLRejectsPythonObjectTags` | no YAML serializer available |
| `test_contribs.TestWebsocketMessaging` ×5 (`test_post_accepts_valid_signature`, `test_post_rejects_missing_signature`, `test_post_rejects_wrong_signature`, `test_token_accepts_valid_signature`, `test_token_rejects_wrong_signature`) | tornado is not installed |

Causes: 4 Windows symlink privilege, 1 multiprocessing, 1 Redis, 2 PyYAML,
5 tornado.

### Tests not executed

- **Scheduler suite** (`gluon/tests/test_scheduler.py`, 25 `def test`) —
  excluded by `W2P_SKIP_SCHEDULER_TESTS=1` (conditional import in
  `gluon/tests/__init__.py:20`).
- **Test modules not imported by `gluon/tests/__init__.py`**, never run by
  the official runner (6 modules): `test_restricted.py` (20),
  `test_login_methods.py` (13), `test_oauth20_account.py` (4),
  `test_update_languages.py` (4), `test_main.py` (1),
  `test_rocket.py` (0, placeholder) — 42 test functions.
- **Redis tests** (`test_redis.py`, 3) — skipped at class level.
- **`test_dal.TestDALAdapters.test_mysql`** reports `ok` but is a no-op:
  it only runs the pydal suite when the `TRAVIS` env var is set.
- **Submodule test suites** (pydal, yatl, rocket3) are not part of this
  command and were not run.

### Supplementary runs (outside the official command)

Run separately on the same environment (commit `cb91b60c` code, Windows 10,
Python 3.14.7) to baseline the tests the official command does not execute.

| Command | Result | Time |
|---|---|---|
| `python -m unittest -v gluon.tests.test_restricted gluon.tests.test_login_methods gluon.tests.test_oauth20_account gluon.tests.test_update_languages gluon.tests.test_main gluon.tests.test_rocket` | 42 run, 42 passed, 0 failed, 0 errors, 0 skipped | 0.38 s |
| `python -m unittest -v gluon.tests.test_scheduler` | 25 run, 25 passed, 0 failed, 0 errors, 0 skipped | 221 s (spawns worker processes) |

These results show the non-imported modules and the scheduler suite pass
when run directly; they are not included in the 487-test official figure.

### Characterization suite

`gluon/tests/characterization/` (not imported by `gluon/tests/__init__.py`,
so it does not change the official figure) pins current behavior before
any refactoring. Run with:

```
python -m unittest discover -s gluon/tests/characterization -t . -v
```

| Phase | Scope | Tests | Result |
|---|---|---|---|
| A | Compatibility contracts A1–A8 | 71 | 71 passed |
| B | Unit-level defects B1–B14 | 42 | 42 passed |
| C | In-process `wsgibase` harness C1–C9 | 38 | 38 passed |
| **Total** | | **151** | **151 passed (~1 s)** |

Identical on repeated runs, no files left behind; the official suite
still reports 487 run / 1 error / 13 skipped after adding them.

### Warnings

- `SyntaxWarning` (invalid escape sequences), emitted at bytecode
  compile time. The first (official) run showed:
  `gluon/tests/test_router.py:1884`, `gluon/tests/test_routes.py:112`,
  `gluon/tests/test_tools.py:2818`, `gluon/tests/test_tools.py:2824`,
  `gluon/contrib/webclient.py:31`. The complete run also showed
  `applications/admin/controllers/webservices.py:23` (`\w`) and `:29`
  (`\.`), repeated for each of 4 tests that exec that controller.
  (Warnings for already-compiled `.pyc` files are not re-emitted, so the
  set varies between runs.)
- `ResourceWarning` ×1: implicit cleanup of `HTTPError 302` in
  `test_contribs.TestPdfImageOrigin.test_cross_host_redirect_is_refused`.
- Logged `ERROR:web2py.redis_utils:Needs redis library to work` at import
  (redis not installed; not a test error).
- Logged `WARNING:web2py.cron` in `test_cron.TestCron.test_3_SimplePool`:
  the cron subprocess
  `web2py.py --cron_job ... -S _test_cron -R applications/_test_cron/cron/test.py`
  returned code 1 with empty stdout/stderr. The test still passed; cause
  not investigated.

### Integration tests that ran

- `test_web.TestWeb` started a real web2py server on 127.0.0.1:8000
  (`web2py.py -a testpass`), ran `testRegisterAndLogin` and
  `testStaticCache` (both ok), then killed the server.
- `test_cron` spawned `web2py.py` subprocesses.

## Environment / dependency problems

1. `os.execv` in `run_system_tests` makes the official command
   non-blocking on Windows (see above). Anyone scripting the baseline on
   Windows must run `python -m unittest -v -c gluon.tests` directly or
   wait on the child process.
2. `gluon/contrib/pam.py` cannot be imported on Windows (`CDLL(None)`).
3. Symlink tests require Windows Developer Mode or admin privilege.
4. Optional dependencies absent (redis, tornado, PyYAML, coverage), so
   those paths are untested here; `--with_coverage` would abort with
   "Coverage not installed".
5. Bundled pydal declares `requires-python >= 3.10`; this baseline ran on
   3.14 only, so 3.9 compatibility is not established here.

## Files created by the test runs (git-ignored, untracked)

Created 2026-09-26 13:47–13:49 by the test runs; none are tracked by git:
`httpserver.log`, `httpserver.pid`, `parameters_8000.py`, `welcome.w2p`,
`applications/admin/cache/`, `applications/admin/private/`,
`applications/admin/sessions/`, `applications/welcome/static/temp/`,
`applications/__pycache__/`, plus writes into `deposit/`.

`deposit/` and `logs/` were created earlier (12:26) by an exploratory
`import gluon` during architectural analysis. All left in place pending
approval.

## Notes

- Full logs (not committed) were kept in the session scratchpad:
  `baseline-direct.log` (complete run), `baseline-run.log` and
  `baseline-stderr.log` (truncated official runs).
- CI (`.github/workflows/tests.yml`) runs on Ubuntu with Python 3.9,
  3.11, 3.12 (scheduler skipped) and 3.14 (scheduler enabled); this local
  baseline is Windows / 3.14 with scheduler skipped, so it is not directly
  comparable to CI.
