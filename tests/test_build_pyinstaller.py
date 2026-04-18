"""Unit tests for the PyInstaller build helper.

Only the fast, compiler-free logic (platform naming, argument
parsing, version reading) is covered here. A full PyInstaller build
runs in tens of seconds, downloads and freezes a Python interpreter,
and emits a large binary — so it lives under
``test_build_pyinstaller_smoke.py`` behind an env-var gate rather
than being part of the default ``make test`` run.
"""

from __future__ import annotations

import importlib.util
import platform as _platform
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "build_pyinstaller.py"


def _load_module():
    """Import ``scripts/build_pyinstaller.py`` as a module.

    The scripts/ directory isn't on ``sys.path`` by default, so we
    locate the file explicitly. This lets the tests exercise the
    helper without making it a first-class package module.
    """
    spec = importlib.util.spec_from_file_location(
        "pymmich_build_pyinstaller", SCRIPT
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_platform_tag_returns_nonempty_string():
    mod = _load_module()
    tag = mod.platform_tag()
    assert isinstance(tag, str)
    assert "-" in tag, f"expected 'os-arch' form, got {tag!r}"
    os_part, arch_part = tag.split("-", 1)
    assert os_part in ("linux", "windows", "macos") or os_part
    assert arch_part


def test_platform_tag_normalises_darwin_to_macos(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(mod.platform, "machine", lambda: "arm64")
    assert mod.platform_tag() == "macos-arm64"


def test_platform_tag_windows_amd64(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(mod.platform, "machine", lambda: "AMD64")
    assert mod.platform_tag() == "windows-amd64"


def test_platform_tag_linux_x86_64(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    assert mod.platform_tag() == "linux-x86_64"


def test_binary_name_includes_version_and_platform(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    assert mod.binary_name("0.1.0") == "pymmich-0.1.0-linux-x86_64"


def test_binary_name_adds_exe_on_windows(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(mod.platform, "machine", lambda: "AMD64")
    assert mod.binary_name("0.1.0") == "pymmich-0.1.0-windows-amd64.exe"


def test_binary_name_without_version(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    assert mod.binary_name() == "pymmich-linux-x86_64"


def test_pymmich_version_matches_package_version():
    """The helper must not rely on importing pymmich (which may pull
    in heavy deps at build time). It reads __init__.py by hand; keep
    the two in sync."""
    mod = _load_module()
    from pymmich import __version__
    assert mod._pymmich_version() == __version__


def test_print_name_subcommand(monkeypatch, capsys):
    mod = _load_module()
    monkeypatch.setattr(mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    from pymmich import __version__
    rc = mod.main(["--print-name"])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"pymmich-{__version__}-linux-x86_64"


def test_entry_module_exists():
    """PyInstaller's build fails with a cryptic error if the entry
    module isn't where scripts/build_pyinstaller.py expects it. Pin
    the invariant here."""
    entry = PROJECT_ROOT / "src" / "pymmich" / "__main__.py"
    assert entry.is_file(), f"missing PyInstaller entry: {entry}"


def test_all_runtime_deps_are_pure_python():
    """Regression guard: the 'no compiler required' promise only holds
    as long as the runtime dependency tree stays pure Python.

    Walk the packages installed into the current venv and flag any
    that ship an extension module (`.so`/`.pyd`) under the pymmich
    runtime closure. pytest/respx/zensical are *test* deps and are
    explicitly skipped — PyInstaller never sees them.
    """
    import pymmich  # noqa: F401

    site_packages = Path(sys.prefix) / "lib"
    # Platform-dependent layout: on Windows it's Lib\site-packages;
    # on POSIX it's lib/pythonX.Y/site-packages.
    candidates = list(site_packages.rglob("site-packages"))
    if not candidates:
        candidates = [Path(sys.prefix) / "Lib" / "site-packages"]
    assert candidates, "could not locate site-packages"

    runtime_roots = [
        "pymmich",
        "httpx",
        "httpcore",
        "h11",
        "certifi",
        "idna",
        "sniffio",
        "anyio",
        "typer",
        "click",
        "rich",
        "markdown_it",
        "mdurl",
        "pygments",
        "shellingham",
        "typing_extensions",
    ]
    offenders: list[Path] = []
    for sp in candidates:
        for root in runtime_roots:
            pkg_dir = sp / root
            if not pkg_dir.exists():
                continue
            for ext in (".so", ".pyd", ".dylib"):
                offenders.extend(pkg_dir.rglob(f"*{ext}"))
    assert not offenders, (
        "Runtime dependency ships a native extension — the "
        "'no compiler required' guarantee for PyInstaller builds "
        f"would no longer hold. Offenders: {offenders}"
    )
