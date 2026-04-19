"""Command-line interface for pymmich.

Exposes two commands — ``upload`` and ``download`` — through typer.
Both commands read the server URL and API key from environment
variables (``PYMMICH_URL`` and ``PYMMICH_API_KEY``) and fail with a
clear error message if they are missing.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import fnmatch
import json as _json
import os
import sys
from pathlib import Path
from typing import Iterator

import typer
from rich.console import Console
from rich.table import Table

from pymmich import __version__
from pymmich.client import (
    Album,
    AssetInfo,
    ImmichClient,
    ImmichError,
    MediaTypes,
    User,
)


class AlbumUserRole(str, enum.Enum):
    """Role used by the ``share`` command when adding users."""

    editor = "editor"
    viewer = "viewer"


class ListFormat(str, enum.Enum):
    """Output format for the ``list`` command."""

    table = "table"
    long = "long"
    json = "json"


@dataclasses.dataclass
class ListEntry:
    """A single row in the output of ``pymmich list``."""

    kind: str  # "album" or "asset"
    id: str
    name: str
    date: dt.datetime | None = None
    asset_count: int | None = None  # only populated for albums

    def to_json(self) -> dict:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "date": self.date.isoformat() if self.date else None,
            "assetCount": self.asset_count,
        }


@dataclasses.dataclass
class ListResult:
    """Collected entries plus per-kind totals for the footer line."""

    entries: list[ListEntry]
    total_albums: int = 0
    total_assets: int = 0

    @property
    def total(self) -> int:
        return self.total_albums + self.total_assets


DEFAULT_LIST_LIMIT = 50


app = typer.Typer(
    name="pymmich",
    help="Upload/download folders and files to/from an Immich server.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"pymmich {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the pymmich version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Top-level pymmich entry point."""


# ---- helpers ------------------------------------------------------------


def _make_client() -> ImmichClient:
    """Build a client from env vars, exiting cleanly on missing config."""
    try:
        return ImmichClient.from_env()
    except ImmichError as exc:
        typer.echo(f"pymmich: {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _collect_media_files(
    path: Path,
    allowed_exts: set[str],
    recursive: bool,
) -> list[Path]:
    """Return every media file directly (or recursively) under ``path``."""
    if path.is_file():
        return [path] if path.suffix.lower() in allowed_exts else []
    if not path.is_dir():
        return []
    iterator = path.rglob("*") if recursive else path.iterdir()
    files: list[Path] = []
    for entry in iterator:
        if entry.is_file() and entry.suffix.lower() in allowed_exts:
            files.append(entry)
    files.sort()
    return files


def _next_unique_name(original: str, used: set[str]) -> str:
    """Return the first ``<stem>_N<ext>`` not in ``used`` (N starting at 1).

    If ``original`` is not in ``used``, it is returned unchanged. The
    caller is expected to add the returned name to ``used`` before the
    next lookup.
    """
    if original not in used:
        return original
    stem, dot, ext = original.rpartition(".")
    if not dot:
        stem, ext = original, ""
    else:
        ext = "." + ext
    n = 1
    while True:
        candidate = f"{stem}_{n}{ext}"
        if candidate not in used:
            return candidate
        n += 1


def _set_file_mtime(path: Path, when: dt.datetime) -> None:
    """Set ``atime`` and ``mtime`` of ``path`` to ``when``."""
    ts = when.timestamp()
    os.utime(path, (ts, ts))


# ---- upload --------------------------------------------------------------


@app.command()
def upload(
    paths: list[Path] = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Files and/or directories to upload.",
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive",
        "-r",
        help="Recurse into subdirectories when scanning a directory.",
    ),
    album: str = typer.Option(
        None,
        "--album",
        "-a",
        help=(
            "Upload every input (files and files found in directories) "
            "into this single target album, ignoring per-directory album "
            "creation."
        ),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help=(
            "Allow existing filenames on the server to be overwritten. "
            "Default: rename the incoming file with a numbered suffix "
            "(foo.jpg -> foo_1.jpg) to keep both files distinct."
        ),
    ),
    case_sensitive: bool = typer.Option(
        False,
        "--case-sensitive/--case-insensitive",
        "-s/-i",
        help=(
            "Match directory names to album names case-sensitively "
            "(off by default). Pass -i or --case-insensitive to force "
            "the default."
        ),
    ),
    only_owned: bool = typer.Option(
        False,
        "--only-owned",
        help=(
            "Only consider albums you own when matching the target "
            "album; otherwise pymmich also looks at albums shared with "
            "you (server-side ?shared=true)."
        ),
    ),
) -> None:
    """Upload files and directories to Immich.

    Directories are uploaded as albums (created if missing); individual
    files are uploaded without album association unless ``--album`` is
    set, in which case every input goes into that album.
    """
    include_shared = not only_owned
    with _make_client() as client:
        try:
            media_types = client.get_supported_media_types()
        except ImmichError as exc:
            typer.echo(f"pymmich: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        allowed = media_types.all_extensions
        total_uploaded = 0
        total_skipped = 0

        # Cache of filename->bool "this name already exists on the server
        # for the current user" for non-album uploads. Populated lazily.
        global_name_cache: dict[str, bool] = {}

        if album is not None:
            # Single target album for everything: resolve (or create) it
            # once and collect all media files up-front.
            try:
                target_album = client.ensure_album(
                    album,
                    case_sensitive=case_sensitive,
                    include_shared=include_shared,
                )
            except ImmichError as exc:
                typer.echo(
                    f"pymmich: failed to prepare album {album!r}: {exc}",
                    err=True,
                )
                raise typer.Exit(code=1) from exc

            used_names = _album_used_names(client, target_album.id)
            files: list[Path] = []
            for path in paths:
                if path.is_file():
                    if path.suffix.lower() not in allowed:
                        typer.echo(
                            f"Skipping {path}: unsupported extension", err=True
                        )
                        total_skipped += 1
                        continue
                    files.append(path)
                elif path.is_dir():
                    files.extend(_collect_media_files(path, allowed, recursive))
                else:
                    typer.echo(
                        f"Skipping {path}: not a file or directory", err=True
                    )

            if files:
                typer.echo(
                    f"Uploading {len(files)} file(s) to album "
                    f"{target_album.album_name!r}"
                )
                asset_ids = _upload_files_to_album(
                    client, files, used_names, force=force
                )
                total_uploaded += len(asset_ids)
                if asset_ids:
                    _add_to_album_or_exit(client, target_album, asset_ids)

            typer.echo(
                f"Done: uploaded {total_uploaded} file(s), "
                f"skipped {total_skipped} unsupported file(s)."
            )
            return

        # Default: per-path album logic; standalone files go unassociated.
        for path in paths:
            if path.is_file():
                if path.suffix.lower() not in allowed:
                    typer.echo(
                        f"Skipping {path}: unsupported extension", err=True
                    )
                    total_skipped += 1
                    continue
                _upload_standalone(client, path, global_name_cache, force=force)
                total_uploaded += 1
                continue

            if not path.is_dir():
                typer.echo(f"Skipping {path}: not a file or directory", err=True)
                continue

            files = _collect_media_files(path, allowed, recursive)
            if not files:
                typer.echo(f"No media files found in {path}, skipping album.")
                continue

            album_name = path.name
            try:
                dir_album = client.ensure_album(
                    album_name,
                    case_sensitive=case_sensitive,
                    include_shared=include_shared,
                )
            except ImmichError as exc:
                typer.echo(
                    f"pymmich: failed to prepare album {album_name!r}: {exc}",
                    err=True,
                )
                raise typer.Exit(code=1) from exc

            used_names = _album_used_names(client, dir_album.id)
            typer.echo(
                f"Uploading {len(files)} file(s) to album {dir_album.album_name!r}"
            )
            asset_ids = _upload_files_to_album(
                client, files, used_names, force=force
            )
            total_uploaded += len(asset_ids)
            if asset_ids:
                _add_to_album_or_exit(client, dir_album, asset_ids)

        typer.echo(
            f"Done: uploaded {total_uploaded} file(s), "
            f"skipped {total_skipped} unsupported file(s)."
        )


def _album_used_names(client: ImmichClient, album_id: str) -> set[str]:
    """Return the set of original filenames already present in ``album_id``."""
    try:
        return {
            a.original_file_name
            for a in client.search_assets_by_album(album_id)
        }
    except ImmichError as exc:
        typer.echo(
            f"pymmich: failed to read existing album contents: {exc}", err=True
        )
        raise typer.Exit(code=1) from exc


def _upload_files_to_album(
    client: ImmichClient,
    files: list[Path],
    used_names: set[str],
    *,
    force: bool,
) -> list[str]:
    """Upload ``files`` into an album, renaming on collision unless ``force``.

    ``used_names`` is mutated in-place to track names already claimed
    during this batch, so two local files with identical names don't
    collide with each other either.
    """
    asset_ids: list[str] = []
    for path in files:
        upload_name = path.name
        if not force and upload_name in used_names:
            upload_name = _next_unique_name(path.name, used_names)
            typer.echo(
                f"pymmich: warning: {path.name!r} already exists in album; "
                f"uploading as {upload_name!r} instead.",
                err=True,
            )
        used_names.add(upload_name)
        try:
            asset_ids.append(_do_upload_file(client, path, upload_name))
        except ImmichError as exc:
            typer.echo(f"pymmich: upload of {path} failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    return asset_ids


def _add_to_album_or_exit(
    client: ImmichClient, album: Album, asset_ids: list[str]
) -> None:
    try:
        client.add_assets_to_album(album.id, asset_ids)
    except ImmichError as exc:
        typer.echo(
            f"pymmich: failed to add assets to album "
            f"{album.album_name!r}: {exc}",
            err=True,
        )
        raise typer.Exit(code=1) from exc


def _upload_standalone(
    client: ImmichClient,
    path: Path,
    cache: dict[str, bool],
    *,
    force: bool,
) -> None:
    """Upload a single file with no album, renaming on global collision."""
    upload_name = path.name
    if not force:
        used: set[str] = set()
        # Materialise just enough filename matches to decide if we collide.
        if upload_name not in cache:
            cache[upload_name] = _server_has_filename(client, upload_name)
        if cache[upload_name]:
            used.add(upload_name)
            # Probe sibling names the same way, lazily, until a free one
            # shows up. The probe cost is at most O(collisions).
            stem, dot, ext = upload_name.rpartition(".")
            if not dot:
                stem, ext = upload_name, ""
            else:
                ext = "." + ext
            n = 1
            while True:
                cand = f"{stem}_{n}{ext}"
                if cand not in cache:
                    cache[cand] = _server_has_filename(client, cand)
                if not cache[cand]:
                    upload_name = cand
                    break
                used.add(cand)
                n += 1
            typer.echo(
                f"pymmich: warning: {path.name!r} already exists on the "
                f"server; uploading as {upload_name!r} instead.",
                err=True,
            )
        # Mark the chosen name as taken so the next standalone upload in
        # this batch doesn't pick it again.
        cache[upload_name] = True
    _do_upload_file(client, path, upload_name)


def _server_has_filename(client: ImmichClient, filename: str) -> bool:
    """Return True if any of the caller's assets already has this filename."""
    try:
        for asset in client.search_assets_by_filename(filename):
            if asset.original_file_name == filename:
                return True
    except ImmichError as exc:
        typer.echo(f"pymmich: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    return False


def _do_upload_file(
    client: ImmichClient, path: Path, filename: str | None = None
) -> str:
    """Upload a single file, print a status line, return its asset id."""
    label = filename if filename and filename != path.name else str(path)
    if filename and filename != path.name:
        typer.echo(f"  + {path} -> {filename}")
    else:
        typer.echo(f"  + {label}")
    result = client.upload_asset(path, filename=filename)
    return result.id


# ---- download ------------------------------------------------------------


@app.command()
def download(
    targets: list[str] = typer.Argument(
        ...,
        help=(
            "Album names or filename glob patterns to download. "
            "Each argument is tried as an album name first and, if no album "
            "matches, as a filename glob."
        ),
    ),
    dir: Path = typer.Option(
        Path("."),
        "--dir",
        "-d",
        help="Local directory to download into (default: current dir).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help=(
            "Overwrite pre-existing local files. Default: rename the "
            "incoming file with a numbered suffix (foo.jpg -> foo_1.jpg) "
            "so no existing file is lost."
        ),
    ),
    case_sensitive: bool = typer.Option(
        False,
        "--case-sensitive/--case-insensitive",
        "-s/-i",
        help=(
            "Match album names case-sensitively (off by default). Pass "
            "-i or --case-insensitive to force the default."
        ),
    ),
    only_owned: bool = typer.Option(
        False,
        "--only-owned",
        help=(
            "Only consider albums you own; otherwise pymmich also looks at "
            "albums shared with you (server-side ?shared=true)."
        ),
    ),
) -> None:
    """Download albums or individual assets from Immich.

    Albums are materialised as directories under ``--dir``; filename
    globs are downloaded flat into ``--dir``.
    """
    dir.mkdir(parents=True, exist_ok=True)
    include_shared = not only_owned

    with _make_client() as client:
        matched_any = False

        for target in targets:
            album = client.find_album(
                target,
                case_sensitive=case_sensitive,
                include_shared=include_shared,
            )
            if album is not None:
                _download_album(client, album, dir, force=force)
                matched_any = True
                continue

            assets = list(_match_assets_by_glob(client, target))
            if not assets:
                typer.echo(
                    f"pymmich: no match for {target!r} "
                    f"(neither an album nor a matching filename).",
                    err=True,
                )
                continue

            for asset in assets:
                _download_asset(client, asset, dir, force=force)
            matched_any = True

        if not matched_any:
            typer.echo("pymmich: no matching albums or assets found.", err=True)
            raise typer.Exit(code=1)


def _match_assets_by_glob(
    client: ImmichClient, pattern: str
) -> list[AssetInfo]:
    """Return assets whose original filename matches the glob ``pattern``."""
    # The server's originalFileName filter is a substring match; we strip
    # glob metacharacters to get a usable search stem, then apply fnmatch
    # client-side to enforce the actual glob semantics.
    stem = pattern
    for ch in "*?[]":
        stem = stem.replace(ch, "")
    # Use casefold match on the client side; the server's search is
    # already case-insensitive in practice.
    folded = pattern.casefold()
    matches: list[AssetInfo] = []
    for asset in client.search_assets_by_filename(stem):
        if fnmatch.fnmatchcase(asset.original_file_name.casefold(), folded):
            matches.append(asset)
    return matches


def _download_album(
    client: ImmichClient, album: Album, root: Path, *, force: bool
) -> None:
    """Download every asset of ``album`` into ``root / album.name``."""
    target_dir = root / album.album_name
    target_dir.mkdir(parents=True, exist_ok=True)
    typer.echo(f"Downloading album {album.album_name!r} to {target_dir}/")

    assets = list(client.search_assets_by_album(album.id))
    if not assets:
        typer.echo(f"  (album {album.album_name!r} is empty)")
        return

    oldest: dt.datetime | None = None
    for asset in assets:
        _download_asset(client, asset, target_dir, force=force)
        if oldest is None or asset.file_created_at < oldest:
            oldest = asset.file_created_at
    if oldest is not None:
        _set_file_mtime(target_dir, oldest)


def _download_asset(
    client: ImmichClient, asset: AssetInfo, target_dir: Path, *, force: bool
) -> None:
    """Download a single asset and stamp its mtime with the asset's date.

    When ``force`` is false and a file with the same name already exists
    in ``target_dir``, the incoming file is renamed with a ``_N`` suffix
    and a warning is printed.
    """
    dest_name = asset.original_file_name
    if not force and (target_dir / dest_name).exists():
        used = {p.name for p in target_dir.iterdir()}
        new_name = _next_unique_name(dest_name, used)
        typer.echo(
            f"pymmich: warning: {dest_name!r} already exists in "
            f"{target_dir}; saving as {new_name!r} instead.",
            err=True,
        )
        dest_name = new_name
    dest = target_dir / dest_name
    if dest_name == asset.original_file_name:
        typer.echo(f"  < {asset.original_file_name}")
    else:
        typer.echo(f"  < {asset.original_file_name} -> {dest_name}")
    client.download_asset(asset.id, dest)
    _set_file_mtime(dest, asset.file_created_at)


# ---- share / unshare ----------------------------------------------------


def _resolve_users(client: ImmichClient, identifiers: list[str]) -> list[User]:
    """Resolve a list of name/email identifiers to ``User`` objects.

    Exits the process with code 1 as soon as any identifier cannot be
    resolved, so no partial work is performed on a typo.
    """
    resolved: list[User] = []
    for ident in identifiers:
        try:
            user = client.find_user(ident)
        except ImmichError as exc:
            typer.echo(f"pymmich: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        if user is None:
            typer.echo(
                f"pymmich: no user found for {ident!r}.", err=True
            )
            raise typer.Exit(code=1)
        resolved.append(user)
    return resolved


def _match_albums_or_exit(
    client: ImmichClient,
    patterns: list[str],
    *,
    case_sensitive: bool,
    include_shared: bool,
) -> list[Album]:
    """Return albums matching any of the given patterns; exit 1 if none."""
    try:
        matched = client.find_albums_matching(
            patterns,
            case_sensitive=case_sensitive,
            include_shared=include_shared,
        )
    except ImmichError as exc:
        typer.echo(f"pymmich: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if not matched:
        typer.echo(
            f"pymmich: no albums matched any of the given patterns: "
            f"{', '.join(repr(p) for p in patterns)}",
            err=True,
        )
        raise typer.Exit(code=1)
    return matched


@app.command()
def share(
    albums: list[str] = typer.Argument(
        ...,
        metavar="ALBUMS...",
        help="Album names or glob patterns to share.",
    ),
    with_: list[str] = typer.Option(
        ...,
        "--with",
        "-w",
        help=(
            "User name or email address to share the album with. "
            "Pass --with multiple times for multiple users."
        ),
    ),
    role: AlbumUserRole = typer.Option(
        AlbumUserRole.editor,
        "--role",
        help="Role to grant to the shared users.",
        case_sensitive=False,
    ),
    case_sensitive: bool = typer.Option(
        False,
        "--case-sensitive/--case-insensitive",
        "-s/-i",
        help=(
            "Match album names case-sensitively (off by default). Pass "
            "-i or --case-insensitive to force the default."
        ),
    ),
    only_owned: bool = typer.Option(
        False,
        "--only-owned",
        help=(
            "Only consider albums you own; otherwise pymmich also looks at "
            "albums shared with you (server-side ?shared=true)."
        ),
    ),
) -> None:
    """Share one or more albums with one or more users."""
    include_shared = not only_owned
    with _make_client() as client:
        users = _resolve_users(client, with_)
        user_ids = [u.id for u in users]

        matched = _match_albums_or_exit(
            client,
            albums,
            case_sensitive=case_sensitive,
            include_shared=include_shared,
        )

        for album in matched:
            typer.echo(
                f"Sharing album {album.album_name!r} with "
                f"{len(users)} user(s) as {role.value}"
            )
            try:
                client.add_users_to_album(
                    album.id, user_ids, role=role.value
                )
            except ImmichError as exc:
                typer.echo(
                    f"pymmich: failed to share {album.album_name!r}: {exc}",
                    err=True,
                )
                raise typer.Exit(code=1) from exc


@app.command()
def unshare(
    albums: list[str] = typer.Argument(
        ...,
        metavar="ALBUMS...",
        help="Album names or glob patterns to unshare.",
    ),
    with_: list[str] = typer.Option(
        ...,
        "--with",
        "-w",
        help=(
            "User name or email address to remove from album sharing. "
            "Pass --with multiple times for multiple users."
        ),
    ),
    case_sensitive: bool = typer.Option(
        False,
        "--case-sensitive/--case-insensitive",
        "-s/-i",
        help=(
            "Match album names case-sensitively (off by default). Pass "
            "-i or --case-insensitive to force the default."
        ),
    ),
    only_owned: bool = typer.Option(
        False,
        "--only-owned",
        help=(
            "Only consider albums you own; otherwise pymmich also looks at "
            "albums shared with you (server-side ?shared=true)."
        ),
    ),
) -> None:
    """Remove one or more users from the sharing list of one or more albums.

    When a requested user is not among the current shared users of a
    matched album, a warning is printed but the command continues and
    exits with status 0.
    """
    include_shared = not only_owned
    with _make_client() as client:
        users = _resolve_users(client, with_)
        matched = _match_albums_or_exit(
            client,
            albums,
            case_sensitive=case_sensitive,
            include_shared=include_shared,
        )

        for album in matched:
            # Fetch full album info to see the current shared users;
            # list_albums() does not return albumUsers.
            try:
                full = client.get_album(album.id)
            except ImmichError as exc:
                typer.echo(
                    f"pymmich: failed to read album {album.album_name!r}: "
                    f"{exc}",
                    err=True,
                )
                raise typer.Exit(code=1) from exc

            shared_ids = {au.user.id for au in full.album_users}
            for user in users:
                if user.id not in shared_ids:
                    typer.echo(
                        f"pymmich: warning: {user.email or user.name!r} is "
                        f"not shared on album {album.album_name!r}; "
                        f"skipping.",
                        err=True,
                    )
                    continue
                typer.echo(
                    f"Unsharing album {album.album_name!r} from "
                    f"{user.email or user.name!r}"
                )
                try:
                    client.remove_user_from_album(album.id, user.id)
                except ImmichError as exc:
                    typer.echo(
                        f"pymmich: failed to unshare {album.album_name!r}: "
                        f"{exc}",
                        err=True,
                    )
                    raise typer.Exit(code=1) from exc


# ---- list --------------------------------------------------------------


def _parse_date(value: str, *, option_name: str) -> dt.datetime:
    """Parse a ``YYYY-MM-DD`` (or full ISO) string to a UTC datetime.

    Exits with an error if the string doesn't parse.
    """
    # Accept both plain date and full ISO-8601.
    for parser in (
        lambda v: dt.datetime.fromisoformat(v),
        lambda v: dt.datetime.strptime(v, "%Y-%m-%d"),
    ):
        try:
            parsed = parser(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.UTC)
            return parsed.astimezone(dt.UTC)
        except ValueError:
            continue
    typer.echo(
        f"pymmich: {option_name} value {value!r} is not a valid date "
        "(expected YYYY-MM-DD or ISO-8601).",
        err=True,
    )
    raise typer.Exit(code=2)


def _album_entry(album: Album) -> ListEntry:
    return ListEntry(
        kind="album",
        id=album.id,
        name=album.album_name,
        date=None,
        asset_count=album.asset_count,
    )


def _asset_entry(asset: AssetInfo) -> ListEntry:
    return ListEntry(
        kind="asset",
        id=asset.id,
        name=asset.original_file_name,
        date=asset.file_created_at,
        asset_count=None,
    )


def _render_table(entries: list[ListEntry]) -> None:
    table = Table(
        show_header=True,
        header_style="bold",
        title=None,
        expand=False,
    )
    table.add_column("Type", style="cyan", no_wrap=True)
    table.add_column("Name", overflow="fold")
    table.add_column("Date", style="dim", no_wrap=True)
    table.add_column("Count/Id", style="dim", no_wrap=True)

    for entry in entries:
        kind = "ALBUM" if entry.kind == "album" else "ASSET"
        date_str = entry.date.strftime("%Y-%m-%d") if entry.date else "-"
        tail = (
            f"{entry.asset_count} assets"
            if entry.asset_count is not None
            else entry.id[:8]
        )
        table.add_row(kind, entry.name, date_str, tail)

    console = Console()
    console.print(table)


def _render_long(entries: list[ListEntry]) -> None:
    """``ls -l`` style: one header line, then one line per entry.

    Columns are: TYPE (3-char tag), COUNT (asset count for albums,
    ``-`` for assets), DATE (YYYY-MM-DD HH:MM), NAME.
    """
    typer.echo(f"{'TYPE':<4}  {'COUNT':>6}  {'DATE':<16}  NAME")
    for entry in entries:
        kind = "ALB" if entry.kind == "album" else "AST"
        date_str = (
            entry.date.strftime("%Y-%m-%d %H:%M")
            if entry.date
            else "-"
        )
        size = (
            f"{entry.asset_count:>6d}"
            if entry.asset_count is not None
            else f"{'-':>6}"
        )
        typer.echo(f"{kind:<4}  {size}  {date_str:<16}  {entry.name}")


def _render_json(entries: list[ListEntry]) -> None:
    """Newline-delimited JSON: one object per line."""
    for entry in entries:
        typer.echo(_json.dumps(entry.to_json()))


def _footer_text(result: ListResult) -> str:
    """Build the trailing status line ('showing X of Y ...' or 'Y ... in total').

    The wording adapts to whether the result is albums, assets, or
    both. When the number of collected entries equals the total, the
    'showing X of Y' form collapses to 'Y in total'.
    """
    shown = len(result.entries)
    total = result.total
    shown_albums = sum(1 for e in result.entries if e.kind == "album")
    shown_assets = shown - shown_albums

    def _kind_phrase(n_alb: int, n_ast: int) -> str:
        # Produce a human-readable "A albums / B assets / both" phrase.
        parts: list[str] = []
        if n_alb:
            parts.append(f"{n_alb} album{'s' if n_alb != 1 else ''}")
        if n_ast:
            parts.append(f"{n_ast} asset{'s' if n_ast != 1 else ''}")
        if not parts:
            return "0 items"
        return " and ".join(parts)

    if shown >= total:
        # Everything that exists is visible.
        return f"{_kind_phrase(result.total_albums, result.total_assets)} in total"
    return (
        f"showing {shown} of "
        f"{_kind_phrase(result.total_albums, result.total_assets)} "
        f"({_kind_phrase(shown_albums, shown_assets)} shown)"
    )


def _render(result: ListResult, fmt: ListFormat) -> None:
    if fmt is ListFormat.table:
        _render_table(result.entries)
    elif fmt is ListFormat.long:
        _render_long(result.entries)
    else:
        _render_json(result.entries)

    # Footer on stderr so stdout stays pure data for scripts.
    typer.echo(_footer_text(result), err=True)


def _collect_list_entries(
    client: ImmichClient,
    *,
    targets: list[str],
    albums_only: bool,
    assets_only: bool,
    include_shared: bool,
    only_shared: bool,
    case_sensitive: bool,
    since: dt.datetime | None,
    until: dt.datetime | None,
    limit: int | None,
) -> ListResult:
    """Build the list of entries (plus totals) for ``pymmich list``.

    With no targets:
        * Albums first, sorted by ``end_date`` DESC (then by name), up
          to ``limit``; then assets DESC by ``file_created_at``.
        * ``--albums-only`` / ``--assets-only`` suppress the other kind.
    With targets:
        * Each target is tried first as an album name glob (unless
          ``assets_only``); if nothing matches, as a filename glob
          (unless ``albums_only``).
    """
    entries: list[ListEntry] = []
    total_albums = 0
    total_assets = 0

    want_albums = not assets_only
    want_assets = not albums_only

    # Only fetch the album list when we're actually going to use it.
    need_albums = want_albums and (bool(targets) or not assets_only)
    album_list: list[Album] = []
    if need_albums:
        if only_shared:
            album_list = client.list_albums(shared=True)
        elif include_shared:
            album_list = client._list_accessible_albums(include_shared=True)
        else:
            album_list = client.list_albums()

    if not targets:
        # ---- default listing: albums + assets ---------------------
        if want_albums:
            sorted_albums = sorted(
                album_list,
                key=lambda a: (
                    a.end_date or dt.datetime.min.replace(tzinfo=dt.UTC),
                    a.album_name.casefold(),
                ),
                reverse=True,
            )
            total_albums = len(sorted_albums)
            album_budget = limit if limit is not None else len(sorted_albums)
            for album in sorted_albums[:album_budget]:
                entries.append(_album_entry(album))

        if want_assets:
            try:
                total_assets = client.count_assets(since=since, until=until)
            except ImmichError as exc:
                typer.echo(f"pymmich: {exc}", err=True)
                raise typer.Exit(code=1) from exc

            asset_budget: int | None
            if limit is None:
                asset_budget = None
            else:
                asset_budget = max(0, limit - len(entries))

            if asset_budget is None or asset_budget > 0:
                for asset in client.list_all_assets(
                    since=since, until=until, limit=asset_budget
                ):
                    entries.append(_asset_entry(asset))

        return ListResult(
            entries=entries,
            total_albums=total_albums,
            total_assets=total_assets,
        )

    # ---- target-based listing ------------------------------------
    matched_any = False
    for target in targets:
        target_entries: list[ListEntry] = []

        if want_albums:
            albums = _match_albums_in_list(
                album_list, target, case_sensitive=case_sensitive
            )
            for album in albums:
                target_entries.append(_album_entry(album))
                total_albums += 1
                matched_any = True
                if albums_only:
                    continue
                for asset in client.search_assets_by_album(album.id):
                    if _asset_in_range(asset, since, until):
                        target_entries.append(_asset_entry(asset))
                        total_assets += 1

        if want_assets and not target_entries:
            has_glob = any(ch in target for ch in "*?[")
            pattern = target.casefold() if not case_sensitive else target
            for asset in client.search_assets_by_filename(target):
                if has_glob:
                    name = (
                        asset.original_file_name.casefold()
                        if not case_sensitive
                        else asset.original_file_name
                    )
                    if not fnmatch.fnmatchcase(name, pattern):
                        continue
                if not _asset_in_range(asset, since, until):
                    continue
                target_entries.append(_asset_entry(asset))
                total_assets += 1
                matched_any = True

        entries.extend(target_entries)

    if not matched_any:
        typer.echo(
            f"pymmich: no matches for any of the given patterns: "
            f"{', '.join(repr(t) for t in targets)}",
            err=True,
        )
        raise typer.Exit(code=1)

    # With targets, we've already materialised everything that matches,
    # so the totals are the lengths of the collected entry kinds, and
    # limit is a display cap only.
    truncated = _truncate(entries, limit)
    return ListResult(
        entries=truncated,
        total_albums=total_albums,
        total_assets=total_assets,
    )


def _match_albums_in_list(
    albums: list[Album], pattern: str, *, case_sensitive: bool
) -> list[Album]:
    """Filter an already-fetched album list by a glob pattern."""
    if case_sensitive:
        return [a for a in albums if fnmatch.fnmatchcase(a.album_name, pattern)]
    folded = pattern.casefold()
    return [
        a for a in albums
        if fnmatch.fnmatchcase(a.album_name.casefold(), folded)
    ]


def _asset_in_range(
    asset: AssetInfo,
    since: dt.datetime | None,
    until: dt.datetime | None,
) -> bool:
    """Return True when ``asset`` falls within the optional [since, until)."""
    if since is not None and asset.file_created_at < since:
        return False
    if until is not None and asset.file_created_at >= until:
        return False
    return True


def _apply_date_filter_albums(
    albums: list[Album],
    since: dt.datetime | None,
    until: dt.datetime | None,
) -> list[Album]:
    """Album list endpoints don't return per-album dates we can filter
    on — pass-through for now so ``--since``/``--until`` don't silently
    drop albums."""
    return albums


def _truncate(entries: list[ListEntry], limit: int | None) -> list[ListEntry]:
    if limit is None or limit <= 0:
        return entries
    return entries[:limit]


@app.command("list-users")
def list_users(
    patterns: list[str] = typer.Argument(
        None,
        metavar="[PATTERNS...]",
        help=(
            "Optional name or email glob patterns. With no patterns, "
            "all users available for sharing are listed. A pattern "
            "with glob chars (*, ?, []) is matched case-sensitively "
            "against name or email; a plain string is matched as a "
            "substring of either field."
        ),
    ),
    fmt: ListFormat = typer.Option(
        ListFormat.table,
        "--format",
        "-f",
        help="Output format.",
        case_sensitive=False,
    ),
    limit: int = typer.Option(
        DEFAULT_LIST_LIMIT,
        "--limit",
        "-n",
        help=(
            f"Return at most this many users. Pass 0 to disable the "
            f"cap. Default: {DEFAULT_LIST_LIMIT}."
        ),
    ),
    case_sensitive: bool = typer.Option(
        False,
        "--case-sensitive/--case-insensitive",
        "-s/-i",
        help=(
            "Match patterns case-sensitively (off by default). Pass "
            "-i or --case-insensitive to force the default."
        ),
    ),
) -> None:
    """List users available for sharing (name + email)."""
    patterns_list = patterns or []
    effective_limit: int | None = limit if limit and limit > 0 else None

    with _make_client() as client:
        try:
            matched = client.find_users_matching(
                patterns_list, case_sensitive=case_sensitive
            )
        except ImmichError as exc:
            typer.echo(f"pymmich: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    if patterns_list and not matched:
        typer.echo(
            f"pymmich: no users matched any of the given patterns: "
            f"{', '.join(repr(p) for p in patterns_list)}",
            err=True,
        )
        raise typer.Exit(code=1)

    total = len(matched)
    shown = matched if effective_limit is None else matched[:effective_limit]

    if fmt is ListFormat.table:
        _render_users_table(shown)
    elif fmt is ListFormat.long:
        _render_users_long(shown)
    else:
        _render_users_json(shown)

    typer.echo(_users_footer_text(len(shown), total), err=True)


def _render_users_table(users: list[User]) -> None:
    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("Name", overflow="fold")
    table.add_column("Email", overflow="fold")
    table.add_column("Id", style="dim", no_wrap=True)
    for user in users:
        table.add_row(user.name or "-", user.email or "-", user.id[:8])
    Console().print(table)


def _render_users_long(users: list[User]) -> None:
    """Header row plus one user per line."""
    typer.echo(f"{'NAME':<24}  {'EMAIL':<32}  ID")
    for user in users:
        typer.echo(
            f"{(user.name or '-'):<24}  {(user.email or '-'):<32}  {user.id}"
        )


def _render_users_json(users: list[User]) -> None:
    for user in users:
        typer.echo(
            _json.dumps(
                {
                    "kind": "user",
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                }
            )
        )


def _users_footer_text(shown: int, total: int) -> str:
    if shown >= total:
        noun = "user" if total == 1 else "users"
        return f"{total} {noun} in total"
    return f"showing {shown} of {total} users"


@app.command("list")
def list_(
    targets: list[str] = typer.Argument(
        None,
        metavar="[TARGETS...]",
        help=(
            "Album names or filename glob patterns. With no targets, "
            "all visible assets are listed in descending date order."
        ),
    ),
    fmt: ListFormat = typer.Option(
        ListFormat.table,
        "--format",
        "-f",
        help="Output format.",
        case_sensitive=False,
    ),
    albums_only: bool = typer.Option(
        False,
        "--albums-only",
        help="Only list albums (ignore asset-matching).",
    ),
    assets_only: bool = typer.Option(
        False,
        "--assets-only",
        help="Only list assets (ignore album-matching).",
    ),
    only_owned: bool = typer.Option(
        False,
        "--only-owned",
        help="Only show albums/assets owned by you.",
    ),
    only_shared: bool = typer.Option(
        False,
        "--only-shared",
        help="Only show albums/assets shared with you.",
    ),
    since: str = typer.Option(
        None,
        "--since",
        help=(
            "Filter assets created on or after this date "
            "(YYYY-MM-DD or ISO-8601)."
        ),
    ),
    until: str = typer.Option(
        None,
        "--until",
        help=(
            "Filter assets created before this date "
            "(YYYY-MM-DD or ISO-8601, exclusive upper bound)."
        ),
    ),
    limit: int = typer.Option(
        DEFAULT_LIST_LIMIT,
        "--limit",
        "-n",
        help=(
            f"Return at most this many results. Pass 0 to disable the cap. "
            f"Default: {DEFAULT_LIST_LIMIT}."
        ),
    ),
    case_sensitive: bool = typer.Option(
        False,
        "--case-sensitive/--case-insensitive",
        "-s/-i",
        help=(
            "Match patterns case-sensitively (off by default). Pass "
            "-i or --case-insensitive to force the default."
        ),
    ),
) -> None:
    """List albums and/or assets from Immich.

    With no targets, lists every visible asset, most recent first.
    With targets, tries each as an album name/glob first, then as a
    filename glob.
    """
    if albums_only and assets_only:
        typer.echo(
            "pymmich: --albums-only and --assets-only are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=2)
    if only_owned and only_shared:
        typer.echo(
            "pymmich: --only-owned and --only-shared are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=2)

    since_dt = _parse_date(since, option_name="--since") if since else None
    until_dt = _parse_date(until, option_name="--until") if until else None

    include_shared = not only_owned
    targets_list = targets or []
    # 0 is treated as "no limit" so users can explicitly opt out of
    # the default cap without passing a huge number.
    effective_limit: int | None = limit if limit and limit > 0 else None

    with _make_client() as client:
        result = _collect_list_entries(
            client,
            targets=targets_list,
            albums_only=albums_only,
            assets_only=assets_only,
            include_shared=include_shared,
            only_shared=only_shared,
            case_sensitive=case_sensitive,
            since=since_dt,
            until=until_dt,
            limit=effective_limit,
        )
    _render(result, fmt)


if __name__ == "__main__":
    app()
