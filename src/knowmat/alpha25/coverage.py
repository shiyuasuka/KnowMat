"""Lossless task coverage ledger for alpha25 extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal


TaskState = Literal[
    "planned", "running", "succeeded", "cached", "split", "failed", "merged"
]
_TERMINAL_SUCCESS = {"succeeded", "cached", "merged"}


@dataclass
class CoverageRecord:
    task_id: str
    unit_id: str
    axis: str
    state: TaskState = "planned"
    parent_task_id: str | None = None
    child_task_ids: list[str] = field(default_factory=list)
    attempts: int = 0
    accepted_facts: int = 0
    rejected_facts: int = 0
    error: str | None = None
    elapsed_seconds: float | None = None
    provider_queue_seconds: float | None = None
    provider_call_seconds: float | None = None
    updated_at: str = field(default_factory=lambda: _now())

    @property
    def is_leaf(self) -> bool:
        return not self.child_task_ids


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IncompleteCoverageError(RuntimeError):
    pass


class CoverageLedger:
    def __init__(self) -> None:
        self._records: dict[str, CoverageRecord] = {}

    @property
    def records(self) -> dict[str, CoverageRecord]:
        return dict(self._records)

    def register(
        self,
        task_id: str,
        *,
        unit_id: str,
        axis: str,
        parent_task_id: str | None = None,
    ) -> CoverageRecord:
        if task_id in self._records:
            raise ValueError(f"Duplicate coverage task: {task_id}")
        if parent_task_id is not None and parent_task_id not in self._records:
            raise ValueError(f"Unknown parent coverage task: {parent_task_id}")
        record = CoverageRecord(
            task_id=task_id,
            unit_id=unit_id,
            axis=axis,
            parent_task_id=parent_task_id,
        )
        self._records[task_id] = record
        if parent_task_id is not None:
            self._records[parent_task_id].child_task_ids.append(task_id)
        return record

    def start(self, task_id: str) -> None:
        record = self._require(task_id)
        if record.state not in {"planned", "running"}:
            raise ValueError(f"Cannot start task {task_id} from state {record.state}")
        record.state = "running"
        record.attempts += 1
        record.updated_at = _now()

    def succeed(
        self,
        task_id: str,
        *,
        accepted_facts: int,
        rejected_facts: int = 0,
        elapsed_seconds: float | None = None,
        provider_queue_seconds: float | None = None,
        provider_call_seconds: float | None = None,
        cached: bool = False,
    ) -> None:
        record = self._require(task_id)
        if record.state not in {"planned", "running"}:
            raise ValueError(f"Cannot complete task {task_id} from state {record.state}")
        record.state = "cached" if cached else "succeeded"
        record.accepted_facts = accepted_facts
        record.rejected_facts = rejected_facts
        record.elapsed_seconds = elapsed_seconds
        record.provider_queue_seconds = provider_queue_seconds
        record.provider_call_seconds = provider_call_seconds
        record.error = None
        record.updated_at = _now()

    def fail(
        self,
        task_id: str,
        error: str,
        *,
        accepted_facts: int = 0,
        rejected_facts: int = 0,
    ) -> None:
        record = self._require(task_id)
        if record.state not in {"planned", "running"}:
            raise ValueError(f"Cannot fail task {task_id} from state {record.state}")
        record.state = "failed"
        record.error = str(error)
        record.accepted_facts = accepted_facts
        record.rejected_facts = rejected_facts
        record.updated_at = _now()

    def mark_split(self, task_id: str) -> None:
        record = self._require(task_id)
        if record.state != "failed":
            raise ValueError(f"Only a failed task can split: {task_id}")
        if not record.child_task_ids:
            raise ValueError(f"Split task has no registered children: {task_id}")
        record.state = "split"
        record.updated_at = _now()

    def mark_merged(self, task_id: str) -> None:
        record = self._require(task_id)
        if record.state not in _TERMINAL_SUCCESS:
            raise ValueError(f"Cannot merge task {task_id} from state {record.state}")
        record.state = "merged"
        record.updated_at = _now()

    def incomplete_leaves(self) -> list[CoverageRecord]:
        return [
            record
            for record in self._records.values()
            if record.is_leaf and record.state not in _TERMINAL_SUCCESS
        ]

    def assert_complete(self) -> None:
        incomplete = self.incomplete_leaves()
        if incomplete:
            detail = ", ".join(f"{row.task_id}:{row.state}" for row in incomplete)
            raise IncompleteCoverageError(f"incomplete_alpha25_task_coverage: {detail}")

    def summary(self) -> dict[str, Any]:
        states: dict[str, int] = {}
        for record in self._records.values():
            states[record.state] = states.get(record.state, 0) + 1
        return {
            "complete": not self.incomplete_leaves(),
            "task_count": len(self._records),
            "leaf_count": sum(record.is_leaf for record in self._records.values()),
            "states": states,
            "accepted_facts": sum(row.accepted_facts for row in self._records.values()),
            "rejected_facts": sum(row.rejected_facts for row in self._records.values()),
            "records": [asdict(row) for row in self._records.values()],
        }

    def register_many(self, tasks: Iterable[Any]) -> None:
        for task in tasks:
            self.register(
                task.task_id,
                unit_id=task.unit_id,
                axis=task.axis,
                parent_task_id=getattr(task, "parent_task_id", None),
            )

    def _require(self, task_id: str) -> CoverageRecord:
        try:
            return self._records[task_id]
        except KeyError:
            raise KeyError(f"Unknown coverage task: {task_id}") from None
