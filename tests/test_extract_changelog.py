"""Tests for ``scripts/extract_changelog.py``."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "extract_changelog.py"


def _load_module():
    # Load the script as a module; scripts/ is not importable by name.
    spec = importlib.util.spec_from_file_location(
        "extract_changelog", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module():
    return _load_module()


SAMPLE = """# Changelog

## [0.3.0] - 2026-04-19

### Added

- New feature A.

### Changed

- Behaviour B.

## [0.2.0] - 2026-04-19

### Added

- Old feature.

## [0.1.0] - 2026-04-18

### Added

- Initial release.
"""


def test_extracts_current_section(module):
    body = module.extract("0.3.0", SAMPLE)
    assert body is not None
    assert "New feature A." in body
    assert "Behaviour B." in body
    # Must stop at the next version header.
    assert "Old feature." not in body
    assert "## [0.2.0]" not in body


def test_extracts_middle_section(module):
    body = module.extract("0.2.0", SAMPLE)
    assert body is not None
    assert "Old feature." in body
    assert "Initial release." not in body


def test_extracts_last_section(module):
    body = module.extract("0.1.0", SAMPLE)
    assert body is not None
    assert "Initial release." in body


def test_missing_version_returns_none(module):
    assert module.extract("9.9.9", SAMPLE) is None


def test_partial_version_does_not_match(module):
    # "0.3" must not match "[0.3.0]".
    assert module.extract("0.3", SAMPLE) is None


def test_cli_prints_section(module, capsys, tmp_path, monkeypatch):
    # Point the script at a temporary CHANGELOG without mutating the
    # real one.
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(module, "CHANGELOG", changelog)

    rc = module.main(["extract_changelog.py", "0.3.0"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "New feature A." in captured.out


def test_cli_missing_exits_1(module, capsys, tmp_path, monkeypatch):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(module, "CHANGELOG", changelog)

    rc = module.main(["extract_changelog.py", "9.9.9"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "no CHANGELOG entry" in captured.err
