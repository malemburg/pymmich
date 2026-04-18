# Development

pymmich is a small Python package managed with [uv](https://docs.astral.sh/uv/)
and a top-level [`justfile`](https://github.com/casey/just).

## Layout

```
.
├── justfile            # cross-platform task runner
├── pyproject.toml      # package metadata and dependencies
├── README.md
├── LICENSE.md
├── src/
│   └── pymmich/        # library + CLI source
├── tests/              # pytest suite
├── docs/
│   ├── zensical.yml    # Zensical config
│   └── content/        # Markdown sources (logo, assets, commands/, …)
└── scripts/            # build helpers (pyinstaller, cleanup, ...)
```

## Why just?

The project targets Linux, macOS, **and Windows**. A shell-driven
`Makefile` doesn't really work on Windows without extra tooling
(`make.exe` from MSYS, workarounds for `find`/`rm`/etc.). `just`
is a single prebuilt binary, has identical syntax on every OS, and is
shipped as the pip-installable `rust-just` wheel — so it becomes part
of the venv the moment you run `uv sync`.

## Setting up a dev environment

```bash
uv sync --all-groups      # creates .venv + installs every dep group,
                          # including `just` itself
```

After this `.venv/bin/just` (or `.venv\Scripts\just.exe` on Windows)
is available. You can either prefix every call with `uv run`:

```bash
uv run just <recipe>
```

or activate the venv and use `just` directly:

```bash
# POSIX
source .venv/bin/activate
just <recipe>

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
just <recipe>
```

## Running the test suite

```bash
uv run just test
# or with extra pytest args:
uv run just test -k list_users -v
```

Tests use [respx](https://lundberg.github.io/respx/) to mock the
Immich HTTP API — no live server is ever contacted, so the suite is
hermetic and fast.

## Building a distribution

```bash
uv run just build         # wheel + sdist in ./dist/
uv run just pyinstaller   # standalone one-file binary in ./dist/pyinstaller/
```

See the [Distribution](distribution.md) page for the details of each
artifact and the per-platform build workflow.

## Building / serving the docs

```bash
uv run just docs         # static site in ./site/
uv run just docs-serve   # live reload at http://127.0.0.1:8000
```

## Cleaning up

```bash
uv run just clean        # remove build, dist, site
uv run just distclean    # clean + caches, __pycache__, editor backups
```

## Adding a new CLI command

The CLI lives in `src/pymmich/cli.py` and is built on top of
[Typer](https://typer.tiangolo.com/). The HTTP client with all the
Immich-specific knowledge lives in `src/pymmich/client.py`. Keep new
commands thin — business logic belongs in the client.

Write a test first (TDD is the project rule), then the implementation.

## Adding a new just recipe

Edit `justfile` at the top of the project. The last comment line
before a recipe becomes its description in `just --list` — keep it
short and verb-first. Use Python (`uv run python scripts/…`) for
anything that would need different shell commands on Windows vs. POSIX
rather than writing two `[unix]` / `[windows]` variants.
