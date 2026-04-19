<p align="center">
  <img src="https://raw.githubusercontent.com/malemburg/pymmich/main/docs/content/assets/logo.svg" alt="pymmich logo" width="180"/>
</p>

# pymmich

> A simple CLI for uploading and downloading photos and videos to/from an
> [Immich](https://immich.app) server.

`pymmich` mirrors the most common tasks you want to automate against an
Immich instance:

- **Upload** a list of directories and/or single files.
  Directories are turned into albums (created on the fly if needed),
  single files are uploaded without album association.
- **Download** assets or whole albums back to local disk,
  restoring the original file creation date on each file and using the
  oldest asset's date as the directory's mtime.
- **List** albums and/or assets on the server as a table, `ls -l`-style,
  or JSON, with optional date-range, scope, and limit filters.
- **List users** available for sharing (name + email), optionally
  filtered by a glob or email domain substring.
- **Share** one or more albums (matched by name or glob) with one or
  more users, identified by email or name. A `--role` flag chooses
  `editor` (default) or `viewer`.
- **Unshare** the same way. If a requested user wasn't actually shared
  on an album, a warning is printed and the command continues.

## Documentation

Full documentation is published at
**<https://malemburg.github.io/pymmich/>**.

## Installation

`pymmich` is published on PyPI:

```bash
pip install pymmich
# or, without installing, one-off run:
uvx pymmich --help
```

Python ≥ 3.13 is required. `pymmich` runs on Linux, Windows and macOS.

If you'd rather not have Python on the target machine at all, pymmich
also ships as a single-file **standalone executable** for each OS
(produced with PyInstaller). See the
[distribution docs](https://malemburg.github.io/pymmich/distribution/)
for details.

## Configuration

`pymmich` reads credentials from environment variables:

| Variable            | Purpose                                                       |
| ------------------- | ------------------------------------------------------------- |
| `PYMMICH_URL`       | Base URL of your Immich server (e.g. `https://immich.me`)     |
| `PYMMICH_API_KEY`   | API key created via the Immich web UI (Account → API Keys)   |
| `PYMMICH_VERIFY_TLS`| Set to `0` to disable certificate verification (dev only)     |

If either of the two required variables is missing, `pymmich` exits with
a clear error message instead of silently guessing.

### API key permissions

If you want to create a scoped API key instead of granting all
permissions, the current set of permissions `pymmich` needs is:

`album.read`, `album.create`, `albumAsset.create`, `albumUser.create`,
`albumUser.delete`, `asset.read`, `asset.upload`, `asset.download`,
`user.read`.

See the
[API key permissions docs](https://malemburg.github.io/pymmich/api-permissions/)
for the per-command breakdown.

## Usage

```bash
# Upload one file plus two folders, recurse into subdirs:
pymmich upload ./single.jpg ~/Pictures/Vacation ~/Pictures/Birthdays --recursive

# Download an album and a filename glob into ./out:
pymmich download "Vacation 2024" "IMG_*.heic" --dir ./out

# Show the 10 most recent assets as a table:
pymmich list --limit 10

# Who can I share albums with?
pymmich list-users

# Share all "Trip *" albums with two users as editors:
pymmich share "Trip *" --with alice@example.com --with bob@example.com

# Revoke Bob's access to a single album:
pymmich unshare "Trip 2024" --with bob@example.com
```

Run `pymmich <command> --help` for the full option list.

## Development

Bootstrap once:

```bash
uv sync --all-groups   # installs runtime + dev deps, including just
```

Then everything is driven by [`just`](https://github.com/casey/just),
which is pulled into `.venv/bin/just` automatically by the sync above —
no separate install needed:

```bash
uv run just            # list recipes
uv run just venv       # re-create .venv with a uv-managed Python 3.13
uv run just test       # run the pytest suite
uv run just build      # build wheel + sdist into ./dist
uv run just pyinstaller  # build a standalone one-file binary into
                         # ./dist/pyinstaller/
uv run just docs       # build the docs site into ./site
```

(Or activate the venv with `source .venv/bin/activate` and drop the
`uv run` prefix.)

`pymmich` uses [uv](https://docs.astral.sh/uv/) for environment and
build management; install it first via `pip install uv` or your OS
package manager. `just` itself is delivered as a pip-installable wheel
(`rust-just` on PyPI), so the whole toolchain is cross-platform and
needs no C compiler.

## Changelog

Release notes live in [CHANGELOG.md](CHANGELOG.md).

## License

`pymmich` is licensed under the [Apache License 2.0](LICENSE.md).
