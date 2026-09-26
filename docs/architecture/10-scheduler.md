# 10 — Scheduler

## Purpose

This document describes the database-backed task scheduler in `gluon/scheduler.py`: its tables, task lifecycle, worker/ticker coordination, the per-task subprocess executor, the public API, and how workers are launched. It also notes the two alternative scheduler implementations that exist in the tree.

Labels: **[Current]**, **[Compat]**, **[Legacy]**, **[Suspected issue]** (static reading, not proven), **[Unverified]**. Nothing was executed to write this document.

## Relevant source files

| File | Role |
|---|---|
| `gluon/scheduler.py` (2010 lines) | `Scheduler`, `executor`, `JobGraph`, `CronParser`, validators, `main()` |
| `gluon/widget.py` | `-K`/`-X` launch (`start_schedulers`, `get_code_for_scheduler`), Tk GUI scheduler menu |
| `gluon/console.py` | `-X/--with_scheduler` (`:584-591`), `-K/--scheduler APP[:GROUPS]` (`:597-625`), consistency check (`:862-863`) |
| `gluon/shell.py` | `run(..., python_code, scheduler_job)` (`:216-340`) and `env(...)` (`:108+`) used by the worker and the executor |
| `applications/welcome/models/db.py` | Optional `Scheduler(db, heartbeat=...)` behind `scheduler.enabled` (`:137-139`) |
| `applications/welcome/private/appconfig.ini` | `[scheduler] enabled = false, heartbeat = 1` |
| `gluon/packages/pydal/pydal/tools/scheduler.py` (428 lines) | Independent pydal `Scheduler` class. Not used by gluon |
| `gluon/contrib/redis_scheduler.py` (829 lines) | `RScheduler(Scheduler)`, a Redis-backed variant |
| `gluon/tests/test_scheduler.py` | 25 tests |

## Main classes / functions

### Constants and status lists (`scheduler.py:92-123`, `:609-611`)

| Name | Value / members | Notes |
|---|---|---|
| `IDENTIFIER` | `"hostname#pid"` (`:92`) | Default `worker_name` |
| Task statuses | `QUEUED, ASSIGNED, RUNNING, COMPLETED, FAILED, TIMEOUT, STOPPED, EXPIRED` (`:96-109`) | |
| Worker statuses | `ACTIVE, PICK, DISABLED, TERMINATE, KILL, STOP_TASK` (`:103-108`) | |
| `HEARTBEAT = 3`, `MAXHIBERNATION = 10` | `:111-112` | seconds |
| `CLEAROUT = "!clear!"` | `:113` | Printing it resets the captured output |
| `RESULTINFILE = "result_in_file:"` | `:114` | Prefix used when a result is ≥1024 chars |
| `TASK_STATUS` | `(QUEUED, RUNNING, COMPLETED, FAILED, TIMEOUT, STOPPED, EXPIRED)` (`:609`) | **omits `ASSIGNED`** |
| `RUN_STATUS` | `(RUNNING, COMPLETED, FAILED, TIMEOUT, STOPPED)` (`:610`) | |
| `WORKER_STATUS` | `(ACTIVE, PICK, DISABLED, TERMINATE, KILL, STOP_TASK)` (`:611`) | |

### Tables (`Scheduler.define_tables`, `scheduler.py:887-1023`)

| Table | Key fields | Notes |
|---|---|---|
| `scheduler_task` | `application_name` (`IS_NOT_EMPTY`, `writable=False`), `task_name`, `group_name="main"`, `status` (`IS_IN_SET(TASK_STATUS)`, default `QUEUED`, `writable=False`), `broadcast`, `function_name` (`IS_IN_SET(tasks)` if a `tasks` dict is given), `uuid` (unique), `args`/`vars` (JSON text, `TYPE(list/dict)`), `enabled`, `start_time`, `next_run_time`, `stop_time`, `repeats` (0 = unlimited), `retry_failed` (-1 = unlimited), `period` (60), `prevent_drift`, `cronline` (`IS_CRONLINE`), `timeout` (60, ≥1), `sync_output`, `times_run`, `times_failed`, `last_run_time`, `assigned_worker_name` | `on_define=set_requirements` defaults `application_name` to `"app/controller"` of the current request (`:877-885`) |
| `scheduler_run` | `task_id`, `status` (`IS_IN_SET(RUN_STATUS)`), start/stop, `run_output`, `run_result`, `traceback`, `worker_name` | One row per execution |
| `scheduler_worker` | `worker_name` (unique), heartbeats, `status`, `is_ticker`, `group_names` (`list:string`), `worker_stats` (`json`) | |
| `scheduler_task_deps` | `job_name`, `task_parent` (int), `task_child` (reference), `can_visit` | Used by `JobGraph` |

The `migrate` argument may be a string prefix, which produces the `.table` filename (`__get_migrate`, `:864-871`).

### Core symbols

| Symbol | Evidence | Role |
|---|---|---|
| `Task`, `TaskReport` | `:134-169` | Plain objects passed through multiprocessing queues |
| `JobGraph.add_deps/validate` | `:172-232` | Topological sort of `scheduler_task_deps`. Commits on success and **rolls back** on failure |
| `CronParser` | `:235-483` | Cron expression iterator (`next()`) |
| `executor(retq, task, outq)` | `:486-560` | Runs inside the child process |
| `IS_CRONLINE`, `TYPE` | `:563-606` | Field validators |
| `Scheduler(threading.Thread)` | `:614-693` | `daemon=True`, sets `current._scheduler = self` (`:690`), defines tables |
| `Scheduler.execute` | `:695-803` | Spawns one `multiprocessing.Process` per task |
| `Scheduler.run` | `:854-859` | Heartbeat thread body: `send_heartbeat` in a loop |
| `Scheduler.loop` | `:1025-1105` | Main worker loop |
| `pop_task` / `wrapped_pop_task` | `:1153-1228` / `:1136-1151` | Take an `ASSIGNED` task, mark it `RUNNING`, compute `next_run_time` |
| `report_task` / `wrapped_report_task` | `:1248-1313` / `:1230-1246` | Store the run and update the task status |
| `send_heartbeat` | `:1330-1441` | Heartbeat, worker commands, dead-worker cleanup, ticker election |
| `being_a_ticker` | `:1443-1482` | Ticker election (`FIXME` deadlock at `:1463`) |
| `assign_tasks` / `wrapped_assign_tasks` | `:1505-1644` / `:1484-1503` | The ticker distributes due tasks to workers |
| `set_worker_status`, `disable`, `resume`, `terminate`, `kill` | `:1651-1716` | Write `scheduler_worker.status` |
| `queue_task` | `:1718-1772` | `validate_and_insert` into `scheduler_task` |
| `task_status` | `:1774-1826` | Lookup by id / uuid / `Query`, optionally with a left-joined run |
| `stop_task` | `:1828-1869` | `RUNNING` → worker `STOP_TASK`. `QUEUED` → `STOPPED` + disabled |
| `get_workers` | `:1871-1892` | Dict of registered workers |
| `main()` | `:1895-2006` | Standalone `python gluon/scheduler.py` runner **[Legacy]** |

## Execution flow

### Launch paths

| Path | Evidence | Behaviour |
|---|---|---|
| `web2py.py -K app[:g1:g2]` (without `-X`), single app | `widget.py:770-775`, `:621-630` | `shell.run(app, True, True, None, False, code, False, True)` runs in the current process |
| `-K a1 -K a2` or `-X -K ...` | `widget.py:632-656`, `:834-837` | One `multiprocessing.Process(target=shell.run)` per app, started 0.7 s apart. With `-X` this happens in a thread alongside the web server |
| Tk GUI | `widget.py:320-363` | Same `Process(target=run, ...)` per app from the scheduler menu |
| `code` string | `widget.py:609-618` | `"from gluon.globals import current;[current._scheduler.group_names=[...];]current._scheduler.loop()"`. Group names from the CLI are interpolated into code that is later `exec`'d (`shell.py:332-334`) |
| Standalone `main()` | `scheduler.py:1895-2006` | optparse. Hard-coded default `db_folder` `/Users/mdipierro/...` (`:1947`) **[Legacy]** |

`shell.run(..., scheduler_job=True)` sets `request.is_scheduler = True` (`shell.py:286-287`) and imports the models. The models must build a `Scheduler`, because the code relies on `current._scheduler` having been set by `Scheduler.__init__` (`scheduler.py:690`). **[Current]**

### Worker loop (`loop`, `scheduler.py:1025-1105`)

1. Install a SIGTERM handler that calls `sys.exit(1)` (`:1043`) and start the heartbeat thread (`:1044`).
2. While `have_heartbeat`: if the status is `DISABLED`, sleep (`:1046-1055`). If this worker is the ticker and `do_assign_tasks` is set, call `wrapped_assign_tasks` (`:1057-1060`).
3. `wrapped_pop_task` commits first (a "MySQL only" FIXME, `:1143`) and retries `pop_task` up to 10 times with 0.5 s sleeps. After that it returns `None`.
4. When a task is popped, `execute(task)` runs, then `wrapped_report_task`, which retries **forever** (`:1237`, FIXME).
5. With no task: `has_pending_due_tasks()` (`:1107-1134`) prevents `max_empty_runs` self-termination while due `QUEUED/ASSIGNED` work exists. A greedy ticker re-assigns tasks. Then sleep.

### Pop (`pop_task`, `scheduler.py:1153-1228`)

- It selects one task with `assigned_worker_name == me` and `status == ASSIGNED`, ordered by `next_run_time`, sets `status=RUNNING` and `last_run_time=now`, then commits (`:1158-1166`).
- `next_run_time` is computed from `cronline` (`:1172-1174`), or `last_run_time + period` (no drift prevention, `:1175-1176`), or `start_time + k*period` with `prevent_drift` (`:1177-1183`).
- `run_again = times_run < repeats or repeats == 0` (`:1185-1191`).
- A `scheduler_run` row is inserted in a retry loop unless `discard_results` is set (`:1193-1204`).

### Execute (`execute`, `scheduler.py:695-803`)

1. It creates `outq` and `retq(maxsize=1)` and a `Process(target=executor)`. With `use_spawn` it uses `get_context("spawn")` (`:706-718`).
2. While the child is alive and not past `timeout`: drain `outq` with 2 s gets, handle `CLEAROUT`, write `run_output` to `scheduler_run` and commit, then `p.join(timeout=sync_output or timeout)` (`:724-760`).
3. A final drain of `outq` follows (`:765-776`). On timeout it calls `terminate_process` and tries `retq.get(timeout=2)` for a traceback, with status `TIMEOUT` (`:777-787`). On normal exit it calls `retq.get_nowait()`. An empty queue means `STOPPED` (`:788-795`). An exception in the parent loop gives `STOPPED` (`:761-764`).
4. If the result starts with `RESULTINFILE`, it reads and deletes the temp file (`:797-802`).

### Executor (child process, `scheduler.py:486-560`)

1. It redirects `sys.stdout` to `outq` (`LogOutput`, `:490-510`).
2. `parse_path_info(task.app)` → `gluon.shell.env(a, c, import_models=True, extra_request={"is_scheduler": True})` (`:520-523`). **The app's models run again inside every task process.**
3. Function lookup: `current._scheduler.tasks` dict if present, otherwise **any callable name in the model environment** (`:526-534`). `CALLABLETYPES` check (`:535-536`).
4. It injects `W2P_TASK` (id, uuid, run_id) into the env and into `current` (`:509`, `:538-540`), and calls `globals().update(_env)` (`:541`).
5. `args = json.loads(task.args)`, `vars = json.loads(task.vars)`. The result is `json.dumps(...)` (`:542-544`).
6. A result of 1024 chars or more goes to `tempfile.mkstemp(suffix=".w2p_sched")` and is replaced by `RESULTINFILE + path` (`:550-554`).
7. A bare `except` produces `TaskReport("FAILED", tb=...)` (`:556-558`). A missing `task.app` raises `ValueError` (`:545-549`).

### Report (`report_task`, `scheduler.py:1248-1313`)

- A run row is kept only if `result != "null"` or there is a traceback. Otherwise it is deleted (`:1257-1272`).
- `COMPLETED`: the status becomes `EXPIRED` if `run_again` and the next run passes `stop_time`, `QUEUED` if `run_again`, otherwise `COMPLETED`. `times_failed` is reset. Dependencies are unblocked on `COMPLETED` (`:1275-1294`, `update_dependencies` `:1315-1318`).
- Failure: `STOPPED` maps to `FAILED`. The task is re-queued while `times_failed < retry_failed` or while `retry_failed == -1` (`:1294-1312`).

### Heartbeat, ticker and dead workers (`send_heartbeat`, `scheduler.py:1330-1441`)

- The heartbeat thread uses its **own DAL connection** (`DAL(self.db._uri, ..., decode_credentials=True)`), reconnects on `OperationalError`, and redefines the tables with `migrate=False` (`:1341-1354`).
- It inserts or updates the `scheduler_worker` row and reacts to the stored status: `DISABLED` (sleep), `TERMINATE` (`give_up`), `KILL` (`die`, return), `STOP_TASK` (`terminate_process`), otherwise `ACTIVE` (`:1362-1406`).
- Every 5 beats, or on `PICK`: it re-queues `RUNNING` tasks of workers whose heartbeat is older than 3×heartbeat (ACTIVE) or 45×heartbeat (others), deletes those workers, and runs `being_a_ticker()` (`:1408-1434`).
- Ticker election: when no other ACTIVE worker has `is_ticker` and this worker is not busy, it sets itself `is_ticker=True` and all others `False`. The code carries the comment "FIXME: This can easily cause deadlocks" (`:1459-1470`, FIXME at `:1463`).

### Assignment (`assign_tasks`, `scheduler.py:1505-1644`)

1. Group the ACTIVE workers by group, skipping those whose `worker_stats.status == "RUNNING"` (`:1516-1527`).
2. Mark `QUEUED/ASSIGNED` tasks past `stop_time` as `EXPIRED` (`:1530-1532`).
3. Dependency filter through `scheduler_task_deps.can_visit` (`:1535-1557`).
4. `limit = len(all_workers) * (50 / (len(wkgroups) or 1))` per group (`:1559`).
5. Broadcast tasks: insert one `ASSIGNED` copy per worker and advance the original (`:1587-1618`). Normal tasks: set `status=ASSIGNED, assigned_worker_name=...` (`:1619-1631`).
6. `greedy = tnum >= limit` (`:1642`).

### Timeouts, retries, repeats, periods

| Setting | Where enforced |
|---|---|
| `timeout` | `execute` loop condition and terminate (`:730-732`, `:777-787`) |
| `sync_output` | Join interval and partial `run_output` saves (`:724-727`, `:743-758`) |
| `repeats` | `pop_task` `run_again` (`:1185-1191`) |
| `retry_failed` | `report_task` (`:1301-1307`) |
| `period` / `prevent_drift` / `cronline` | `pop_task` (`:1172-1183`) |
| `stop_time` | `report_task` `EXPIRED` (`:1274-1284`), `assign_tasks` (`:1530-1532`) |

## Dependencies

- `gluon` (DAL, Field, validators) (`scheduler.py:37-47`), `pydal.objects.Query`, `pydal.utils.utcnow`, `gluon.storage`, `gluon.utils.web2py_uuid`.
- `gluon.shell.env` / `parse_path_info` inside the executor (`:517`).
- stdlib `multiprocessing`, `threading`, `signal`, `tempfile`, `json`.
- The database is the only coordination channel between workers. There is no broker.

## Side effects

- Each task spawns an OS process that re-imports gluon (with spawn) and **re-runs the app models** (`:520-522`). Importing gluon creates folders (see CLAUDE.md).
- Writes rows to all four tables, deletes dead worker rows, and commits frequently, including `db.commit()` in `JobGraph.validate` and `rollback` on its failure (`:227-232`). That rollback discards unrelated pending work in the caller's transaction.
- Temp files `*.w2p_sched` in the system temp dir for large results (`:551`). They are deleted by the parent after the read (`:801`).
- `sys.stdout` is replaced in the child. A SIGTERM handler is installed in the worker process (`:1043`).
- `queue_task(immediate=True)` sets the ticker worker status to `PICK` (`:1768-1769`).

## Compatibility constraints

- **[Compat]** Table and column names, status strings, and JSON `args`/`vars` in text columns. Existing apps and appadmin queries (`USAGE`, `:51-58`) depend on them.
- **[Compat]** Task function lookup through the model environment when no `tasks` dict is given.
- **[Compat]** `-K app:group1:group2` syntax and legacy `app1,app2` (`console.py:600-614`).
- **[Compat]** `W2P_TASK` injection and `CLEAROUT` / `RESULTINFILE` conventions.

## Related tests

`gluon/tests/test_scheduler.py` (25 tests):

| Class | Tests | Nature |
|---|---|---|
| `CronParserTest` | 15 | Pure parsing (`:61-444`) |
| `TestsForJobGraph` | 3 | DB only (`:446-590`). Cyclic → `None` |
| `TestsForSchedulerAPIs` | 2 | `queue_task`, `task_status` (`:592-642`) |
| `TestsForSchedulerRunner` | 5 | Writes a model file and runs **`subprocess.call([python, "web2py.py", "-K", app])`** (`:684-699`). Covers repeats/expired/priority, timeout/progress, drift/immediate, retry, regressions |

- The whole module is imported only when `W2P_SKIP_SCHEDULER_TESTS` is unset (`gluon/tests/__init__.py:20-21`). The accepted baseline (`docs/ai-context/baseline.md`) sets it, so these tests are **not counted** (not even as skipped).
- CI runs them only on Python 3.14. They are skipped on 3.9/3.11/3.12 in GitHub Actions (`.github/workflows/tests.yml:21-29`) and AppVeyor (`appveyor.yml:10-25`).

## Known gaps in test coverage

- `stop_task`, `disable/resume/terminate/kill`, `set_worker_status` `exclude`, broadcast tasks, `use_spawn`, `sync_output` edge cases, `discard_results`, `RESULTINFILE` large results, dead-worker cleanup, and ticker election have no dedicated tests.
- `JobGraph.validate` with no dependency rows is untested.
- `gluon/contrib/redis_scheduler.py` has no test (`test_redis` does not import it).
- `pydal/tools/scheduler.py` is not exercised by web2py.

## Open questions

1. Does the `limit` float (e.g. `50.0`) passed to `limitby` (`:1559`, `:1578-1580`) work on all adapters? **[Unverified]**
2. Is the worker selection in `assign_tasks` (`:1620-1626`) meant to pick the least-loaded worker? It compares each count with the *previous* worker's count, not with a running minimum.
3. Does `pydal`'s `validate_and_insert` validate default values (for example `status=QUEUED`) or only provided fields? This decides whether `queue_task(status=ASSIGNED)` is rejected. **[Unverified]**
4. Is the heartbeat thread's separate `DAL` safe with SQLite file locking under load (commits from two connections in one process)? **[Unverified]**

## Discrepancies with the technical reference

| Reference (§13) | Source |
|---|---|
| Lifecycle `QUEUED → ASSIGNED → RUNNING → COMPLETED/FAILED/TIMEOUT/EXPIRED` | Also `STOPPED`. Runs map `STOPPED` → task `FAILED`. Failed tasks may return to `QUEUED` (retry). Repeating tasks return to `QUEUED`. `ASSIGNED` is **not** in the field's `IS_IN_SET` (`:609`, `:902-907`) |
| `Scheduler(db, tasks=dict(...))` | Also works **without** `tasks`: any callable in the model env is runnable (`:526-536`) |
| Workers run "outside the web server" | Also inside it with `-X` (thread + processes, `widget.py:834-837`) and from the Tk GUI |
| Not mentioned | Per-task `multiprocessing.Process`, heartbeat thread with its own DAL, ticker election, `JobGraph`, cron lines, broadcast, `use_spawn`, `immediate` |

## Findings from static reading

- **[Suspected issue]** `stop_task` uses `integer_types` (`:1853`), which is not defined or imported in `scheduler.py` (imports at `:13-49`). Any call raises `NameError`.
- **[Suspected issue]** `set_worker_status`: `exclusion = exclude and exclude.append(action) or [action]` (`:1669`). `list.append` returns `None`, so `exclusion` is always `[action]`. The `exclude` lists passed by `disable/resume/terminate` (for example `[DISABLED, KILL, TERMINATE]`) are ignored, and `disable()` may overwrite `KILL`/`TERMINATE`.
- **[Suspected issue]** `disable/resume/terminate/kill` accept `worker_name` but do not pass it to `set_worker_status` (`:1682-1716`).
- **[Suspected issue]** `queue_task` with `cronline` and no `start_time` passes the bound method `self.now` (not called) to `CronParser` (`:1757`). The resulting exception is swallowed (`:1760-1761`), so `next_run_time` falls back to the field default.
- **[Suspected issue]** Broadcast copies omit `vars`, `timeout`, `period` and `stop_time` (`:1589-1601`). A broadcast task with `period=0` and no `cronline` calls `CronParser(None, ...)` (`:1602-1612`).
- **[Suspected issue]** `JobGraph.validate` on a job with no dependency rows raises in `reduce(set.union, [])` (`:211`). The exception is caught, which rolls back the caller's transaction and returns `None`, as if a cycle existed.
- **[Suspected issue]** `TASK_STATUS` lacks `ASSIGNED`. Internal transitions use `update()`/`insert()` without validation, so the worker is not affected. But forms that expose `status` (appadmin sets `ignore_rw = True`, `applications/*/controllers/appadmin.py:52`) would reject editing an `ASSIGNED` task.
- **[Suspected issue]** `gluon/contrib/redis_scheduler.py:22` imports `_decode_dict` from `gluon.scheduler`, which defines no such name. Importing the module would fail.
- **[Suspected issue]** `main()` calls `builtins.__import__(..., -1)` (`:1981`). A negative `level` is invalid on Python 3.
- **[Current]** Task selection by name from the model environment means that write access to `scheduler_task` gives the ability to invoke any model-level callable with JSON arguments. Treat the table as a code-invocation interface.

## Modernization considerations (optional)

- Before any change, write characterization tests for `set_worker_status`, `stop_task`, broadcast, and `JobGraph.validate` with empty deps. The runner tests spawn `web2py.py -K` subprocesses, so they are slow and platform-sensitive.
- Consider adding `ASSIGNED` to the validator only after confirming appadmin/form behaviour.
- The executor re-running models per task is expensive. Any change must preserve `current`, `W2P_TASK` and `request.is_scheduler` semantics.
