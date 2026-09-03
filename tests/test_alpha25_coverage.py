import pytest

from knowmat.alpha25.coverage import CoverageLedger, IncompleteCoverageError
from knowmat.alpha25.planner import build_evidence_units, plan_axis_tasks, split_task_once


def _task():
    text = "Yield strength was 900 MPa.\n\n" * 80
    return plan_axis_tasks(build_evidence_units(text, max_prose_chars=6000))[0]


def test_coverage_requires_every_leaf_to_succeed():
    task = _task()
    ledger = CoverageLedger()
    ledger.register_many([task])
    ledger.start(task.task_id)
    ledger.fail(task.task_id, "output_truncated")

    with pytest.raises(IncompleteCoverageError, match="incomplete_alpha25_task_coverage"):
        ledger.assert_complete()


def test_split_parent_is_complete_only_when_all_children_succeed():
    task = _task()
    children = split_task_once(task)
    ledger = CoverageLedger()
    ledger.register_many([task])
    ledger.start(task.task_id)
    ledger.fail(task.task_id, "invalid_json")
    ledger.register_many(children)
    ledger.mark_split(task.task_id)
    ledger.succeed(children[0].task_id, accepted_facts=2)

    with pytest.raises(IncompleteCoverageError):
        ledger.assert_complete()

    ledger.succeed(children[1].task_id, accepted_facts=1, cached=True)
    ledger.assert_complete()
    assert ledger.summary()["accepted_facts"] == 3
