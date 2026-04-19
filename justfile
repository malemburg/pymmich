# pymmich - task runner
#
# Cross-platform recipes. Works on Linux, macOS, and Windows
# (PowerShell). Every recipe goes through uv, so the only host-level
# dependency is uv itself.
#
# Bootstrap (once):
#   uv sync --all-groups
#
# After that, use either:
#   uv run just <recipe>
# or, if .venv is activated, simply:
#   just <recipe>
#
# To see the list of recipes: `just` (or `just --list`).

set windows-shell := ["powershell.exe", "-NoLogoProfile", "-NonInteractive", "-Command"]

PYTHON_VERSION := "3.13"

# List every recipe (default when `just` is run with no arguments).
default:
    @just --list

# Create .venv with a uv-managed Python and install every dep group.
venv:
    uv python install {{PYTHON_VERSION}}
    uv venv --managed-python --python {{PYTHON_VERSION}}
    uv sync --all-groups

# Build sdist + wheel into ./dist.
build:
    uv build

# Alias for `build` so `just dist` works too.
dist: build

# Publish sdist + wheel from ./dist to PyPI. Credentials come from
# UV_PUBLISH_TOKEN (preferred) or UV_PUBLISH_USERNAME/UV_PUBLISH_PASSWORD.
# Rebuilds first to ensure the uploaded artefacts match the current tree.
publish: clean build
    uv publish

# Publish sdist + wheel to TestPyPI (https://test.pypi.org) for
# release dry-runs. Use a TestPyPI-specific token in UV_PUBLISH_TOKEN.
publish-test: clean build
    uv publish --publish-url https://test.pypi.org/legacy/

# Build a standalone one-file binary into ./dist/pyinstaller/.
pyinstaller:
    uv python install {{PYTHON_VERSION}}
    uv venv --managed-python --python {{PYTHON_VERSION}} --allow-existing
    uv sync --group pyinstaller --quiet
    uv run --group pyinstaller python scripts/build_pyinstaller.py --clean

# Run the pytest suite (extra args are forwarded: `just test -k foo`).
test *args:
    uv run --group dev pytest {{args}}

# Run the pymmich CLI (args forwarded: `just run list --limit 10`).
run *args:
    uv run pymmich {{args}}

# Build the docs site into ./docs/site.
docs:
    uv run --group dev zensical build -f docs/zensical.yml

# Live-reload docs server at http://127.0.0.1:8081.
docs-serve:
    uv run --group dev zensical serve -f docs/zensical.yml -a 0.0.0.0:8081

# Remove build and distribution artefacts.
clean:
    uv run python scripts/clean.py

# Deep clean: also removes caches, bytecode, and editor backups.
distclean:
    uv run python scripts/clean.py --distclean
