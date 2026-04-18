# Configuration

pymmich is configured entirely through environment variables so the
same binary can be safely invoked from shells, scripts and CI jobs.

## Required

| Variable            | Description                                              |
| ------------------- | -------------------------------------------------------- |
| `PYMMICH_URL`       | Base URL of the Immich server, e.g. `https://immich.me`. |
| `PYMMICH_API_KEY`   | API key created in the Immich web UI.                    |

If either of the two is missing, pymmich exits with a clear message
and exit code `2`.

## Optional

| Variable             | Default | Description                                                                 |
| -------------------- | ------- | --------------------------------------------------------------------------- |
| `PYMMICH_VERIFY_TLS` | `1`     | Set to `0` / `false` / `no` to disable TLS certificate verification (dev only). |

!!! warning "TLS verification"
    Only disable TLS verification for local development. For any
    production server, leave `PYMMICH_VERIFY_TLS` at its default value.

## Creating an API key

1. Open the Immich web UI.
2. Click your avatar → **Account Settings** → **API Keys**.
3. Click **New API Key**, give it a descriptive name, and either
   select **All permissions** or tick only the permissions pymmich
   actually needs (see [API key permissions](api-permissions.md)).
4. Copy the value that is shown once.
5. Store the value in a secret manager or a shell profile file with
   restrictive permissions.

## Example: `.envrc` for direnv

```bash
export PYMMICH_URL="https://immich.example.com"
export PYMMICH_API_KEY="abcd1234..."
```
