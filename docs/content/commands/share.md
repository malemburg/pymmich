# `pymmich share`

Share one or more albums with one or more users.

## Synopsis

```bash
pymmich share [OPTIONS] ALBUMS...
```

## Behaviour

- Each `ALBUMS` argument is treated as a name or **glob pattern**
  (e.g. `Trip *`, `Vacation 202?`). Matching is case-insensitive by
  default.
- Each user passed via `--with` is looked up on the server:
    - Email first (case-insensitive exact match — emails are unique).
    - Name next (case-insensitive exact match; an ambiguous name match
      fails with an error suggesting to use the email address).
- If no album matches any pattern, the command exits with a non-zero
  status before any sharing takes place — mass-share on a typo is
  prevented.
- If any user identifier cannot be resolved, the command exits with a
  non-zero status without sharing anything.

## Options

| Option                                   | Description                                                                  |
| ---------------------------------------- | ---------------------------------------------------------------------------- |
| `-w, --with TEXT`                        | **Required.** User name or email. Pass multiple times for multiple users.    |
| `--role [editor\|viewer]`                | Role to grant to the shared users. Defaults to `editor`.                     |
| `-s, --case-sensitive / -i, --case-insensitive` | Toggle case-sensitive album matching. Default: case-insensitive.      |
| `--only-owned`                           | Only consider albums you own (skip albums shared with you).                  |
| `-h, --help`                             | Show help.                                                                   |

### Album scope

By default, pymmich queries `/albums?shared=true`, so albums where you
are a member (editor or viewer) are considered too — you can share
someone else's album onward if the server lets you. Pass
`--only-owned` to restrict the pattern match to albums you own.

## Examples

```bash
# Share a single album with one user (by email).
pymmich share "Vacation 2024" --with alice@example.com

# Share all "Trip *" albums with two users as read-only viewers.
pymmich share "Trip *" \
    --with alice@example.com \
    --with bob@example.com \
    --role viewer

# Mix names and emails; both are accepted.
pymmich share "Family Reunion" --with Alice --with bob@example.com
```

## Exit codes

| Code | Meaning                                                                 |
| ---- | ----------------------------------------------------------------------- |
| `0`  | All matched albums were shared successfully.                            |
| `1`  | No album matched, a user could not be resolved, or a server error.      |
| `2`  | Missing / invalid configuration (env vars) or invalid CLI arguments.    |
