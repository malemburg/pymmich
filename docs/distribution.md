# Distribution formats

pymmich ships in two shapes:

1. A **Python package** (sdist + wheel) published to PyPI.
2. **Standalone executables** produced by PyInstaller, one per
   operating system.

Both are produced from the same source tree; which one you reach for
depends on whether the target machine already has Python installed.

## Python package (PyPI)

The default, and by far the lightest distribution. Users install it
with a single `pip` (or `uvx`, or `pipx`) invocation:

```bash
pip install pymmich
uvx pymmich --help     # install-less one-shot run
```

Build it locally with:

```bash
uv run just build
```

This produces a source distribution and a pure-Python wheel in
`./dist/`, named `pymmich-<version>.tar.gz` and
`pymmich-<version>-py3-none-any.whl`.

## Standalone executables (PyInstaller)

For users who can't or don't want to install Python, pymmich can be
frozen into a single-file executable for Linux, Windows and macOS.

Each binary bundles its own Python interpreter and every dependency,
so running it needs **nothing but the OS itself** on the target
machine — no Python, no `pip`, no compiler.

### Building

```bash
uv run just pyinstaller
```

This:

1. Installs a **uv-managed** Python 3.13 distribution (the managed
   distributions ship `libpython3.13.so` / equivalent, which the
   PyInstaller bootloader needs).
2. Syncs the `pyinstaller` dependency group.
3. Runs `scripts/build_pyinstaller.py --clean`.

The binary lands at
`dist/pyinstaller/pymmich-<version>-<os>-<arch>[.exe]`.

!!! note "No C compiler required"
    Every pymmich runtime dependency (httpx, typer, click, rich, and
    all transitives) is a pure-Python wheel, and PyInstaller itself is
    too. A cross-platform regression test
    (`tests/test_build_pyinstaller.py::test_all_runtime_deps_are_pure_python`)
    fails the build if a future dependency change accidentally
    introduces a native extension.

### Cross-platform builds

PyInstaller does **not** cross-compile. To produce a Windows `.exe`
you have to run the build on Windows; likewise for macOS. The typical
setup is a CI matrix (GitHub Actions `windows-latest`, `ubuntu-latest`,
`macos-latest`, or GitLab runners with matching tags) each invoking
`uv run just pyinstaller` and uploading the produced binary as an
artifact. Since `just` is bundled into the venv as `rust-just`, no
extra tool needs to be installed on the runner beyond `uv` itself.

### What you get

| OS        | Filename                                        | Bootloader |
| --------- | ----------------------------------------------- | ---------- |
| Linux     | `pymmich-<ver>-linux-x86_64`                    | ELF        |
| Linux ARM | `pymmich-<ver>-linux-arm64`                     | ELF        |
| Windows   | `pymmich-<ver>-windows-amd64.exe`               | PE/COFF    |
| macOS     | `pymmich-<ver>-macos-x86_64` / `-arm64`         | Mach-O     |

Typical output size is around **15–20 MB** — that's the full Python
runtime, the standard library, httpx, typer, click, and rich folded
into one file.

### Smoke-testing a build

A slow end-to-end test actually runs PyInstaller, invokes the binary,
and checks the version string. It's gated behind an environment
variable so it doesn't run on every `make test`:

```bash
PYMMICH_PYINSTALLER_SMOKE=1 uv run pytest \
    tests/test_build_pyinstaller_smoke.py
```

### Troubleshooting

- **`Python shared library … was not found`** — You're building against
  a statically-linked system Python (common on Debian/Ubuntu minimal
  images). Rerun `uv run just venv` so the recipe re-creates the venv
  with `uv python install 3.13` + `uv venv --managed-python`.
- **Binary is much larger than expected** — Check whether a new
  dependency pulled in a native extension. Run
  `uv run pytest tests/test_build_pyinstaller.py` — the
  `test_all_runtime_deps_are_pure_python` test will flag it.
- **Binary exits immediately with no output** — Run it with
  `PYI_VERBOSE_IMPORT=1` to get PyInstaller's import trace.

## Which format should I use?

| You have…                              | Reach for               |
| -------------------------------------- | ----------------------- |
| Python 3.13+ already installed         | `pip install pymmich`   |
| `uv` already installed, one-off script | `uvx pymmich …`         |
| A container / CI job / build agent     | `pip install pymmich`   |
| A locked-down machine without Python   | PyInstaller binary      |
| A corporate laptop you can't pip on    | PyInstaller binary      |
