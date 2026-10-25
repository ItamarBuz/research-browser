"""Pin every catalog entry to an exact Hugging Face revision with file sizes and SHA-256.

Usage (from engine/):
    uv run python scripts/pin_models.py            # pin new entries, keep existing pins
    uv run python scripts/pin_models.py --update   # re-resolve every entry to its latest revision

It also checks each declared license against the Hugging Face model card (of
`license_source` when set), so an entry cannot claim a license its upstream does not have.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from rb_engine.domain.catalog import ALLOWED_LICENSES, HF_BASE_URL
from rb_engine.runtime.catalog import LockedEntry, LockedFile, SpecEntry, parse_lock, parse_spec

CATALOG_DIR = Path(__file__).resolve().parents[1] / "src" / "rb_engine" / "catalog"
SPEC_PATH = CATALOG_DIR / "models.toml"
LOCK_PATH = CATALOG_DIR / "models.lock.json"


def _get_json(client: httpx.Client, url: str) -> Any:  # noqa: ANN401 - raw JSON
    for attempt in range(4):
        response = client.get(url)
        if response.status_code == 429 and attempt < 3:
            time.sleep(5 * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"rate limited: {url}")


def _check_license(client: httpx.Client, entry: SpecEntry) -> None:
    if entry.license not in ALLOWED_LICENSES:
        raise SystemExit(f"{entry.id}: license {entry.license!r} is not in the allowlist")
    source = entry.license_source or entry.repo
    card = _get_json(client, f"{HF_BASE_URL}/api/models/{source}").get("cardData") or {}
    upstream = card.get("license")
    if upstream != entry.license:
        raise SystemExit(f"{entry.id}: declares {entry.license!r} but {source} says {upstream!r}")


def _sha256_of_url(client: httpx.Client, url: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with client.stream("GET", url) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _pin(client: httpx.Client, entry: SpecEntry, revision: str | None) -> LockedEntry:
    if revision is None:
        revision = _get_json(client, f"{HF_BASE_URL}/api/models/{entry.repo}")["sha"]
    tree = _get_json(
        client, f"{HF_BASE_URL}/api/models/{entry.repo}/tree/{revision}?recursive=true"
    )
    by_path = {item["path"]: item for item in tree if item.get("type") == "file"}
    files: dict[str, LockedFile] = {}
    for path in entry.files:
        item = by_path.get(path)
        if item is None:
            raise SystemExit(f"{entry.id}: {path} not found in {entry.repo}@{revision}")
        lfs = item.get("lfs")
        if lfs:  # large files: Hugging Face stores the SHA-256 as the LFS object id
            files[path] = LockedFile(sha256=lfs["oid"], size_bytes=lfs["size"])
        else:  # small git files only expose a git blob id, so hash the content ourselves
            url = f"{HF_BASE_URL}/{entry.repo}/resolve/{revision}/{path}"
            sha, size = _sha256_of_url(client, url)
            files[path] = LockedFile(sha256=sha, size_bytes=size)
    return LockedEntry(revision=revision, files=files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="re-resolve to latest revisions")
    args = parser.parse_args()

    spec = parse_spec(SPEC_PATH.read_text(encoding="utf-8"))
    old_lock = parse_lock(LOCK_PATH.read_text(encoding="utf-8")) if LOCK_PATH.exists() else {}
    new_lock: dict[str, LockedEntry] = {}

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        for entry in spec:
            _check_license(client, entry)
            previous = old_lock.get(entry.id)
            keep = previous is not None and not args.update
            revision = previous.revision if keep and previous else None
            new_lock[entry.id] = _pin(client, entry, revision)
            total_mb = sum(f.size_bytes for f in new_lock[entry.id].files.values()) / 1e6
            print(f"{entry.id}: {new_lock[entry.id].revision[:12]} ({total_mb:,.0f} MB)")

    payload = {k: v.model_dump() for k, v in sorted(new_lock.items())}
    LOCK_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {LOCK_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
