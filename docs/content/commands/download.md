# `pymmich download`

Download albums or individual assets from Immich.

## Synopsis

```bash
pymmich download [OPTIONS] TARGETS...
```

## Behaviour

Each `TARGET` is first looked up as an **album name**. If no album
matches, the target is treated as a **filename glob** (e.g. `*.jpg`,
`IMG_*.heic`).

- **Album downloads** create a directory under `--dir` named after the
  album and populate it with the album's assets.
    - If a directory with the same name already exists, new files are
      added alongside any existing ones — pymmich never deletes local
      files.
    - The directory's mtime is set to the oldest asset's creation date.
- **Filename glob downloads** write matching assets flat into `--dir`.
- For every downloaded file, the mtime is set to the asset's
  `fileCreatedAt` date so the files carry a meaningful timestamp.
- **Album scope**: by default, pymmich queries the server with
  `?shared=true`, which surfaces both albums you own **and** albums
  others have shared with you. Pass `--only-owned` to restrict the
  lookup to albums you own.

## Options

| Option                | Description                                                         |
| --------------------- | ------------------------------------------------------------------- |
| `-d, --dir PATH`                         | Destination directory. Defaults to the current directory.    |
| `-f, --force`                            | Overwrite pre-existing local files. Default: rename the incoming file with a numbered suffix (`foo.jpg` → `foo_1.jpg`) and print a warning. |
| `-s, --case-sensitive / -i, --case-insensitive` | Toggle case-sensitive album matching. Default: case-insensitive. |
| `--only-owned`                           | Only consider albums you own (skip albums shared with you).  |
| `-h, --help`                             | Show help.                                                   |

## Examples

```bash
# Download a whole album back to ./backup/Vacation.
pymmich download "Vacation 2024" --dir ./backup

# Download every HEIC whose name starts with 'IMG_'.
pymmich download "IMG_*.heic" --dir ./heics

# Mix of both in one invocation.
pymmich download "Vacation 2024" "IMG_*.heic" --dir ./restore

# Strict: ignore albums that were shared with you, only pull your own.
pymmich download "Vacation 2024" --dir ./backup --only-owned

# Overwrite any local files that happen to have the same name as the
# incoming ones (default is to save the incoming file as foo_1.jpg).
pymmich download "Vacation 2024" --dir ./backup --force
```

## Exit codes

| Code | Meaning                                              |
| ---- | ---------------------------------------------------- |
| `0`  | At least one target matched and was downloaded.      |
| `1`  | No matches found, or a server error occurred.        |
| `2`  | Missing / invalid configuration (env vars).          |
