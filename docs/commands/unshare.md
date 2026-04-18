# `pymmich unshare`

Remove one or more users from the sharing list of one or more albums.

## Synopsis

```bash
pymmich unshare [OPTIONS] ALBUMS...
```

## Behaviour

- Album matching and user resolution work the same way as for
  [`share`](share.md) — globs, case-insensitive by default, email-first
  user lookup.
- For every matched album, the current list of shared users is fetched
  via `GET /albums/{id}`; then each `--with` user is compared against
  that list:
    - If the user **is** shared, they are removed.
    - If the user **is not** shared on that album, a **warning** is
      printed and the user is skipped. This mirrors the spec rule that
      unshare must not fail for users that aren't shared.
- As with `share`, if no album matches the patterns, the command exits
  non-zero before doing anything.
- Unknown user identifiers still fail hard — a missing user is a
  configuration error, not "nothing to do".

## Options

| Option                                   | Description                                                                |
| ---------------------------------------- | -------------------------------------------------------------------------- |
| `-w, --with TEXT`                        | **Required.** User name or email. Pass multiple times for multiple users.  |
| `-s, --case-sensitive / -i, --case-insensitive` | Toggle case-sensitive album matching. Default: case-insensitive.    |
| `--only-owned`                           | Only consider albums you own (skip albums shared with you).                |
| `-h, --help`                             | Show help.                                                                 |

### Album scope

Like [`share`](share.md), `unshare` queries `/albums?shared=true` by
default so that albums shared with you are included in the pattern
match (useful if you're a co-owner/editor and want to manage
co-sharing). Pass `--only-owned` to restrict to owned albums.

## Examples

```bash
# Remove one user from a specific album.
pymmich unshare "Vacation 2024" --with bob@example.com

# Remove two users from every album starting with "Trip ".
pymmich unshare "Trip *" \
    --with alice@example.com \
    --with bob@example.com
```

## Exit codes

| Code | Meaning                                                                   |
| ---- | ------------------------------------------------------------------------- |
| `0`  | All processed albums handled (possibly with warnings for non-shared users). |
| `1`  | No album matched, a user could not be resolved, or a server error.        |
| `2`  | Missing / invalid configuration (env vars) or invalid CLI arguments.      |
