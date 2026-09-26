"""
B7, B8, B9 - Scheduler API defects that need no worker process.

Source: gluon/scheduler.py JobGraph.validate (185-232), Scheduler
set_worker_status (1651-1682), disable/resume/terminate/kill
(1684-1716), stop_task (1828-1853).
Docs: docs/architecture/10-scheduler.md.

A Scheduler is instantiated (tables are defined) but never started, so no
thread or process is created.
"""

import unittest

from gluon.dal import DAL
from gluon.scheduler import (ACTIVE, DISABLED, KILL, TERMINATE, JobGraph,
                             Scheduler)


class SchedulerTestCase(unittest.TestCase):
    def setUp(self):
        self.db = DAL("sqlite:memory")
        self.scheduler = Scheduler(self.db, migrate=True)

    def tearDown(self):
        self.db.close()

    def add_worker(self, name, status, group="main"):
        return self.db.scheduler_worker.insert(
            worker_name=name, status=status, group_names=[group]
        )

    def status_of(self, name):
        row = self.db(self.db.scheduler_worker.worker_name == name).select().first()
        return row.status


class TestStopTask(SchedulerTestCase):
    """B7: stop_task()."""

    def test_current_stop_task_by_id_raises_nameerror(self):
        """PINS-DEFECT: B7. integer_types is not defined in gluon.scheduler."""
        with self.assertRaises(NameError):
            self.scheduler.stop_task(1)

    def test_current_stop_task_by_uuid_also_raises_nameerror(self):
        """PINS-DEFECT: B7. The isinstance(ref, integer_types) check runs first."""
        with self.assertRaises(NameError):
            self.scheduler.stop_task("some-uuid")


class TestWorkerStatus(SchedulerTestCase):
    """B8: set_worker_status() exclusion lists and worker_name."""

    def test_current_disable_overwrites_killed_worker(self):
        """PINS-DEFECT: B8-exclude. exclude.append() returns None."""
        self.add_worker("w1", KILL)
        self.scheduler.disable(group_names=["main"])
        self.assertEqual(self.status_of("w1"), DISABLED)

    def test_current_resume_overwrites_terminating_worker(self):
        """PINS-DEFECT: B8-exclude."""
        self.add_worker("w1", TERMINATE)
        self.scheduler.resume(group_names=["main"])
        self.assertEqual(self.status_of("w1"), ACTIVE)

    def test_current_disable_ignores_worker_name(self):
        """PINS-DEFECT: B8-worker-name. Every worker in the group is changed."""
        self.add_worker("w1", ACTIVE)
        self.add_worker("w2", ACTIVE)
        self.scheduler.disable(group_names=["main"], worker_name="w1")
        self.assertEqual(self.status_of("w1"), DISABLED)
        self.assertEqual(self.status_of("w2"), DISABLED)

    def test_other_groups_are_untouched(self):
        self.add_worker("w1", ACTIVE, group="other")
        self.scheduler.disable(group_names=["main"])
        self.assertEqual(self.status_of("w1"), ACTIVE)


class TestJobGraphValidate(SchedulerTestCase):
    """B9: JobGraph.validate()."""

    def add_tasks(self, n):
        """scheduler_task_deps references scheduler_task, so real rows are needed."""
        return [
            self.db.scheduler_task.insert(function_name="f", task_name="t%d" % i)
            for i in range(n)
        ]

    def test_linear_dependencies_are_ordered(self):
        t1, t2, t3 = self.add_tasks(3)
        graph = JobGraph(self.db, "job")
        graph.add_deps(t1, t2)
        graph.add_deps(t2, t3)
        self.assertEqual(graph.validate("job"), [{t3}, {t2}, {t1}])

    def test_cycle_returns_none(self):
        t1, t2 = self.add_tasks(2)
        graph = JobGraph(self.db, "job")
        graph.add_deps(t1, t2)
        graph.add_deps(t2, t1)
        self.assertIsNone(graph.validate("job"))

    def test_current_job_without_dependencies_returns_none_like_a_cycle(self):
        """PINS-DEFECT: B9. reduce(set.union, []) raises and is swallowed."""
        graph = JobGraph(self.db, "empty")
        self.assertIsNone(graph.validate("empty"))


if __name__ == "__main__":
    unittest.main()
