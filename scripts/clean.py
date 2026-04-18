"""Cross-platform cleanup helper.

Invoked by the ``just clean`` and ``just distclean`` recipes. We use a
Python script rather than shell commands because ``rm -rf``,
``find -delete`` and friends don't exist on Windows — and writing two
recipes per target (``[unix]`` / ``[windows]``) for every build step
gets noisy fast.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Build artefacts — removed by both ``clean`` and ``distclean``.
BUILD_DIRS = ("build", "dist", "site", ".coverage", "htmlcov")

# Extra cache-y directories swept up by ``distclean``.
CACHE_DIR_NAMES = ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")

# Editor/OS leftovers swept up by ``distclean``.
GARBAGE_GLOBS = ("*.py[co]", "*~", "*.bak", "*.swp", "*.swo")


def _remove_path(path: pathlib.Path) -> None:
    """Remove ``path`` whether it's a file or a directory, silently."""
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def clean() -> None:
    """Remove top-level build artefacts (``clean`` target)."""
    for name in BUILD_DIRS:
        _remove_path(PROJECT_ROOT / name)
    # Stale egg-info metadata on either the project root or src/.
    for root in (PROJECT_ROOT, PROJECT_ROOT / "src"):
        if not root.is_dir():
            continue
        for info in root.glob("*.egg-info"):
            _remove_path(info)


def distclean() -> None:
    """Everything ``clean`` does, plus bytecode caches and editor junk."""
    clean()
    for name in CACHE_DIR_NAMES:
        for d in PROJECT_ROOT.rglob(name):
            _remove_path(d)
    for pattern in GARBAGE_GLOBS:
        for p in PROJECT_ROOT.rglob(pattern):
            _remove_path(p)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--distclean",
        action="store_true",
        help="Also remove caches, bytecode, editor backups.",
    )
    args = parser.parse_args(argv)
    if args.distclean:
        distclean()
    else:
        clean()
    return 0


if __name__ == "__main__":
    sys.exit(main())
