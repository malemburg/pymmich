# `pymmich upload`

Upload files and directories to Immich.

## Synopsis

```bash
pymmich upload [OPTIONS] PATHS...
```

## Behaviour

- **Single files** given on the command line are uploaded as standalone
  assets, without being placed in an album.
- **Directories** are uploaded as an Immich album:
    - The directory's base name is used as the album name.
    - The album is created on the fly if it doesn't exist yet.
    - All image and video files found (directly, or recursively with
      `--recursive`) are uploaded and then associated with the album.
- Which extensions count as "image" or "video" is determined at runtime
  by asking the server (`GET /server/media-types`), so pymmich stays in
  step with whatever your Immich version supports.

## Options

| Option                                   | Description                                                           |
| ---------------------------------------- | --------------------------------------------------------------------- |
| `-r, --recursive`                        | Recurse into subdirectories when scanning a directory.                |
| `-s, --case-sensitive / -i, --case-insensitive` | Toggle case-sensitive directory-to-album matching. Default: case-insensitive. |
| `--only-owned`                           | Only consider albums you own when matching (skip shared).             |
| `-h, --help`                             | Show help.                                                            |

### Album name matching

By default, album names are matched **case-insensitively**, so uploading
`~/Pictures/vacation` to a server that already has an album called
`Vacation` reuses the existing album. The server-side album keeps its
original spelling — pymmich never renames existing albums.

Pass `--case-sensitive` if you want `vacation` and `Vacation` to be
treated as different albums.

When a new album has to be created, it is created using the spelling
from the local directory name.

## Examples

```bash
# Upload two album folders and one standalone photo.
pymmich upload ~/Pictures/Trip2024 ~/Pictures/Birthdays ./loose_photo.jpg

# Recurse into every subdirectory of 'Trip2024'.
pymmich upload ~/Pictures/Trip2024 --recursive

# Force exact-case album name matching.
pymmich upload ./Trip --case-sensitive
```

## Exit codes

| Code | Meaning                                               |
| ---- | ----------------------------------------------------- |
| `0`  | Success.                                              |
| `1`  | A server-side or upload error occurred.               |
| `2`  | Missing / invalid configuration (env vars).           |
