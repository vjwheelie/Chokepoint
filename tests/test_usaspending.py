"""Downloader tests against a fake USAspending (httpx.MockTransport): no network access."""

import json
from datetime import date

import httpx
import pytest

from chokepoint.ingest import usaspending as us

ZIP_BYTES = b"PK\x03\x04 fake zip"


class FakeUSAspending:
    """Scripted USAspending. `statuses` are returned in order by download/status."""

    def __init__(self, statuses: list[dict | None]):
        self.statuses = list(statuses)
        self.calls: list[str] = []
        self.request_body: dict | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.path)
        if request.url.path.endswith("/download/transactions/"):
            self.request_body = json.loads(request.content)
            return httpx.Response(200, json={"file_name": "x.zip"})
        if request.url.path.endswith("/download/status"):
            status = self.statuses.pop(0)
            return httpx.Response(200, json=status if status is not None else {"detail": "?"})
        if request.url.host == "files.usaspending.gov":
            return httpx.Response(200, content=ZIP_BYTES)
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


FINISHED = {
    "status": "finished",
    "total_rows": 3,
    "file_url": "https://files.usaspending.gov/generated_downloads/x.zip",
}


def run(fake: FakeUSAspending, tmp_path, fy=2019, today=date(2026, 10, 22), **kw):
    return us.download_fy(
        fy, client=fake.client(), raw_dir=tmp_path, today=today, sleep=lambda s: None, **kw
    )


def test_downloads_and_writes_manifest(tmp_path):
    # None = a status body with no `status` key, which the real API returned once.
    fake = FakeUSAspending([None, {"status": "running", "total_rows": 0}, FINISHED])
    path = run(fake, tmp_path)

    assert path.read_bytes() == ZIP_BYTES
    manifest = us.read_manifest(tmp_path, 2019)
    assert manifest.total_rows == 3
    assert manifest.downloaded_on == "2026-10-22"
    assert not (tmp_path / "fy2019.zip.part").exists()

    filters = fake.request_body["filters"]
    assert filters["psc_codes"] == {"require": [["Product", "59"]]}
    assert filters["time_period"] == [{"start_date": "2018-10-01", "end_date": "2019-09-30"}]
    assert "federal_action_obligation" in fake.request_body["columns"]


def test_fresh_cache_makes_no_network_calls(tmp_path):
    run(FakeUSAspending([FINISHED]), tmp_path)
    second = FakeUSAspending([])
    run(second, tmp_path, today=date(2030, 1, 1))
    assert second.calls == []


def test_force_redownloads(tmp_path):
    run(FakeUSAspending([FINISHED]), tmp_path)
    again = FakeUSAspending([FINISHED])
    run(again, tmp_path, force=True)
    assert again.calls


def test_settling_fy_refreshes_after_a_week(tmp_path):
    run(FakeUSAspending([FINISHED]), tmp_path, fy=2026, today=date(2026, 10, 22))

    within_week = FakeUSAspending([])
    run(within_week, tmp_path, fy=2026, today=date(2026, 10, 29))
    assert within_week.calls == []

    after_week = FakeUSAspending([FINISHED])
    run(after_week, tmp_path, fy=2026, today=date(2026, 10, 30))
    assert after_week.calls


def test_settling_cache_refetched_once_fy_becomes_final(tmp_path):
    # Cached on 2027-01-25 (still settling); by 2027-01-30 FY2026 is final -> fetch final data.
    run(FakeUSAspending([FINISHED]), tmp_path, fy=2026, today=date(2027, 1, 25))
    final = FakeUSAspending([FINISHED])
    run(final, tmp_path, fy=2026, today=date(2027, 1, 30))
    assert final.calls
    # ...and after that it is never fetched again.
    later = FakeUSAspending([])
    run(later, tmp_path, fy=2026, today=date(2028, 1, 1))
    assert later.calls == []


def test_failed_download_raises_and_caches_nothing(tmp_path):
    fake = FakeUSAspending([{"status": "failed", "message": "boom"}])
    with pytest.raises(RuntimeError, match="boom"):
        run(fake, tmp_path)
    assert us.read_manifest(tmp_path, 2019) is None


def test_poll_timeout(tmp_path):
    fake = FakeUSAspending([{"status": "running"}] * 5)
    with pytest.raises(TimeoutError):
        run(fake, tmp_path, poll_interval=10, timeout_s=30)
