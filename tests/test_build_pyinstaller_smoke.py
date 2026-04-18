"""Slow smoke test for the PyInstaller build.

A real ``pyinstaller`` run installs PyInstaller, bundles the Python
interpreter and every pymmich dependency, and produces a 10–20 MB
one-file binary. That's far too slow for every ``make test`` run,
so this test is **opt-in** via an environment variable:

.. code-block:: bash

    PYMMICH_PYINSTALLER_SMOKE=1 make test

or, equivalently:

.. code-block:: bash

    PYMMICH_PYINSTALLER_SMOKE=1 uv run pytest tests/test_build_pyinstaller_smoke.py

When the flag is set, the test invokes the real build helper,
verifies the resulting binary exists, runs ``--version`` through it,
and checks the reported version matches the Python package's.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "build_pyinstaller.py"
SMOKE_ENV = "PYMMICH_PYINSTALLER_SMOKE"


pytestmark = pytest.mark.skipif(
    os.environ.get(SMOKE_ENV) not in ("1", "true", "yes"),
    reason=f"set {SMOKE_ENV}=1 to run the PyInstaller smoke test",
)


def _load_helper():
    spec = importlib.util.spec_from_file_location(
        "pymmich_build_pyinstaller", SCRIPT
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pyinstaller_build_runs_and_binary_prints_version(tmp_path):
    if not shutil.which("pyinstaller") and importlib.util.find_spec(
        "PyInstaller"
    ) is None:
        pytest.skip(
            "PyInstaller not installed — run "
            "`uv sync --group pyinstaller` first"
        )

    helper = _load_helper()
    produced = helper.build(clean=True)

    assert produced.exists(), f"missing binary: {produced}"
    assert produced.stat().st_size > 0

    # Run the binary and check --version matches the package.
    result = subprocess.run(
        [str(produced), "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    from pymmich import __version__
    assert __version__ in result.stdout
