# pymmich

<p align="center">
  <img src="assets/logo.svg" alt="pymmich logo" width="160"/>
</p>

**pymmich** is a small, focused CLI for uploading and downloading photos and
videos to/from an [Immich](https://immich.app) server — and for managing
who those albums are shared with.

It does six things — and tries to do them well:

- **`pymmich upload`** — push a mix of directories and files to Immich.
  Directories become albums (created on the fly if they don't exist yet);
  single files are uploaded without any album association.
- **`pymmich download`** — pull albums or individual files back out.
  Albums are materialised as directories; file creation dates and
  directory mtimes are set from the asset metadata.
- **`pymmich list`** — inspect albums and/or assets on the server in a
  table, `ls -l`-style, or JSON.
- **`pymmich list-users`** — show the users (name + email) available for
  sharing albums with.
- **`pymmich share`** — share one or more albums (glob-matched by name)
  with one or more users, identified by email or name.
- **`pymmich unshare`** — undo a share. Warns but doesn't fail if a
  requested user wasn't actually shared on an album.

## At a glance

```bash
# Push two folders (as albums) and one standalone file
pymmich upload ~/Pictures/Vacation ~/Pictures/Birthdays ./selfie.jpg --recursive

# Pull an album and a filename pattern into ./backup
pymmich download "Vacation 2024" "IMG_*.heic" --dir ./backup

# Show my 10 most recent assets as a table
pymmich list --limit 10

# Who can I share albums with?
pymmich list-users

# Share every "Trip *" album with Alice and Bob as editors
pymmich share "Trip *" --with alice@example.com --with bob@example.com

# Revoke Bob's access to a single album
pymmich unshare "Trip 2024" --with bob@example.com
```

## Quick links

- [Getting started](getting-started.md) — install and authenticate.
- [Upload command](commands/upload.md)
- [Download command](commands/download.md)
- [List command](commands/list.md)
- [List-users command](commands/list-users.md)
- [Share command](commands/share.md)
- [Unshare command](commands/unshare.md)
- [Configuration](configuration.md) — environment variables.
- [API key permissions](api-permissions.md) — which permissions to grant.
- [Distribution](distribution.md) — PyPI wheels and standalone binaries.
- [Development](development.md) — contributing, tests, docs.

## Design goals

- **Minimal surface area.** Six commands, a handful of options.
- **Honest error handling.** If the server or configuration is wrong,
  pymmich tells you — it never silently continues on bad data.
- **Scriptable.** No interactive prompts, credentials via env vars.
- **Portable.** Works on Linux, Windows and macOS with Python 3.13+.

## License

pymmich is released under the
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
