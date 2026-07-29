#!/usr/bin/env python3
"""
Download the published VizDOM synthetic benchmark into ``data/``.

Host-agnostic: point it at whatever you published the archive to.

    # Direct archive (Zenodo record file, GitHub Release asset, any HTTPS URL):
    python scripts/data_prep/download_data.py \
        --url "https://zenodo.org/records/<RECORD_ID>/files/vizdom-data.zip?download=1"

    # Hugging Face dataset repo (requires `pip install huggingface_hub`):
    python scripts/data_prep/download_data.py --hf "your-user/vizdom-data"

The archive is expected to contain the dataset's top-level folders (``synthetic/``,
``synthetic_camera/``, ...); it is extracted into ``data/`` so you end up with
``data/synthetic/{train,test,yolo}`` etc. Set the URL once via the
``VIZDOM_DATA_URL`` environment variable to omit --url.
"""

from __future__ import annotations

import argparse
import os
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    with urlopen(url) as resp, open(dest, "wb") as out:  # noqa: S310 (trusted URL)
        total = int(resp.headers.get("Content-Length", 0))
        read = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            read += len(chunk)
            if total:
                pct = 100 * read / total
                print(f"\r  {read/1e6:6.1f} / {total/1e6:.1f} MB ({pct:4.1f}%)",
                      end="", flush=True)
        print()


def _extract(archive: Path, into: Path) -> None:
    print(f"Extracting {archive.name} -> {into}")
    if archive.suffix == ".zip" or zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(into)
    elif tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tf:
            tf.extractall(into)  # noqa: S202 (trusted archive)
    else:
        raise SystemExit(f"Unrecognised archive format: {archive}")


def from_url(url: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".zip" if url.lower().endswith(".zip") else ".tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / f"vizdom-data{suffix}"
        _download(url, archive)
        _extract(archive, DATA_DIR)
    print(f"Done. See {DATA_DIR / 'synthetic'}")


def from_hf(repo_id: str) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise SystemExit("Install huggingface_hub first: pip install huggingface_hub")
    print(f"Downloading HF dataset {repo_id}")
    local = snapshot_download(repo_id=repo_id, repo_type="dataset")
    print(f"Downloaded to {local}")
    print("Copy/symlink its 'synthetic/' folder into data/ if not already there.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("VIZDOM_DATA_URL"),
                    help="direct HTTPS URL to a .zip/.tar.gz archive "
                         "(or set VIZDOM_DATA_URL)")
    ap.add_argument("--hf", help="Hugging Face dataset repo id, e.g. user/vizdom-synthetic")
    args = ap.parse_args(argv)

    if args.hf:
        from_hf(args.hf)
    elif args.url:
        from_url(args.url)
    else:
        ap.print_help()
        print("\nERROR: provide --url or --hf (or set VIZDOM_DATA_URL).", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
