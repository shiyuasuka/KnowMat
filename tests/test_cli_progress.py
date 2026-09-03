import time

import knowmat.__main__ as cli


def test_elapsed_progress_returns_immediately_when_worker_finishes(monkeypatch):
    monkeypatch.setattr(cli, "_PROGRESS_INTERVAL_SEC", 0.5)
    started = time.monotonic()

    result = cli._run_with_elapsed_progress("LLM", "paper.md", lambda: "done")

    assert result == "done"
    assert time.monotonic() - started < 0.2


def test_alpha25_shared_pool_keeps_requested_file_admission(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_GLOBAL_CONCURRENCY", "12")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_WORKERS", "6")
    monkeypatch.delenv("KNOWMAT2_ALPHA25_SHARED_TASK_POOL", raising=False)
    monkeypatch.delenv("KNOWMAT2_ALPHA25_AUTO_BALANCE_FILE_WORKERS", raising=False)

    workers, note = cli._alpha25_file_worker_budget(6)

    assert workers == 6
    assert note is None


def test_alpha25_shared_pool_caps_file_admission_at_global_limit(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_GLOBAL_CONCURRENCY", "4")
    monkeypatch.delenv("KNOWMAT2_ALPHA25_SHARED_TASK_POOL", raising=False)

    workers, note = cli._alpha25_file_worker_budget(9)

    assert workers == 4
    assert note is not None
    assert "9 -> 4" in note


def test_alpha25_file_worker_balance_does_not_increase_requested_width(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_GLOBAL_CONCURRENCY", "12")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_WORKERS", "6")

    workers, note = cli._alpha25_file_worker_budget(1)

    assert workers == 1
    assert note is None


def test_alpha25_file_worker_balance_can_be_explicitly_disabled(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_GLOBAL_CONCURRENCY", "12")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_WORKERS", "6")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_AUTO_BALANCE_FILE_WORKERS", "0")

    workers, note = cli._alpha25_file_worker_budget(6)

    assert workers == 6
    assert note is None


def test_alpha25_file_workers_use_effective_inner_width(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_GLOBAL_CONCURRENCY", "4")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_WORKERS", "12")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_SHARED_TASK_POOL", "0")
    monkeypatch.delenv("KNOWMAT2_ALPHA25_AUTO_BALANCE_FILE_WORKERS", raising=False)

    workers, note = cli._alpha25_file_worker_budget(3)

    assert workers == 1
    assert note is not None
