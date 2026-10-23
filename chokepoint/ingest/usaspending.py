"""Download FSG 59 DoD prime transactions from USAspending, one cached zip per fiscal year (D-002).

The download/transactions endpoint is asynchronous: POST a request, poll download/status until
it is finished, then fetch the zip. Each FY is cached as `fy{N}.zip` plus a `fy{N}.manifest.json`
recording what was requested and when, so re-runs make no network calls when the cache is fresh.

Run: uv run python -m chokepoint.ingest.usaspending [--force]
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import httpx

from chokepoint import config
from chokepoint.ingest.parse import fiscal_year_bounds, is_fiscal_year_final

log = logging.getLogger(__name__)

MAX_AGE_DAYS_WHILE_SETTLING = 7


@dataclass
class Manifest:
    fy: int
    file_name: str
    total_rows: int | None
    downloaded_on: str  # ISO date
    sha256: str
    request: dict


def build_request(fy: int) -> dict:
    start, end = fiscal_year_bounds(fy)
    return {
        "filters": {
            "agencies": [config.AWARDING_AGENCY],
            "psc_codes": {"require": config.PSC_FILTER},
            "time_period": [{"start_date": start.isoformat(), "end_date": end.isoformat()}],
            "award_type_codes": config.CONTRACT_AWARD_TYPES,
        },
        "file_format": "csv",
        "columns": config.TRANSACTION_COLUMNS,
    }


def zip_path(raw_dir: Path, fy: int) -> Path:
    return raw_dir / f"fy{fy}.zip"


def manifest_path(raw_dir: Path, fy: int) -> Path:
    return raw_dir / f"fy{fy}.manifest.json"


def read_manifest(raw_dir: Path, fy: int) -> Manifest | None:
    path = manifest_path(raw_dir, fy)
    if not path.exists() or not zip_path(raw_dir, fy).exists():
        return None
    return Manifest(**json.loads(path.read_text()))


def is_cache_fresh(manifest: Manifest | None, today: date) -> bool:
    """A cached FY is reusable if it was downloaded after the FY became final (D-012),
    or, while the FY is still settling, if it is less than a week old."""
    if manifest is None:
        return False
    downloaded = date.fromisoformat(manifest.downloaded_on)
    if is_fiscal_year_final(manifest.fy, downloaded):
        return True
    if is_fiscal_year_final(manifest.fy, today):
        return False  # cached while settling; the FY has since become final, so fetch once more
    return (today - downloaded).days <= MAX_AGE_DAYS_WHILE_SETTLING


def _wait_for_file(
    client: httpx.Client,
    file_name: str,
    poll_interval: float,
    timeout_s: float,
    sleep: Callable[[float], None],
) -> dict:
    status_url = f"{config.USASPENDING_API}/download/status"
    waited = 0.0
    while waited <= timeout_s:
        resp = client.get(status_url, params={"file_name": file_name})
        status = resp.json() if resp.status_code == 200 else {}
        # The status endpoint occasionally returns a body without `status`; treat it as running.
        state = status.get("status")
        if state == "finished":
            return status
        if state == "failed":
            raise RuntimeError(f"USAspending download {file_name} failed: {status.get('message')}")
        log.info("%s: %s, %s rows so far", file_name, state or "pending", status.get("total_rows"))
        sleep(poll_interval)
        waited += poll_interval
    raise TimeoutError(f"USAspending download {file_name} not ready after {timeout_s:.0f}s")


def download_fy(
    fy: int,
    *,
    client: httpx.Client,
    raw_dir: Path = config.RAW_DIR,
    today: date | None = None,
    force: bool = False,
    poll_interval: float = 10,
    timeout_s: float = 1800,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Return the path to the cached zip for `fy`, downloading it only if the cache is stale."""
    today = today or date.today()
    if not force and is_cache_fresh(read_manifest(raw_dir, fy), today):
        log.info("FY%d: cache fresh, skipping download", fy)
        return zip_path(raw_dir, fy)

    request = build_request(fy)
    resp = client.post(f"{config.USASPENDING_API}/download/transactions/", json=request)
    resp.raise_for_status()
    file_name = resp.json()["file_name"]
    status = _wait_for_file(client, file_name, poll_interval, timeout_s, sleep)

    content = client.get(status["file_url"]).raise_for_status().content
    raw_dir.mkdir(parents=True, exist_ok=True)
    # Write to a temp file then rename, so an interrupted run never leaves a half-written zip
    # that looks cached.
    part = zip_path(raw_dir, fy).with_suffix(".zip.part")
    part.write_bytes(content)
    part.replace(zip_path(raw_dir, fy))

    manifest = Manifest(
        fy=fy,
        file_name=file_name,
        total_rows=status.get("total_rows"),
        downloaded_on=today.isoformat(),
        sha256=hashlib.sha256(content).hexdigest(),
        request=request,
    )
    manifest_path(raw_dir, fy).write_text(json.dumps(asdict(manifest), indent=2))
    log.info("FY%d: downloaded %s rows", fy, manifest.total_rows)
    return zip_path(raw_dir, fy)


def download_all(force: bool = False) -> list[Path]:
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        return [
            download_fy(fy, client=client, force=force)
            for fy in range(config.FIRST_FY, config.LAST_FY + 1)
        ]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    for path in download_all(force=args.force):
        print(path)
