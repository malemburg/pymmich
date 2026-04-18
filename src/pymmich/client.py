"""Low-level Immich API client used by the pymmich CLI.

Wraps a minimal subset of the Immich REST API needed for uploading and
downloading photos/videos and managing the albums they belong to.

All network I/O goes through a single ``httpx.Client``; call sites are
expected to use the client as a context manager so the underlying
connection pool is closed on exit.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import fnmatch
import mimetypes
import os
from pathlib import Path
from typing import Any, Iterator

import httpx


DEFAULT_TIMEOUT = 60.0
UPLOAD_TIMEOUT = 300.0
DOWNLOAD_TIMEOUT = 300.0
SEARCH_PAGE_SIZE = 250


class ImmichError(RuntimeError):
    """Raised for any Immich-API or configuration error.

    Wraps the underlying ``httpx`` exception when the failure is a
    transport or HTTP status error.
    """


@dataclasses.dataclass
class MediaTypes:
    """Supported media types returned by ``GET /server/media-types``."""

    image: list[str]
    video: list[str]
    sidecar: list[str]

    @property
    def all_extensions(self) -> set[str]:
        """Return the set of image+video extensions (lowercase, with dot)."""
        return {e.lower() for e in (*self.image, *self.video)}


@dataclasses.dataclass
class User:
    """Minimal representation of an Immich user."""

    id: str
    name: str
    email: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "User":
        """Build a ``User`` from a ``UserResponseDto`` JSON payload."""
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            email=data.get("email", ""),
        )


@dataclasses.dataclass
class AlbumUser:
    """A user + role association on an album."""

    user: User
    role: str  # "editor" | "viewer"

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "AlbumUser":
        """Build an ``AlbumUser`` from an ``AlbumUserResponseDto`` JSON payload."""
        return cls(
            user=User.from_api(data["user"]),
            role=data.get("role", "editor"),
        )


@dataclasses.dataclass
class Album:
    """Minimal representation of an Immich album.

    ``album_users`` is populated by endpoints that return the full
    ``AlbumResponseDto`` (e.g. ``GET /albums/{id}``); list endpoints
    typically omit it, in which case it defaults to an empty list.
    ``start_date`` and ``end_date`` are populated by ``/albums``
    endpoints (start/end of the contained assets) and may be ``None``
    for empty albums.
    """

    # Instance attributes (see module docstring for conventions)
    id: str = ""
    album_name: str = ""
    asset_count: int = 0
    # Default value is mutable (list); set to None in the class definition
    # and assigned in the constructor via from_api() /  __post_init__.
    album_users: list[AlbumUser] = dataclasses.field(default_factory=list)
    start_date: dt.datetime | None = None
    end_date: dt.datetime | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Album":
        """Build an ``Album`` from an ``AlbumResponseDto`` JSON payload."""
        start = data.get("startDate")
        end = data.get("endDate")
        return cls(
            id=data["id"],
            album_name=data["albumName"],
            asset_count=int(data.get("assetCount", 0)),
            album_users=[
                AlbumUser.from_api(au) for au in data.get("albumUsers", [])
            ],
            start_date=_parse_dt(start) if start else None,
            end_date=_parse_dt(end) if end else None,
        )


@dataclasses.dataclass
class UploadResult:
    """Result of an asset upload call (``POST /assets``)."""

    id: str
    status: str  # "created" | "replaced" | "duplicate"


@dataclasses.dataclass
class BulkIdResult:
    """Single entry in a bulk-id response (add/remove assets to/from album)."""

    id: str
    success: bool
    error: str | None = None


@dataclasses.dataclass
class AssetInfo:
    """Minimal asset information used by download."""

    id: str
    original_file_name: str
    file_created_at: dt.datetime
    file_modified_at: dt.datetime
    type: str  # "IMAGE" | "VIDEO" | "AUDIO" | "OTHER"

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "AssetInfo":
        """Build an ``AssetInfo`` from an ``AssetResponseDto`` JSON payload."""
        return cls(
            id=data["id"],
            original_file_name=data.get("originalFileName", data["id"]),
            file_created_at=_parse_dt(data["fileCreatedAt"]),
            file_modified_at=_parse_dt(data["fileModifiedAt"]),
            type=data.get("type", "OTHER"),
        )


def _parse_dt(value: str) -> dt.datetime:
    """Parse an ISO-8601 timestamp in UTC to an aware ``datetime``."""
    # Immich emits ISO-8601 timestamps with a trailing Z; fromisoformat
    # handles offsets but not the Z suffix before Python 3.11 in all cases.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return dt.datetime.fromisoformat(value).astimezone(dt.UTC)


def _isoformat_z(value: dt.datetime) -> str:
    """Return ``value`` as an ISO-8601 timestamp with millisecond precision
    and a trailing ``Z`` — the format Immich expects on date filters."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    else:
        value = value.astimezone(dt.UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")


class ImmichClient:
    """Thin wrapper around the subset of Immich's REST API pymmich needs."""

    # Instance attributes (see module docstring for conventions)
    base_url: str = ""
    api_key: str = ""
    verify_tls: bool = True
    _http: httpx.Client | None = None

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        verify_tls: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialise the client.

        Args:
            base_url: Root URL of the Immich server. Either the bare host
                (``https://host``) or the API root (``https://host/api``)
                is accepted; the ``/api`` suffix is appended if missing.
            api_key: API key used for the ``x-api-key`` header.
            verify_tls: Verify TLS certificates. Disable only for dev.
            timeout: Default HTTP timeout in seconds.
        """
        self.base_url = self._normalise_base_url(base_url)
        self.api_key = api_key
        self.verify_tls = verify_tls
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "x-api-key": api_key,
                "accept": "application/json",
            },
            verify=verify_tls,
            timeout=timeout,
        )

    # ---- construction helpers -------------------------------------------

    @classmethod
    def from_env(cls) -> "ImmichClient":
        """Build a client from ``PYMMICH_URL``/``PYMMICH_API_KEY`` env vars.

        Raises:
            ImmichError: If any of the required env vars is missing.
        """
        url = os.environ.get("PYMMICH_URL")
        api_key = os.environ.get("PYMMICH_API_KEY")
        if not url:
            raise ImmichError(
                "PYMMICH_URL environment variable is not set. "
                "Set it to the base URL of your Immich server."
            )
        if not api_key:
            raise ImmichError(
                "PYMMICH_API_KEY environment variable is not set. "
                "Create an API key in the Immich web UI (Account → API Keys)."
            )
        verify = os.environ.get("PYMMICH_VERIFY_TLS", "1") not in ("0", "false", "no")
        return cls(base_url=url, api_key=api_key, verify_tls=verify)

    @staticmethod
    def _normalise_base_url(url: str) -> str:
        """Strip a trailing slash and append ``/api`` if not already there."""
        url = url.rstrip("/")
        if not url.endswith("/api"):
            url = url + "/api"
        return url

    # ---- context manager ------------------------------------------------

    def __enter__(self) -> "ImmichClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http is not None:
            self._http.close()
            self._http = None

    # ---- low-level HTTP helpers -----------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a request and raise ``ImmichError`` on transport/HTTP errors."""
        assert self._http is not None, "ImmichClient has been closed"
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ImmichError(f"HTTP request failed: {exc}") from exc
        if response.status_code >= 400:
            body = response.text
            raise ImmichError(
                f"Immich API error {response.status_code} on "
                f"{method} {path}: {body}"
            )
        return response

    # ---- server info ----------------------------------------------------

    def ping(self) -> None:
        """Ping the server. Raises ``ImmichError`` on failure."""
        self._request("GET", "/server/ping")

    def get_supported_media_types(self) -> MediaTypes:
        """Return the media types the server accepts on upload."""
        data = self._request("GET", "/server/media-types").json()
        return MediaTypes(
            image=list(data.get("image", [])),
            video=list(data.get("video", [])),
            sidecar=list(data.get("sidecar", [])),
        )

    # ---- albums ---------------------------------------------------------

    def list_albums(self, *, shared: bool | None = None) -> list[Album]:
        """List albums visible to the authenticated user.

        Args:
            shared: Controls which albums the server returns:

                * ``None`` (default) — only albums owned by the user
                  (matches ``GET /albums`` without a ``shared`` param).
                * ``True`` — albums owned by the user **and** albums
                  shared with the user.
                * ``False`` — only owned albums that are not shared.
        """
        params: dict[str, str] = {}
        if shared is True:
            params["shared"] = "true"
        elif shared is False:
            params["shared"] = "false"
        data = self._request("GET", "/albums", params=params).json()
        return [Album.from_api(item) for item in data]

    def create_album(self, name: str, description: str = "") -> Album:
        """Create a new album with the given name."""
        payload: dict[str, Any] = {"albumName": name}
        if description:
            payload["description"] = description
        data = self._request("POST", "/albums", json=payload).json()
        return Album.from_api(data)

    def _list_accessible_albums(self, include_shared: bool) -> list[Album]:
        """Return owned albums, optionally merged with shared-with-me.

        The Immich ``GET /albums`` endpoint cannot return both groups in
        a single call: without ``shared`` it returns all owned albums
        (regardless of whether they're shared), and with ``shared=true``
        it returns "shared" albums (my own shared albums + those shared
        with me + those I have a link for) — which *excludes* my
        personal, unshared albums. To surface every album the caller
        can see, we must issue both requests and merge, de-duplicating
        by album id.
        """
        owned = self.list_albums()
        if not include_shared:
            return owned
        shared = self.list_albums(shared=True)
        seen: set[str] = {a.id for a in owned}
        merged: list[Album] = list(owned)
        for album in shared:
            if album.id in seen:
                continue
            merged.append(album)
            seen.add(album.id)
        return merged

    def find_album(
        self,
        name: str,
        *,
        case_sensitive: bool = False,
        include_shared: bool = True,
    ) -> Album | None:
        """Return the first album whose name matches, or ``None``.

        Args:
            name: Album name to look up.
            case_sensitive: If true, match names exactly; otherwise
                compare casefolded names.
            include_shared: If true (default), also consider albums
                shared with the authenticated user, not just owned ones.
        """
        albums = self._list_accessible_albums(include_shared=include_shared)
        if case_sensitive:
            for album in albums:
                if album.album_name == name:
                    return album
            return None
        folded = name.casefold()
        for album in albums:
            if album.album_name.casefold() == folded:
                return album
        return None

    def ensure_album(
        self,
        name: str,
        *,
        case_sensitive: bool = False,
        include_shared: bool = True,
    ) -> Album:
        """Find an album with this name, creating it if missing.

        When a new album has to be created, the ``name`` argument is used
        verbatim so the album picks up the same spelling the caller passed.
        The ``include_shared`` argument is forwarded to :meth:`find_album`
        so the caller can control whether shared-with-me albums are
        considered before an owned album is created.
        """
        existing = self.find_album(
            name,
            case_sensitive=case_sensitive,
            include_shared=include_shared,
        )
        if existing is not None:
            return existing
        return self.create_album(name)

    def add_assets_to_album(
        self, album_id: str, asset_ids: list[str]
    ) -> list[BulkIdResult]:
        """Add assets to an album; returns a per-asset success/error list."""
        if not asset_ids:
            return []
        data = self._request(
            "PUT",
            f"/albums/{album_id}/assets",
            json={"ids": asset_ids},
        ).json()
        return [
            BulkIdResult(
                id=item["id"],
                success=bool(item.get("success", False)),
                error=item.get("error"),
            )
            for item in data
        ]

    def get_album(self, album_id: str) -> Album:
        """Retrieve detailed info for a single album (including albumUsers)."""
        data = self._request("GET", f"/albums/{album_id}").json()
        return Album.from_api(data)

    def find_albums_matching(
        self,
        patterns: list[str],
        *,
        case_sensitive: bool = False,
        include_shared: bool = True,
    ) -> list[Album]:
        """Return all albums whose name matches any of the given globs.

        Plain names (no glob metacharacters) still work and match exactly
        (modulo case folding). Results are de-duplicated by album id, in
        the order the patterns were given, then by album name.

        Args:
            patterns: Glob patterns and/or literal album names.
            case_sensitive: If true, match names exactly (no case
                folding). Default is case-insensitive, to mirror the
                behaviour of the ``upload``/``download`` commands.
            include_shared: If true (default), also consider albums
                shared with the authenticated user.
        """
        albums = self._list_accessible_albums(include_shared=include_shared)
        seen: set[str] = set()
        matched: list[Album] = []
        for pattern in patterns:
            if case_sensitive:
                pat = pattern
                candidates = [(a.album_name, a) for a in albums]
            else:
                pat = pattern.casefold()
                candidates = [(a.album_name.casefold(), a) for a in albums]
            for name, album in candidates:
                if album.id in seen:
                    continue
                if fnmatch.fnmatchcase(name, pat):
                    matched.append(album)
                    seen.add(album.id)
        return matched

    def add_users_to_album(
        self,
        album_id: str,
        user_ids: list[str],
        *,
        role: str = "editor",
    ) -> Album | None:
        """Share an album with one or more users.

        Args:
            album_id: Album to share.
            user_ids: User ids to add. Empty list is a no-op and
                returns ``None`` without hitting the server.
            role: ``"editor"`` (default) or ``"viewer"``.

        Returns:
            The updated ``Album`` as returned by the server, or ``None``
            if ``user_ids`` was empty.
        """
        if not user_ids:
            return None
        payload = {
            "albumUsers": [
                {"userId": uid, "role": role} for uid in user_ids
            ],
        }
        data = self._request(
            "PUT", f"/albums/{album_id}/users", json=payload
        ).json()
        return Album.from_api(data)

    def remove_user_from_album(self, album_id: str, user_id: str) -> None:
        """Unshare an album from a single user."""
        self._request("DELETE", f"/albums/{album_id}/user/{user_id}")

    # ---- users ----------------------------------------------------------

    def list_users(self) -> list[User]:
        """List all users visible to the authenticated user."""
        data = self._request("GET", "/users").json()
        return [User.from_api(item) for item in data]

    def find_users_matching(
        self,
        patterns: list[str],
        *,
        case_sensitive: bool = False,
    ) -> list[User]:
        """Return all users whose name or email matches any pattern.

        Args:
            patterns: Glob patterns and/or literal substrings. An empty
                list returns every user the server exposes.
            case_sensitive: Match case-exactly when true. Default is
                case-insensitive.

        A pattern with glob metacharacters (``*``, ``?``, ``[``) is
        matched with :func:`fnmatch.fnmatchcase` against the name and
        email. A plain string is matched as a substring of either field
        — handy for e.g. filtering by email domain.

        Results are de-duplicated by user id, preserving the order the
        user list was returned in.
        """
        users = self.list_users()
        if not patterns:
            return users

        seen: set[str] = set()
        matched: list[User] = []
        for pattern in patterns:
            if case_sensitive:
                needle = pattern
                has_glob = any(ch in pattern for ch in "*?[")
            else:
                needle = pattern.casefold()
                has_glob = any(ch in pattern for ch in "*?[")

            for user in users:
                if user.id in seen:
                    continue
                name = user.name if case_sensitive else user.name.casefold()
                email = user.email if case_sensitive else user.email.casefold()
                if has_glob:
                    if not (
                        fnmatch.fnmatchcase(name, needle)
                        or fnmatch.fnmatchcase(email, needle)
                    ):
                        continue
                else:
                    if needle not in name and needle not in email:
                        continue
                matched.append(user)
                seen.add(user.id)
        return matched

    def find_user(self, identifier: str) -> User | None:
        """Look up a user by email or name (case-insensitive).

        Emails are checked first because they are unique; an ambiguous
        email match would indicate a server-side data problem and we
        let such a conflict propagate as an error. Name matches are
        only considered when no user's email matches; if more than one
        user has the same name, ``ImmichError`` is raised so the caller
        can disambiguate by email.
        """
        ident = identifier.casefold()
        users = self.list_users()

        email_matches = [u for u in users if u.email.casefold() == ident]
        if len(email_matches) == 1:
            return email_matches[0]
        if len(email_matches) > 1:
            raise ImmichError(
                f"User identifier {identifier!r} matches "
                f"{len(email_matches)} users by email."
            )

        name_matches = [u for u in users if u.name.casefold() == ident]
        if len(name_matches) == 1:
            return name_matches[0]
        if len(name_matches) > 1:
            raise ImmichError(
                f"User name {identifier!r} is ambiguous; it matches "
                f"{len(name_matches)} users. Use the email address instead."
            )

        return None

    # ---- assets ---------------------------------------------------------

    def upload_asset(
        self,
        path: Path,
        *,
        is_favorite: bool = False,
    ) -> UploadResult:
        """Upload a single file as an Immich asset.

        Args:
            path: Path to the file to upload.
            is_favorite: Mark the asset as a favourite after upload.

        Returns:
            The server-assigned asset id together with the upload status
            (``created``, ``replaced`` or ``duplicate``).
        """
        stat = path.stat()
        created = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.UTC)
        modified = created
        data = {
            "deviceAssetId": f"{path.name}-{int(stat.st_mtime)}-{stat.st_size}",
            "deviceId": "pymmich",
            # Must match the regex `...(:\.\d+)?Z$` the server enforces.
            # datetime.isoformat() yields microseconds when st_mtime has
            # subseconds, which combined with a naive .replace() would
            # produce an invalid "...22.123456.000Z" string.
            "fileCreatedAt": _isoformat_z(created),
            "fileModifiedAt": _isoformat_z(modified),
            "isFavorite": "true" if is_favorite else "false",
        }
        mime, _ = mimetypes.guess_type(path.name)
        mime = mime or "application/octet-stream"
        with path.open("rb") as fh:
            files = {"assetData": (path.name, fh, mime)}
            assert self._http is not None, "ImmichClient has been closed"
            try:
                response = self._http.post(
                    "/assets",
                    data=data,
                    files=files,
                    timeout=UPLOAD_TIMEOUT,
                )
            except httpx.HTTPError as exc:
                raise ImmichError(f"Upload of {path} failed: {exc}") from exc
        if response.status_code not in (200, 201):
            raise ImmichError(
                f"Upload of {path} failed with status "
                f"{response.status_code}: {response.text}"
            )
        body = response.json()
        return UploadResult(id=body["id"], status=body["status"])

    def get_asset_info(self, asset_id: str) -> AssetInfo:
        """Fetch detailed metadata for a single asset."""
        data = self._request("GET", f"/assets/{asset_id}").json()
        return AssetInfo.from_api(data)

    def download_asset(self, asset_id: str, dest: Path) -> None:
        """Download the original file of an asset to ``dest``.

        The destination directory must already exist. The file is written
        through a temporary file that is renamed on success, so partial
        downloads don't leave half-written files behind.
        """
        assert self._http is not None, "ImmichClient has been closed"
        tmp = dest.with_name(dest.name + ".part")
        try:
            with self._http.stream(
                "GET",
                f"/assets/{asset_id}/original",
                timeout=DOWNLOAD_TIMEOUT,
            ) as response:
                if response.status_code >= 400:
                    raise ImmichError(
                        f"Download of asset {asset_id} failed with status "
                        f"{response.status_code}: {response.text}"
                    )
                with tmp.open("wb") as fh:
                    for chunk in response.iter_bytes():
                        fh.write(chunk)
        except httpx.HTTPError as exc:
            if tmp.exists():
                tmp.unlink()
            raise ImmichError(f"Download of asset {asset_id} failed: {exc}") from exc
        tmp.replace(dest)

    # ---- search ---------------------------------------------------------

    def _search_metadata(
        self,
        filters: dict[str, Any],
        *,
        limit: int | None = None,
    ) -> Iterator[AssetInfo]:
        """Iterate over all assets matching the given metadata filters.

        The Immich search endpoint is paginated via ``page``/``nextPage``
        tokens; this helper transparently fetches all pages, stopping
        early once ``limit`` results have been yielded.
        """
        page = 1
        yielded = 0
        while True:
            payload = dict(filters)
            payload.setdefault("size", SEARCH_PAGE_SIZE)
            payload["page"] = page
            data = self._request(
                "POST", "/search/metadata", json=payload
            ).json()
            assets = data.get("assets", {})
            for item in assets.get("items", []):
                yield AssetInfo.from_api(item)
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            next_page = assets.get("nextPage")
            if not next_page:
                break
            try:
                page = int(next_page)
            except (TypeError, ValueError):
                # Server returned a non-numeric next-page token we cannot
                # use with our paging scheme; stop rather than loop forever.
                break

    def count_assets(
        self,
        *,
        since: dt.datetime | None = None,
        until: dt.datetime | None = None,
    ) -> int:
        """Return the server's reported total asset count for the given
        ``takenAfter`` / ``takenBefore`` range.

        Uses a minimal ``/search/metadata`` call (``size=1``) and reads
        the ``total`` field from the response. Subject to the same
        owner-scope limitations as :meth:`list_all_assets`.
        """
        payload: dict[str, Any] = {"size": 1, "page": 1}
        if since is not None:
            payload["takenAfter"] = _isoformat_z(since)
        if until is not None:
            payload["takenBefore"] = _isoformat_z(until)
        data = self._request(
            "POST", "/search/metadata", json=payload
        ).json()
        return int(data.get("assets", {}).get("total", 0))

    def list_all_assets(
        self,
        *,
        since: dt.datetime | None = None,
        until: dt.datetime | None = None,
        limit: int | None = None,
        order: str = "desc",
    ) -> Iterator[AssetInfo]:
        """Yield all assets visible to the authenticated user.

        Args:
            since: If given, only yield assets taken on or after this
                datetime (maps to ``takenAfter``).
            until: If given, only yield assets taken before this
                datetime (maps to ``takenBefore``).
            limit: Maximum number of assets to yield. The server is
                asked for at most ``min(limit, SEARCH_PAGE_SIZE)``
                items per page, and pagination stops as soon as enough
                results have been collected.
            order: ``"desc"`` (default, most-recent first) or ``"asc"``.

        Note:
            Uses ``/search/metadata`` under the hood, which the Immich
            server forcibly scopes to assets owned by the caller (and
            the caller's partners). Assets contributed by other users
            to albums shared with the caller will not appear unless
            they're queried through a specific album.
        """
        filters: dict[str, Any] = {"order": order}
        if since is not None:
            filters["takenAfter"] = _isoformat_z(since)
        if until is not None:
            filters["takenBefore"] = _isoformat_z(until)
        if limit is not None and limit < SEARCH_PAGE_SIZE:
            filters["size"] = max(1, limit)
        yield from self._search_metadata(filters, limit=limit)

    def search_assets_by_album(self, album_id: str) -> Iterator[AssetInfo]:
        """Yield all assets contained in the given album.

        Uses the ``/timeline/buckets`` + ``/timeline/bucket`` endpoints
        rather than ``/search/metadata``. The search endpoint forcibly
        filters results to assets owned by the authenticated user (and
        their partners), which hides contributions from other members
        of a shared album — the common "someone shared their photos
        with me in an album" scenario. The timeline endpoints, when
        given an ``albumId`` filter, return every asset in the album
        regardless of owner.

        The timeline bucket payload is columnar and does not include
        the ``originalFileName`` needed for download, so we fetch full
        info for each id via ``GET /assets/{id}``.
        """
        buckets = self._request(
            "GET",
            "/timeline/buckets",
            params={"albumId": album_id},
        ).json()
        for bucket in buckets:
            time_bucket = bucket.get("timeBucket")
            if not time_bucket:
                continue
            data = self._request(
                "GET",
                "/timeline/bucket",
                params={
                    "albumId": album_id,
                    "timeBucket": time_bucket,
                },
            ).json()
            for asset_id in data.get("id", []):
                yield self.get_asset_info(asset_id)

    def search_assets_by_filename(self, filename: str) -> Iterator[AssetInfo]:
        """Yield assets whose original filename matches ``filename``.

        The server does a substring match on ``originalFileName``; the
        caller is expected to apply any more precise glob filtering
        client-side.
        """
        yield from self._search_metadata({"originalFileName": filename})
