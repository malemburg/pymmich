# `pymmich list`

List albums and/or assets on the Immich server.

## Synopsis

```bash
pymmich list [OPTIONS] [TARGETS...]
```

## Behaviour

- **No targets**: both **albums** and **assets** are listed — albums
  first (sorted by most-recent-asset date, DESC), then assets (sorted
  by creation date, DESC).
- **With targets**: each argument is first tried as an **album name /
  glob** (just like `download`). If nothing matches, it falls back to a
  **filename search**:
    - A pattern without glob metacharacters (`*`, `?`, `[`) is matched
      as a substring server-side.
    - A pattern with glob chars is first narrowed server-side on the
      stem and then refined client-side via `fnmatch`.
- When an album matches, its assets are inlined underneath the album
  entry (skipped if `--albums-only` is in effect).
- **Default cap**: at most **50 items** are printed; pass `--limit N`
  to raise the cap (or `--limit 0` for no cap at all). A footer line
  on stderr reports the total — "_N albums and M assets in total_" if
  everything fits, or "_showing K of N albums and M assets_" when more
  results exist than were printed.

## Options

| Option                                   | Description                                                         |
| ---------------------------------------- | ------------------------------------------------------------------- |
| `-f, --format [table\|long\|json]`       | Output format. Default: `table`.                                    |
| `--albums-only`                          | Only list albums; skip asset matching and album contents.           |
| `--assets-only`                          | Only list assets; treat all targets as filename patterns.           |
| `--only-owned`                           | Only show albums/assets you own.                                    |
| `--only-shared`                          | Only show albums/assets shared with you.                            |
| `--since YYYY-MM-DD`                     | Lower bound on asset creation date (inclusive).                     |
| `--until YYYY-MM-DD`                     | Upper bound on asset creation date (**exclusive**).                 |
| `-n, --limit N`                          | Cap output at N items (default: **50**; pass **0** to disable).     |
| `-s, --case-sensitive / -i, --case-insensitive` | Toggle case-sensitive pattern matching. Default: case-insensitive. |
| `-h, --help`                             | Show help.                                                          |

`--albums-only` and `--assets-only` are mutually exclusive, as are
`--only-owned` and `--only-shared`.

## Output formats

### `table` (default)

A rich terminal table with Type, Name, Date, and a Count/Id column:

```
┏━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Type  ┃ Name            ┃ Date       ┃ Count/Id   ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ ALBUM │ Vacation 2024   │ -          │ 15 assets  │
│ ASSET │ IMG_0001.heic   │ 2024-07-12 │ 6a1f0c22   │
└───────┴─────────────────┴────────────┴────────────┘
```

Good for interactive use. Not meant to be parsed.

### `long`

`ls -l` style, with a header row, then one line per entry:

```
TYPE   COUNT  DATE              NAME
ALB       15  -                 Vacation 2024
AST        -  2024-07-12 14:33  IMG_0001.heic
```

Columns are: type (`ALB` for album, `AST` for asset), asset count
(`-` for non-album entries), creation date, and name.

### `json`

Newline-delimited JSON (one object per line), easy to pipe into `jq`:

```json
{"kind": "album", "id": "…", "name": "Vacation 2024", "date": null, "assetCount": 15}
{"kind": "asset", "id": "…", "name": "IMG_0001.heic", "date": "2024-07-12T14:33:00+00:00", "assetCount": null}
```

## Examples

```bash
# Default: show up to 50 albums + assets, most recent first.
pymmich list

# Remove the default cap — stream everything:
pymmich list --limit 0

# What did I take in the last week?
pymmich list --since "$(date -d '7 days ago' +%F)" --assets-only

# Top 20 most recent assets, as JSON for a dashboard:
pymmich list --limit 20 --assets-only --format json

# Which albums have I been invited to (read-only scope)?
pymmich list --albums-only --only-shared

# How big is my 'Trip 2024' album?
pymmich list "Trip 2024" --albums-only

# Every HEIC file whose name starts with 'IMG_':
pymmich list "IMG_*.heic" --assets-only --format long
```

## Exit codes

| Code | Meaning                                                       |
| ---- | ------------------------------------------------------------- |
| `0`  | Success (possibly with zero matches when targets were empty). |
| `1`  | Targets were given but nothing matched, or a server error.    |
| `2`  | Invalid / conflicting options, or missing configuration.      |
