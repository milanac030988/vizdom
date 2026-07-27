"""
Set up Microsoft OmniParser as a detector backend for this project.

What it does
------------
1. Reports whether the extra Python deps OmniParser needs are present
   (ultralytics, supervision); optionally installs them with --install-deps.
2. Clones the OmniParser repo to third_party/OmniParser (so `util.utils`
   imports) unless it is already there or --skip-repo is given. The clone is
   pinned to a specific commit (REPO_COMMIT) for reproducible setups.
3. Downloads the v2 weights from Hugging Face into models/omniparser/ and
   renames icon_caption -> icon_caption_florence, matching the paths the
   Visual DOM Viewer auto-detects.

After running, `--detector omniparser` (CLI) and the "omniparser" dropdown
entry (Viewer) work without setting any environment variables, because both
default-detect these locations:
    models/omniparser/icon_detect/model.pt
    models/omniparser/icon_caption_florence/
    third_party/OmniParser            (as OMNIPARSER_ROOT)

Run with the SAME interpreter the app uses (the Viewer/dashboard use
D:\\Python\\python39\\python.exe):
    "D:\\Python\\python39\\python.exe" scripts/setup_omniparser.py
    "D:\\Python\\python39\\python.exe" scripts/setup_omniparser.py --install-deps

LICENSING
---------
OmniParser's icon_detect is AGPL-3.0 (via Ultralytics/YOLO); icon_caption is
MIT; the repo is CC-BY-4.0. This project is already on AGPL through its existing
Ultralytics dependency, so this adds no new licence class — but distributing or
network-serving the project while this backend is active carries AGPL
obligations. See docs/discussion/landscape-comparison-*.html section 9 and
docs/adr/015-pluggable-detector-backends.md.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HF_REPO = "microsoft/OmniParser-v2.0"
REPO_URL = "https://github.com/microsoft/OmniParser.git"

# Pin the exact OmniParser commit for reproducible setups (gives submodule-grade
# reproducibility without a submodule — see docs/adr/015-pluggable-detector-backends.md
# for why this project vendors via this script rather than a git submodule).
# This is the commit the patch_repo() block below is known to match. To bump:
# clone the new HEAD, confirm patch_repo() still applies, then update this SHA.
#   354021201345a96178360b28733573e27269f2de = "Merge PR #363 feat/yolov9-e-detector" (2026-07-19)
REPO_COMMIT = "354021201345a96178360b28733573e27269f2de"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEIGHTS_DIR = PROJECT_ROOT / "models" / "omniparser"
REPO_DIR = PROJECT_ROOT / "third_party" / "OmniParser"

# Deps OmniParser actually needs for our easyocr-driven use. We deliberately do
# NOT install paddlepaddle/paddleocr: OmniParser's util/utils.py imports and
# instantiates PaddleOCR at module top, but we run with use_paddleocr=False, and
# paddle drags in a protobuf that conflicts with the dashboard's streamlit. The
# repo is patched (see patch_repo) to make PaddleOCR lazy instead.
EXTRA_DEPS = ["ultralytics", "supervision"]


def check_deps() -> list:
    """Return the list of required-but-missing modules."""
    missing = []
    for mod in EXTRA_DEPS:
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    return missing


def install_deps(missing: list) -> None:
    print(f"Installing: {', '.join(missing)}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])


def clone_repo() -> None:
    if REPO_DIR.exists():
        print(f"[repo] already present: {REPO_DIR}")
        _report_commit()
        return
    REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
    print(f"[repo] cloning {REPO_URL} @ {REPO_COMMIT[:12]} -> {REPO_DIR}")
    _clone_at_commit()


def _clone_at_commit() -> None:
    """Clone OmniParser and check out the pinned commit (reproducible).

    Tries a bandwidth-friendly shallow fetch of just REPO_COMMIT; if the server
    rejects fetch-by-SHA, falls back to a full clone + checkout so the pinned
    commit is guaranteed present regardless of how far back it is.
    """
    try:
        subprocess.check_call(["git", "init", "--quiet", str(REPO_DIR)])
        subprocess.check_call(["git", "-C", str(REPO_DIR), "remote", "add", "origin", REPO_URL])
        subprocess.check_call(["git", "-C", str(REPO_DIR), "fetch", "--quiet",
                               "--depth", "1", "origin", REPO_COMMIT])
        subprocess.check_call(["git", "-C", str(REPO_DIR), "checkout", "--quiet", "FETCH_HEAD"])
    except subprocess.CalledProcessError:
        print("[repo] shallow fetch-by-commit failed; falling back to full clone")
        shutil.rmtree(REPO_DIR, ignore_errors=True)
        subprocess.check_call(["git", "clone", "--quiet", REPO_URL, str(REPO_DIR)])
        subprocess.check_call(["git", "-C", str(REPO_DIR), "checkout", "--quiet", REPO_COMMIT])


def _report_commit() -> None:
    """Warn if an existing clone is not at the pinned commit (patch may not match)."""
    try:
        head = subprocess.check_output(
            ["git", "-C", str(REPO_DIR), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return
    if head == REPO_COMMIT:
        print(f"[repo] at pinned commit {head[:12]}")
    else:
        print(f"[repo] WARNING: at {head[:12]}, pinned is {REPO_COMMIT[:12]}. "
              f"patch_repo() may not match. To get the pinned version, delete "
              f"{REPO_DIR} and re-run (the patch is re-applied after checkout).")


def patch_repo() -> None:
    """
    Make PaddleOCR lazy in the cloned OmniParser's util/utils.py.

    OmniParser imports and instantiates PaddleOCR at module top level, which
    forces a paddlepaddle dependency we don't want (protobuf conflict with the
    dashboard). We run with use_paddleocr=False, so defer it. Idempotent.
    """
    utils = REPO_DIR / "util" / "utils.py"
    if not utils.exists():
        print(f"[patch] skipped: {utils} not found")
        return

    text = utils.read_text(encoding="utf-8")
    if "_ensure_paddle_ocr" in text:
        print("[patch] util/utils.py already patched")
        return

    original = (
        "from paddleocr import PaddleOCR\n"
        "reader = easyocr.Reader(['en'])\n"
        "paddle_ocr = PaddleOCR(\n"
        "    lang='en',  # other lang also available\n"
        "    use_angle_cls=False,\n"
        "    use_gpu=False,  # using cuda will conflict with pytorch in the same process\n"
        "    show_log=False,\n"
        "    max_batch_size=1024,\n"
        "    use_dilation=True,  # improves accuracy\n"
        "    det_db_score_mode='slow',  # improves accuracy\n"
        "    rec_batch_num=1024)"
    )
    replacement = (
        "# PATCHED by setup_omniparser.py: make PaddleOCR optional/lazy.\n"
        "reader = easyocr.Reader(['en'])\n"
        "paddle_ocr = None\n\n"
        "def _ensure_paddle_ocr():\n"
        "    global paddle_ocr\n"
        "    if paddle_ocr is None:\n"
        "        from paddleocr import PaddleOCR\n"
        "        paddle_ocr = PaddleOCR(lang='en', use_angle_cls=False, use_gpu=False,\n"
        "            show_log=False, max_batch_size=1024, use_dilation=True,\n"
        "            det_db_score_mode='slow', rec_batch_num=1024)\n"
        "    return paddle_ocr"
    )

    if original in text:
        text = text.replace(original, replacement)
        text = text.replace(
            "result = paddle_ocr.ocr(image_np, cls=False)[0]",
            "result = _ensure_paddle_ocr().ocr(image_np, cls=False)[0]",
        )
        utils.write_text(text, encoding="utf-8")
        print("[patch] util/utils.py: PaddleOCR made lazy")
    else:
        print("[patch] WARNING: expected PaddleOCR block not found; OmniParser "
              "version may differ. If `import util.utils` fails on paddleocr, "
              "patch it manually (make the top-level PaddleOCR import/instantiation lazy).")


def download_weights() -> None:
    try:
        from huggingface_hub import snapshot_download
    except Exception:
        print("ERROR: huggingface_hub not available in this interpreter. "
              "Install it with:  pip install huggingface_hub")
        sys.exit(1)

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[weights] downloading {HF_REPO} (icon_detect + icon_caption) -> {WEIGHTS_DIR}")
    snapshot_download(
        repo_id=HF_REPO,
        local_dir=str(WEIGHTS_DIR),
        allow_patterns=["icon_detect/*", "icon_caption/*"],
    )

    # OmniParser's caption loader expects the folder named icon_caption_florence.
    src = WEIGHTS_DIR / "icon_caption"
    dst = WEIGHTS_DIR / "icon_caption_florence"
    if src.exists() and not dst.exists():
        print(f"[weights] renaming {src.name} -> {dst.name}")
        src.rename(dst)


def verify() -> bool:
    """Check the artifacts the Viewer/CLI look for; return True if all present."""
    icon_detect = WEIGHTS_DIR / "icon_detect" / "model.pt"
    icon_caption = WEIGHTS_DIR / "icon_caption_florence"
    checks = [
        ("OmniParser repo", REPO_DIR.exists()),
        ("icon_detect/model.pt", icon_detect.exists()),
        ("icon_caption_florence/", icon_caption.is_dir()),
        ("ultralytics installed", "ultralytics" not in check_deps()),
        ("supervision installed", "supervision" not in check_deps()),
    ]
    print("\n=== Verification ===")
    ok = True
    for label, passed in checks:
        print(f"  [{'OK ' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description="Set up OmniParser detector backend.")
    ap.add_argument("--install-deps", action="store_true",
                    help="pip install missing deps (ultralytics, supervision) into this interpreter")
    ap.add_argument("--skip-repo", action="store_true", help="do not clone the OmniParser repo")
    ap.add_argument("--skip-weights", action="store_true", help="do not download weights")
    args = ap.parse_args()

    print(f"Interpreter : {sys.executable}")
    print(f"Project root: {PROJECT_ROOT}\n")

    missing = check_deps()
    if missing:
        print(f"[deps] missing: {', '.join(missing)}")
        if args.install_deps:
            install_deps(missing)
        else:
            print("       re-run with --install-deps to install them automatically, or:")
            print(f"       {sys.executable} -m pip install {' '.join(missing)}")
    else:
        print("[deps] ultralytics, supervision present")

    if not args.skip_repo:
        try:
            clone_repo()
        except FileNotFoundError:
            print("ERROR: git not found on PATH. Install git or clone OmniParser manually to "
                  f"{REPO_DIR}")
        except subprocess.CalledProcessError as e:
            print(f"ERROR cloning repo: {e}")
        patch_repo()

    if not args.skip_weights:
        download_weights()

    all_ok = verify()

    print("\n=== Next steps ===")
    if all_ok:
        print("All set. Launch the Viewer (start_viewer.bat) and pick 'omniparser' in the Det dropdown,")
        print("or run:  python scripts/process_gui_image.py <image> --detector omniparser")
        print("No environment variables needed — default paths are auto-detected.")
    else:
        print("Some items are missing above. Fix them, or set these env vars to custom paths:")
        print("  OMNIPARSER_ROOT         = <path to cloned OmniParser repo>")
        print("  OMNIPARSER_ICON_DETECT  = <path to icon_detect model .pt>")
        print("  OMNIPARSER_ICON_CAPTION = <path to icon_caption_florence dir>")


if __name__ == "__main__":
    main()
