# Getting started

## Requirements

- Python **3.13** or newer
- Access to a running [Immich](https://immich.app) server
- An Immich API key (Account → **API Keys** in the Immich web UI)

pymmich runs on Linux, Windows, and macOS.

## Install

### From PyPI

```bash
pip install pymmich
```

### One-off run via `uvx`

If you already have [uv](https://docs.astral.sh/uv/) you can skip
installation and run pymmich directly:

```bash
uvx pymmich --help
```

## Authenticate

pymmich reads its credentials from two environment variables:

```bash
export PYMMICH_URL="https://immich.example.com"
export PYMMICH_API_KEY="your-api-key-here"
```

If either is unset, pymmich exits with an error — it will not guess.

!!! tip "Verifying the connection"
    If you want to check that the credentials work before uploading
    anything real, try a harmless download with a pattern that won't
    match:

    ```bash
    pymmich download "__definitely_not_there__"
    ```

    A credentials problem surfaces with a clear 4xx/5xx error.

## First upload

Upload the current directory as an album:

```bash
pymmich upload . --recursive
```

The album name defaults to the directory's base name. See
[Upload](commands/upload.md) for the full option list.

## First download

Pull an album back:

```bash
pymmich download "My Album" --out ./restore
```

See [Download](commands/download.md) for more.
