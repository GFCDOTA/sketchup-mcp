"""Bootstrap the CubiCasa5K DL oracle: clone repo + fetch pretrained weights.

This script is dev-time setup only. It is NEVER imported by `main.py` or any
service in the pipeline core (CLAUDE.md invariants Section 6 / vendor README).

Steps (idempotent):
  1. git clone https://github.com/CubiCasa/CubiCasa5k -> vendor/CubiCasa5k/repo/
  2. gdown <Drive ID> -O vendor/CubiCasa5k/weights/model_best_val_loss_var.pkl
  3. Sanity-check the weights file size (50-200 MB).
  4. Compute and print SHA256 (CubiCasa does not publish a canonical hash;
     the first successful run is your pinning event - record this value).

Usage:
    python scripts/oracle/cubicasa_download.py
    python scripts/oracle/cubicasa_download.py --force  # re-download

Reference: vendor/CubiCasa5k/README.md sections 1, 3, 4, 5.
License of downloaded artifacts: CC BY-NC 4.0 (non-commercial use only).
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENDOR_DIR = PROJECT_ROOT / "vendor" / "CubiCasa5k"
REPO_DIR = VENDOR_DIR / "repo"
WEIGHTS_DIR = VENDOR_DIR / "weights"
WEIGHTS_PATH = WEIGHTS_DIR / "model_best_val_loss_var.pkl"

REPO_URL = "https://github.com/CubiCasa/CubiCasa5k.git"
GDRIVE_ID = "1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK"

MIN_WEIGHTS_BYTES = 50 * 1024 * 1024   # 50 MB
MAX_WEIGHTS_BYTES = 200 * 1024 * 1024  # 200 MB


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _repo_is_populated(repo_dir: Path) -> bool:
    """A clone is considered done when floortrans/__init__.py exists."""
    return (repo_dir / "floortrans" / "__init__.py").is_file()


def clone_repo(force: bool) -> None:
    if not _has("git"):
        raise SystemExit(
            "[setup] ERROR: 'git' executable not found on PATH. Install Git "
            "and re-run: https://git-scm.com/downloads"
        )

    if _repo_is_populated(REPO_DIR) and not force:
        print(f"[setup] repo already cloned at {REPO_DIR} - skipping")
        return

    if force and REPO_DIR.exists():
        print(f"[setup] --force: removing {REPO_DIR}")
        shutil.rmtree(REPO_DIR, ignore_errors=True)

    REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
    print(f"[setup] cloning {REPO_URL} -> {REPO_DIR}")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", REPO_URL, str(REPO_DIR)],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"[setup] ERROR: git clone failed (exit {exc.returncode}). "
            "Check network access and try again."
        ) from exc

    if not _repo_is_populated(REPO_DIR):
        raise SystemExit(
            f"[setup] ERROR: clone completed but {REPO_DIR}/floortrans is "
            "missing. The upstream repo layout may have changed."
        )


def download_weights(force: bool) -> None:
    if WEIGHTS_PATH.exists() and not force:
        size = WEIGHTS_PATH.stat().st_size
        if MIN_WEIGHTS_BYTES <= size <= MAX_WEIGHTS_BYTES:
            print(f"[setup] weights already at {WEIGHTS_PATH} ({size:,} bytes) - skipping")
            return
        print(
            f"[setup] WARNING: existing weights file size {size:,} bytes "
            f"is outside [{MIN_WEIGHTS_BYTES:,}, {MAX_WEIGHTS_BYTES:,}] - re-downloading"
        )
        WEIGHTS_PATH.unlink()

    if force and WEIGHTS_PATH.exists():
        print(f"[setup] --force: removing {WEIGHTS_PATH}")
        WEIGHTS_PATH.unlink()

    if not _has("gdown"):
        raise SystemExit(
            "[setup] ERROR: 'gdown' not found on PATH. Install it with "
            "'pip install gdown' (or 'pip install --user gdown')."
        )

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[setup] downloading weights (~96 MB) via gdown id={GDRIVE_ID}")
    try:
        subprocess.run(
            ["gdown", "--id", GDRIVE_ID, "-O", str(WEIGHTS_PATH)],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"[setup] ERROR: gdown failed (exit {exc.returncode}). Google "
            "Drive sometimes rate-limits anonymous downloads of large files. "
            f"Open https://drive.google.com/uc?id={GDRIVE_ID} in a browser, "
            f"download manually, and place the file at {WEIGHTS_PATH}."
        ) from exc

    if not WEIGHTS_PATH.exists():
        raise SystemExit(f"[setup] ERROR: gdown reported success but {WEIGHTS_PATH} is missing.")

    size = WEIGHTS_PATH.stat().st_size
    if size < MIN_WEIGHTS_BYTES or size > MAX_WEIGHTS_BYTES:
        raise SystemExit(
            f"[setup] ERROR: downloaded weights size {size:,} bytes is "
            f"outside the plausible range [{MIN_WEIGHTS_BYTES:,}, "
            f"{MAX_WEIGHTS_BYTES:,}]. The download likely failed or returned "
            "the Google Drive 'quota exceeded' HTML page. Delete the file "
            "and retry, or download manually via browser."
        )
    print(f"[setup] downloaded {size:,} bytes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download / re-clone even if files already exist.",
    )
    args = parser.parse_args(argv)

    print(f"[setup] project root: {PROJECT_ROOT}")
    print(f"[setup] vendor dir:   {VENDOR_DIR}")

    clone_repo(args.force)
    download_weights(args.force)

    sha = _sha256(WEIGHTS_PATH)
    print()
    print(f"[setup] weights path:   {WEIGHTS_PATH}")
    print(f"[setup] weights size:   {WEIGHTS_PATH.stat().st_size:,} bytes")
    print(f"[setup] weights sha256: {sha}")
    print()
    print("[setup] CubiCasa5K does not publish a canonical SHA256 - record "
          "this value as your pin (vendor/CubiCasa5k/README.md section 5).")
    print("[setup] LICENSE: CC BY-NC 4.0 (non-commercial use only).")
    print("[setup] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
