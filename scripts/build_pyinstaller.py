"""Build a standalone ``pymmich`` executable with PyInstaller.

The script is intentionally small and parameter-free: run it from the
project root with the dev env active (``uv sync --group pyinstaller``)
and it writes a one-file binary to ``dist/pyinstaller/<platform>/``.

Constraints intentionally honoured here:

* **No compiler required.** Every runtime dependency of pymmich is a
  pure-Python wheel (httpx, typer, click, rich + transitives) and
  PyInstaller itself is also a pure-Python wheel, so this script works
  on any platform that has a Python interpreter installed via uv.
* **No cross-compilation.** PyInstaller bundles the interpreter it is
  run with, so build a Windows exe on Windows, a macOS binary on macOS,
  and so on. CI matrices are the sane way to produce all three.

Run directly:

.. code-block:: bash

    uv run --group pyinstaller python scripts/build_pyinstaller.py

Or via the Makefile:

.. code-block:: bash

    make pyinstaller
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path


# Project root is the parent of scripts/. Never rely on an absolute
# path — users might run pymmich out of /opt, /home/..., C:\Users\...,
# or a relocatable build directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
DIST_DIR = PROJECT_ROOT / "dist" / "pyinstaller"
BUILD_DIR = PROJECT_ROOT / "build" / "pyinstaller"


def platform_tag() -> str:
    """Return a short ``os-arch`` label for directory/file naming.

    Kept in its own function so the Makefile, the docs, and the tests
    all agree on how the platform is rendered (``linux-x86_64``,
    ``windows-amd64``, ``macos-arm64``, …).
    """
    system = platform.system().lower()
    if system == "darwin":
        system = "macos"
    machine = platform.machine().lower() or "unknown"
    # Normalise a few common aliases so the label is stable.
    if machine in ("x86_64", "amd64"):
        machine = "x86_64" if system != "windows" else "amd64"
    if machine in ("arm64", "aarch64"):
        machine = "arm64"
    return f"{system}-{machine}"


def binary_name(version: str | None = None) -> str:
    """Return the one-file binary file name for the current platform.

    If ``version`` is provided, it's embedded between the project name
    and the platform tag, matching the distribution-naming rule in the
    project spec.
    """
    base = "pymmich"
    if version:
        base = f"{base}-{version}"
    base = f"{base}-{platform_tag()}"
    if platform.system() == "Windows":
        base += ".exe"
    return base


def _pymmich_version() -> str:
    """Read the package version without importing the runtime."""
    # Parse `__version__ = "X.Y.Z"` out of src/pymmich/__init__.py so
    # we don't accidentally import heavy deps at build time.
    init = SRC_DIR / "pymmich" / "__init__.py"
    for line in init.read_text().splitlines():
        line = line.strip()
        if line.startswith("__version__"):
            _, _, value = line.partition("=")
            return value.strip().strip("'\"")
    raise RuntimeError(f"could not find __version__ in {init}")


def build(*, clean: bool = False) -> Path:
    """Run PyInstaller and return the path to the produced binary.

    Args:
        clean: If true, wipe prior ``build/pyinstaller/`` and
            ``dist/pyinstaller/`` directories first so a stale cache
            cannot poison the next build.
    """
    if clean:
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
        shutil.rmtree(DIST_DIR, ignore_errors=True)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    version = _pymmich_version()
    out_name = binary_name(version)
    # PyInstaller wants its output basename without the ``.exe`` suffix;
    # it adds the platform-appropriate extension itself.
    if out_name.endswith(".exe"):
        pyi_name = out_name[:-4]
    else:
        pyi_name = out_name

    # Use the installed pymmich package's __main__.py as the entry.
    # We pass its path explicitly rather than relying on
    # ``-m pymmich``, because PyInstaller CLI takes a script path.
    entry = SRC_DIR / "pymmich" / "__main__.py"
    if not entry.is_file():
        raise SystemExit(f"entry script not found: {entry}")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",
        "--clean",
        "--noconfirm",
        "--name",
        pyi_name,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(BUILD_DIR),
        # pymmich lives in ``src/``. Put the project's own source first
        # so PyInstaller can resolve ``from pymmich.cli import app``
        # before it looks at site-packages.
        "--paths",
        str(SRC_DIR),
        str(entry),
    ]
    # Don't tee through a shell — subprocess with a list avoids quoting
    # headaches on Windows paths with spaces.
    subprocess.run(cmd, check=True)

    produced = DIST_DIR / out_name
    if not produced.exists():
        # Fall back to whatever PyInstaller wrote (e.g. different
        # extension rules on some platforms) so the caller gets a
        # helpful error with the actual filename.
        matches = list(DIST_DIR.iterdir()) if DIST_DIR.exists() else []
        raise SystemExit(
            f"PyInstaller finished but expected binary not found at "
            f"{produced}. Files in {DIST_DIR}: {matches}"
        )
    return produced


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove previous build/ and dist/pyinstaller/ output first.",
    )
    parser.add_argument(
        "--print-name",
        action="store_true",
        help="Print the binary name for the current platform and exit.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.print_name:
        print(binary_name(_pymmich_version()))
        return 0
    out = build(clean=args.clean)
    print(f"built: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
