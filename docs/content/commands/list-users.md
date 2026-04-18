# `pymmich list-users`

List users available for sharing albums with.

## Synopsis

```bash
pymmich list-users [OPTIONS] [PATTERNS...]
```

## Behaviour

- **No patterns**: every user visible to your API key is listed.
- **With patterns**: each argument filters the user list.
    - A pattern with glob metacharacters (`*`, `?`, `[`) is matched via
      `fnmatch` against both the user's **name** and **email**.
    - A plain string is matched as a case-insensitive **substring** of
      either field — handy for filtering by email domain
      (e.g. `pymmich list-users @example.com`).
- **Default cap**: at most **50 users** are printed. Pass `--limit N`
  to raise the cap, or `--limit 0` to disable it. A footer on stderr
  reports the total ("_N users in total_" or "_showing K of N users_").

## Options

| Option                                   | Description                                                         |
| ---------------------------------------- | ------------------------------------------------------------------- |
| `-f, --format [table\|long\|json]`       | Output format. Default: `table`.                                    |
| `-n, --limit N`                          | Cap output at N users (default: **50**; pass **0** to disable).     |
| `-s, --case-sensitive / -i, --case-insensitive` | Toggle case-sensitive pattern matching. Default: case-insensitive. |
| `-h, --help`                             | Show help.                                                          |

## Output formats

### `table` (default)

Rich terminal table with Name, Email and a short Id column:

```
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Name    ┃ Email               ┃ Id       ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ Alice   │ alice@example.com   │ 6a1f0c22 │
│ Bob     │ bob@example.com     │ 2e9b77a4 │
└─────────┴─────────────────────┴──────────┘
```

### `long`

Header row followed by one line per user, full id included:

```
NAME                      EMAIL                             ID
Alice                     alice@example.com                 6a1f0c22-...-...
Bob                       bob@example.com                   2e9b77a4-...-...
```

### `json`

Newline-delimited JSON (`kind: "user"`):

```json
{"kind": "user", "id": "…", "name": "Alice", "email": "alice@example.com"}
```

## Examples

```bash
# Every user on the server.
pymmich list-users

# Just users whose email is on example.com:
pymmich list-users @example.com

# Glob on the name:
pymmich list-users "A*"

# All users as JSON, no cap:
pymmich list-users --limit 0 --format json
```

## Exit codes

| Code | Meaning                                                  |
| ---- | -------------------------------------------------------- |
| `0`  | Success (possibly zero users when no patterns given).    |
| `1`  | Patterns were given but nothing matched, or server error.|
| `2`  | Invalid options, or missing configuration.               |

## API permissions

`list-users` only needs `user.read`, which the `share` and `unshare`
commands already require — no additional permission is needed.
