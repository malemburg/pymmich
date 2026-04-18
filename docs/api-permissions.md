# API key permissions

When you create an API key in the Immich web UI (Account → **API Keys**
→ **New API Key**), you can limit the key to a specific set of
permissions. This page lists exactly which permissions `pymmich`
currently needs — both as a complete set (if you want one key that
works for every command) and broken down per command (if you want the
smallest key that's still useful).

!!! tip "Full access always works"
    If you don't care about scoping the key down, selecting **All
    permissions** on the API-key dialog works too. The permission list
    below is only interesting if you want to follow the principle of
    least privilege.

## Complete set (all `pymmich` commands)

Selecting these nine permissions is enough for every command the tool
currently ships:

| Permission             | Used by                                                                             |
| ---------------------- | ----------------------------------------------------------------------------------- |
| `album.read`           | `upload`, `download`, `list`, `share`, `unshare`                                    |
| `album.create`         | `upload` (when an album needs to be created)                                        |
| `albumAsset.create`    | `upload` (associating uploaded assets with an album)                                |
| `albumUser.create`     | `share`                                                                             |
| `albumUser.delete`     | `unshare`                                                                           |
| `asset.read`           | `download`, `list` (timeline + metadata search, plus per-asset details)             |
| `asset.upload`         | `upload` (uploading each file)                                                      |
| `asset.download`       | `download` (streaming the original bytes)                                           |
| `user.read`            | `share`, `unshare`, `list-users` (listing / resolving users)                        |

The Immich endpoints `GET /server/ping` and `GET /server/media-types`
are public and don't need any permission.

## Per-command breakdown

### `pymmich upload`

Permissions marked as "conditional" are only touched under specific
circumstances — e.g. creating an album is only attempted when the
destination album doesn't exist yet.

| Permission           | HTTP endpoint                   | When                                       |
| -------------------- | ------------------------------- | ------------------------------------------ |
| `album.read`         | `GET /albums`                   | Always (look up target album by name)      |
| `album.create`       | `POST /albums`                  | Conditional: album did not exist yet       |
| `asset.upload`       | `POST /assets`                  | For each file being uploaded               |
| `albumAsset.create`  | `PUT /albums/{id}/assets`       | When uploading a directory (= into album)  |

Uploading only standalone files (no directories) does not require
`album.read`, `album.create`, or `albumAsset.create`, but those are
only skipped when no directory is in the argument list — the simplest
option is to just grant all four.

### `pymmich download`

| Permission       | HTTP endpoint                                    | When                                                         |
| ---------------- | ------------------------------------------------ | ------------------------------------------------------------ |
| `album.read`     | `GET /albums`, `GET /albums?shared=true`         | Resolving target to album (owned + shared-with-me merged)    |
| `asset.read`     | `GET /timeline/buckets`, `GET /timeline/bucket`, `GET /assets/{id}`, `POST /search/metadata` | Album contents (timeline) + per-asset details + filename search |
| `asset.download` | `GET /assets/{id}/original`                      | For every asset being downloaded                             |

!!! note "Why timeline instead of search for album contents?"
    `POST /search/metadata` forcibly scopes results to assets owned by
    the caller (and their partners). For shared albums, that hides
    photos contributed by other members. The timeline endpoints don't
    apply that filter when an `albumId` is given, so `pymmich` uses
    them to get the full roster.

### `pymmich list`

| Permission   | HTTP endpoint                                     | When                                        |
| ------------ | ------------------------------------------------- | ------------------------------------------- |
| `album.read` | `GET /albums`, `GET /albums?shared=true`          | Album matching and `--albums-only` listings |
| `asset.read` | `POST /search/metadata`, `GET /timeline/buckets`, `GET /timeline/bucket`, `GET /assets/{id}` | Asset listings, filename search, album asset enumeration |

### `pymmich list-users`

| Permission   | HTTP endpoint     | When                              |
| ------------ | ----------------- | --------------------------------- |
| `user.read`  | `GET /users`      | Always (the command's whole job). |

No additional permission beyond what `share` and `unshare` already
need — if those work, `list-users` works too.

### `pymmich share`

| Permission          | HTTP endpoint                 | When                            |
| ------------------- | ----------------------------- | ------------------------------- |
| `user.read`         | `GET /users`                  | Resolving `--with` identifiers  |
| `album.read`        | `GET /albums`                 | Matching album glob patterns    |
| `albumUser.create`  | `PUT /albums/{id}/users`      | For each matched album          |

### `pymmich unshare`

| Permission          | HTTP endpoint                             | When                                   |
| ------------------- | ----------------------------------------- | -------------------------------------- |
| `user.read`         | `GET /users`                              | Resolving `--with` identifiers         |
| `album.read`        | `GET /albums` + `GET /albums/{id}`        | Matching globs + reading current shares |
| `albumUser.delete`  | `DELETE /albums/{id}/user/{userId}`       | For each user actually removed         |

## Troubleshooting

If `pymmich` fails with an HTTP 403 ("forbidden") response, the API
key you're using is missing one of the permissions listed above. The
error message that `pymmich` prints includes the HTTP method and path
that was rejected — look that endpoint up in the tables above to see
which permission to add.
