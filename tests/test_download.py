"""Tests for the ``pymmich download`` command."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from pymmich.cli import app


runner = CliRunner()


def _cli_env(monkeypatch, base_url: str, api_key: str) -> None:
    monkeypatch.setenv("PYMMICH_URL", base_url)
    monkeypatch.setenv("PYMMICH_API_KEY", api_key)


def _asset(
    asset_id: str,
    filename: str,
    created: str = "2024-03-01T12:00:00.000Z",
) -> dict:
    return {
        "id": asset_id,
        "originalFileName": filename,
        "fileCreatedAt": created,
        "fileModifiedAt": created,
        "type": "IMAGE",
    }


def _search_response(items: list[dict]) -> dict:
    return {
        "albums": {"total": 0, "count": 0, "items": [], "facets": [], "nextPage": None},
        "assets": {
            "total": len(items),
            "count": len(items),
            "nextPage": None,
            "facets": [],
            "items": items,
        },
    }


def _mock_album_assets(mock_router, assets: list[dict]) -> None:
    """Wire up the timeline + per-asset-info mocks that back
    ``search_assets_by_album``. ``assets`` must be the list of full
    asset dicts the album should yield."""
    if assets:
        # one bucket per distinct fileCreatedAt day is enough for tests
        buckets = [{"timeBucket": "2024-01-01", "count": len(assets)}]
    else:
        buckets = []
    mock_router.get("/api/timeline/buckets").respond(200, json=buckets)
    mock_router.get("/api/timeline/bucket").respond(
        200, json={"id": [a["id"] for a in assets]}
    )
    for asset in assets:
        mock_router.get(f"/api/assets/{asset['id']}").respond(200, json=asset)


def test_download_album(
    tmp_path: Path, mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)

    mock_router.get("/api/albums").respond(
        200,
        json=[{"id": "alb-1", "albumName": "Vacation", "assetCount": 2}],
    )
    _mock_album_assets(
        mock_router,
        [
            _asset("a1", "one.jpg", "2024-01-03T10:00:00.000Z"),
            _asset("a2", "two.jpg", "2024-01-05T10:00:00.000Z"),
        ],
    )
    mock_router.get("/api/assets/a1/original").respond(200, content=b"bytes-1")
    mock_router.get("/api/assets/a2/original").respond(200, content=b"bytes-2")

    out = tmp_path / "out"
    result = runner.invoke(app, ["download", "Vacation", "--dir", str(out)])
    assert result.exit_code == 0, result.stderr

    album_dir = out / "Vacation"
    assert (album_dir / "one.jpg").read_bytes() == b"bytes-1"
    assert (album_dir / "two.jpg").read_bytes() == b"bytes-2"

    # file mtime is set to asset creation date
    f1_mtime = dt.datetime.fromtimestamp(
        (album_dir / "one.jpg").stat().st_mtime, tz=dt.UTC
    )
    assert f1_mtime == dt.datetime(2024, 1, 3, 10, 0, 0, tzinfo=dt.UTC)

    # directory mtime is the oldest asset's date
    dir_mtime = dt.datetime.fromtimestamp(album_dir.stat().st_mtime, tz=dt.UTC)
    assert dir_mtime == dt.datetime(2024, 1, 3, 10, 0, 0, tzinfo=dt.UTC)


def test_download_album_adds_to_existing_dir(
    tmp_path: Path, mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)

    out = tmp_path / "out"
    album_dir = out / "Vacation"
    album_dir.mkdir(parents=True)
    (album_dir / "preexisting.txt").write_bytes(b"keep me")

    mock_router.get("/api/albums").respond(
        200, json=[{"id": "alb-1", "albumName": "Vacation", "assetCount": 1}]
    )
    _mock_album_assets(mock_router, [_asset("a1", "new.jpg")])
    mock_router.get("/api/assets/a1/original").respond(200, content=b"fresh")

    result = runner.invoke(app, ["download", "Vacation", "--dir", str(out)])
    assert result.exit_code == 0, result.stderr
    assert (album_dir / "preexisting.txt").read_bytes() == b"keep me"
    assert (album_dir / "new.jpg").read_bytes() == b"fresh"


def test_download_filename_glob_when_no_album_match(
    tmp_path: Path, mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)

    mock_router.get("/api/albums").respond(200, json=[])

    def _search(request):
        import json as _json
        body = _json.loads(request.content)
        if "originalFileName" in body:
            items = [
                _asset("a1", "IMG_0001.heic"),
                _asset("a2", "IMG_0002.heic"),
                _asset("a3", "notes.txt"),  # matches substring but not glob
            ]
            return httpx.Response(200, json=_search_response(items))
        return httpx.Response(200, json=_search_response([]))

    mock_router.post("/api/search/metadata").mock(side_effect=_search)
    mock_router.get("/api/assets/a1/original").respond(200, content=b"h1")
    mock_router.get("/api/assets/a2/original").respond(200, content=b"h2")

    out = tmp_path / "out"
    result = runner.invoke(app, ["download", "IMG_*.heic", "--dir", str(out)])
    assert result.exit_code == 0, result.stderr
    assert (out / "IMG_0001.heic").read_bytes() == b"h1"
    assert (out / "IMG_0002.heic").read_bytes() == b"h2"
    assert not (out / "notes.txt").exists()


def test_download_uses_cwd_when_no_out(
    tmp_path: Path, mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[{"id": "alb-1", "albumName": "X", "assetCount": 1}]
    )
    _mock_album_assets(mock_router, [_asset("a1", "f.jpg")])
    mock_router.get("/api/assets/a1/original").respond(200, content=b"B")

    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["download", "X"])
    assert result.exit_code == 0, result.stderr
    assert (tmp_path / "X" / "f.jpg").read_bytes() == b"B"


def test_download_no_match_fails(
    tmp_path: Path, mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[])
    mock_router.post("/api/search/metadata").respond(
        200, json=_search_response([])
    )
    result = runner.invoke(app, ["download", "Nonexistent", "--dir", str(tmp_path)])
    assert result.exit_code != 0
    combined = (result.stdout or "") + (result.stderr or "")
    assert "no match" in combined.lower() or "no assets" in combined.lower()


def test_download_album_case_sensitive(
    tmp_path: Path, mock_router, base_url, api_key, monkeypatch
):
    """With --case-sensitive, 'vacation' should NOT match album 'Vacation'."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[{"id": "alb-1", "albumName": "Vacation", "assetCount": 0}]
    )
    mock_router.post("/api/search/metadata").respond(
        200, json=_search_response([])
    )
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["download", "vacation", "--dir", str(out), "--case-sensitive"]
    )
    # no album match and no filename match -> error
    assert result.exit_code != 0


def test_download_default_includes_shared_albums(
    tmp_path: Path, mock_router, base_url, api_key, monkeypatch
):
    """By default, ``pymmich download`` must hit BOTH ``GET /albums``
    and ``GET /albums?shared=true`` so owned + shared-with-me albums
    merge."""
    _cli_env(monkeypatch, base_url, api_key)

    def _albums_handler(request):
        if request.url.params.get("shared") == "true":
            return httpx.Response(
                200,
                json=[
                    {"id": "alb-shared", "albumName": "Shared With Me", "assetCount": 1}
                ],
            )
        return httpx.Response(200, json=[])

    route = mock_router.get("/api/albums").mock(side_effect=_albums_handler)
    _mock_album_assets(mock_router, [_asset("a1", "file.jpg")])
    mock_router.get("/api/assets/a1/original").respond(200, content=b"B")

    out = tmp_path / "out"
    result = runner.invoke(app, ["download", "Shared With Me", "--dir", str(out)])
    assert result.exit_code == 0, result.stdout
    urls = [str(c.request.url) for c in route.calls]
    assert any("shared=true" in u for u in urls)
    assert any("shared=true" not in u for u in urls)
    assert (out / "Shared With Me" / "file.jpg").read_bytes() == b"B"


def test_download_short_i_forces_case_insensitive(
    tmp_path: Path, mock_router, base_url, api_key, monkeypatch
):
    """``-i`` must override a preceding ``--case-sensitive`` on the
    same command line (boolean flag pair semantics)."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[{"id": "alb-1", "albumName": "Vacation", "assetCount": 0}]
    )
    _mock_album_assets(mock_router, [])
    out = tmp_path / "out"
    # --case-sensitive on its own would make 'vacation' miss 'Vacation';
    # -i flips it back to insensitive, so the album matches.
    result = runner.invoke(
        app,
        ["download", "vacation", "--dir", str(out), "--case-sensitive", "-i"],
    )
    assert result.exit_code == 0, result.stdout


def test_download_renames_on_local_collision_by_default(
    tmp_path: Path, mock_router, base_url, api_key, monkeypatch
):
    """A pre-existing local file must not be overwritten; instead the
    incoming file is saved with a numbered suffix and a warning is
    printed."""
    _cli_env(monkeypatch, base_url, api_key)
    out = tmp_path / "out"
    album_dir = out / "Vacation"
    album_dir.mkdir(parents=True)
    (album_dir / "one.jpg").write_bytes(b"OLD")

    mock_router.get("/api/albums").respond(
        200, json=[{"id": "alb-1", "albumName": "Vacation", "assetCount": 1}]
    )
    _mock_album_assets(mock_router, [_asset("a1", "one.jpg")])
    mock_router.get("/api/assets/a1/original").respond(200, content=b"NEW")

    result = runner.invoke(app, ["download", "Vacation", "--dir", str(out)])
    assert result.exit_code == 0, result.stderr
    assert (album_dir / "one.jpg").read_bytes() == b"OLD"
    assert (album_dir / "one_1.jpg").read_bytes() == b"NEW"
    assert "one_1.jpg" in result.stderr


def test_download_force_overwrites_local_file(
    tmp_path: Path, mock_router, base_url, api_key, monkeypatch
):
    """``--force`` must overwrite an existing local file."""
    _cli_env(monkeypatch, base_url, api_key)
    out = tmp_path / "out"
    album_dir = out / "Vacation"
    album_dir.mkdir(parents=True)
    (album_dir / "one.jpg").write_bytes(b"OLD")

    mock_router.get("/api/albums").respond(
        200, json=[{"id": "alb-1", "albumName": "Vacation", "assetCount": 1}]
    )
    _mock_album_assets(mock_router, [_asset("a1", "one.jpg")])
    mock_router.get("/api/assets/a1/original").respond(200, content=b"NEW")

    result = runner.invoke(
        app, ["download", "Vacation", "--dir", str(out), "--force"]
    )
    assert result.exit_code == 0, result.stderr
    assert (album_dir / "one.jpg").read_bytes() == b"NEW"
    assert not (album_dir / "one_1.jpg").exists()


def test_download_only_owned_skips_shared_query(
    tmp_path: Path, mock_router, base_url, api_key, monkeypatch
):
    """``--only-owned`` must issue a single owned-only request (no
    extra ``?shared=true`` call)."""
    _cli_env(monkeypatch, base_url, api_key)
    route = mock_router.get("/api/albums").respond(
        200, json=[{"id": "alb-1", "albumName": "Mine", "assetCount": 0}]
    )
    _mock_album_assets(mock_router, [])
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["download", "Mine", "--dir", str(out), "--only-owned"]
    )
    # No assets in album, but CLI finished the album lookup successfully.
    assert result.exit_code == 0, result.stdout
    assert route.call_count == 1
    assert "shared" not in route.calls.last.request.url.params
