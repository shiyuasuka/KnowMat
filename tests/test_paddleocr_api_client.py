from __future__ import annotations

from pathlib import Path

import pytest
import requests

from knowmat.pdf.paddleocr_api_client import (
    PaddleOCRAPIClient,
    PaddleOCRAPIError,
)


class _Response:
    def __init__(self, status_code: int, body: str = "", payload: dict | None = None):
        self.status_code = status_code
        self.text = body
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


def test_submit_retries_queue_full_and_reopens_pdf(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"fresh-pdf")
    responses = iter(
        [
            _Response(400, '{"code":10010,"msg":"任务提交队列已满，请稍后重试"}'),
            _Response(200, payload={"data": {"jobId": "job-2"}}),
        ]
    )
    uploaded: list[bytes] = []
    sleeps: list[float] = []

    def fake_post(*args, **kwargs):
        uploaded.append(kwargs["files"]["file"][1].read())
        return next(responses)

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr("knowmat.pdf.paddleocr_api_client.time.sleep", sleeps.append)
    client = PaddleOCRAPIClient(
        "token", submit_max_attempts=2, retry_base_seconds=0.25
    )

    assert client.submit_job(pdf) == "job-2"
    assert uploaded == [b"fresh-pdf", b"fresh-pdf"]
    assert sleeps == [0.25]


def test_submit_does_not_retry_authentication_error(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Response(401, "invalid token")

    monkeypatch.setattr(requests, "post", fake_post)
    client = PaddleOCRAPIClient("token", submit_max_attempts=6, retry_base_seconds=0)

    with pytest.raises(PaddleOCRAPIError, match="HTTP 401"):
        client.submit_job(pdf)
    assert calls == 1


def test_poll_keeps_same_job_after_transient_server_error(monkeypatch):
    responses = iter(
        [
            _Response(503, "temporarily unavailable"),
            _Response(200, payload={"data": {"state": "done", "resultUrl": {}}}),
        ]
    )
    urls: list[str] = []

    def fake_get(url, **kwargs):
        urls.append(url)
        return next(responses)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("knowmat.pdf.paddleocr_api_client.time.sleep", lambda _: None)
    client = PaddleOCRAPIClient("token", retry_base_seconds=0)

    assert client.poll_job("job-1", poll_interval=0)["state"] == "done"
    assert urls == [f"{client.base_url}/job-1", f"{client.base_url}/job-1"]


def test_upload_resubmits_job_that_failed_with_server_500(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    client = PaddleOCRAPIClient(
        "token", job_max_attempts=2, retry_base_seconds=0
    )
    submitted: list[str] = []
    poll_results = iter(
        [
            PaddleOCRAPIError(
                "PaddleOCR job failed: OCR服务请求失败，状态码 500",
                status_code=500,
            ),
            {"state": "done", "resultUrl": {}},
        ]
    )

    def fake_submit(*args, **kwargs):
        job_id = f"job-{len(submitted) + 1}"
        submitted.append(job_id)
        return job_id

    def fake_poll(*args, **kwargs):
        result = next(poll_results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(client, "submit_job", fake_submit)
    monkeypatch.setattr(client, "poll_job", fake_poll)

    assert client.upload_and_parse(pdf)["state"] == "done"
    assert submitted == ["job-1", "job-2"]
