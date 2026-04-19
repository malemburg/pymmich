"""Tests for the ``pymmich upload`` command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from pymmich.cli import app


runner = CliRunner()


@pytest.fixture
def media_types_route(mock_router):
    mock_router.get("/api/server/media-types").respond(
        200,
        json={
            "image": [".jpg", ".jpeg", ".png", ".heic"],
            "video": [".mp4", ".mov"],
            "sidecar": [".xmp"],
        },
    )


def _cli_env(monkeypatch, base_url: str, api_key: str) -> None:
    monkeypatch.setenv("PYMMICH_URL", base_url)
    monkeypatch.setenv("PYMMICH_API_KEY", api_key)


def _mock_empty_album_contents(mock_router) -> None:
    """Mock an empty album (for collision-check reads during upload)."""
    mock_router.get("/api/timeline/buckets").respond(200, json=[])
    mock_router.get("/api/timeline/bucket").respond(200, json={"id": []})


def _mock_empty_filename_search(mock_router) -> None:
    """Mock an empty `/api/search/metadata` (no filename collisions)."""
    mock_router.post("/api/search/metadata").respond(
        200,
        json={
            "albums": {"total": 0, "count": 0, "items": [], "facets": [], "nextPage": None},
            "assets": {"total": 0, "count": 0, "items": [], "facets": [], "nextPage": None},
        },
    )


def test_upload_single_file_no_album(
    tmp_path: Path, mock_router, media_types_route, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)

    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"data")

    upload = mock_router.post("/api/assets").respond(
        201, json={"id": "a-1", "status": "created"}
    )
    _mock_empty_filename_search(mock_router)
    albums = mock_router.get("/api/albums")
    create = mock_router.post("/api/albums")
    add = mock_router.put("/api/albums/any/assets")

    result = runner.invoke(app, ["upload", str(photo)])
    assert result.exit_code == 0, result.stderr
    assert upload.called
    assert not albums.called
    assert not create.called
    assert not add.called


def test_upload_directory_creates_album(
    tmp_path: Path, mock_router, media_types_route, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)

    album_dir = tmp_path / "Trip"
    album_dir.mkdir()
    (album_dir / "a.jpg").write_bytes(b"a")
    (album_dir / "b.png").write_bytes(b"b")
    (album_dir / "notes.txt").write_bytes(b"text")  # should be skipped

    mock_router.get("/api/albums").respond(200, json=[])
    create = mock_router.post("/api/albums").respond(
        201, json={"id": "trip-1", "albumName": "Trip", "assetCount": 0}
    )
    _mock_empty_album_contents(mock_router)
    # individual uploads get distinct ids
    upload_ids = iter(["u-1", "u-2"])

    def _upload_handler(request):
        import httpx as _httpx
        return _httpx.Response(
            201, json={"id": next(upload_ids), "status": "created"}
        )

    upload_route = mock_router.post("/api/assets").mock(side_effect=_upload_handler)
    add = mock_router.put("/api/albums/trip-1/assets").respond(
        200, json=[{"id": "u-1", "success": True}, {"id": "u-2", "success": True}]
    )

    result = runner.invoke(app, ["upload", str(album_dir)])
    assert result.exit_code == 0, result.stderr
    assert upload_route.call_count == 2
    assert create.called
    assert add.called


def test_upload_directory_reuses_existing_album_case_insensitive(
    tmp_path: Path, mock_router, media_types_route, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)

    album_dir = tmp_path / "Trip"
    album_dir.mkdir()
    (album_dir / "a.jpg").write_bytes(b"a")

    mock_router.get("/api/albums").respond(
        200,
        json=[{"id": "trip-existing", "albumName": "trip", "assetCount": 5}],
    )
    create = mock_router.post("/api/albums")
    _mock_empty_album_contents(mock_router)
    mock_router.post("/api/assets").respond(
        201, json={"id": "u-1", "status": "created"}
    )
    add = mock_router.put("/api/albums/trip-existing/assets").respond(
        200, json=[{"id": "u-1", "success": True}]
    )

    result = runner.invoke(app, ["upload", str(album_dir)])
    assert result.exit_code == 0, result.stderr
    assert not create.called
    assert add.called


def test_upload_recursive(
    tmp_path: Path, mock_router, media_types_route, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)

    album_dir = tmp_path / "Trip"
    nested = album_dir / "day1"
    nested.mkdir(parents=True)
    (album_dir / "cover.jpg").write_bytes(b"x")
    (nested / "sunrise.jpg").write_bytes(b"y")

    mock_router.get("/api/albums").respond(200, json=[])
    mock_router.post("/api/albums").respond(
        201, json={"id": "t-1", "albumName": "Trip", "assetCount": 0}
    )
    _mock_empty_album_contents(mock_router)
    upload_ids = iter(["u-1", "u-2"])

    def _upload_handler(request):
        import httpx as _httpx
        return _httpx.Response(
            201, json={"id": next(upload_ids), "status": "created"}
        )

    upload_route = mock_router.post("/api/assets").mock(side_effect=_upload_handler)
    mock_router.put("/api/albums/t-1/assets").respond(200, json=[])

    result = runner.invoke(app, ["upload", str(album_dir), "--recursive"])
    assert result.exit_code == 0, result.stderr
    assert upload_route.call_count == 2


def test_upload_non_recursive_skips_subdirs(
    tmp_path: Path, mock_router, media_types_route, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)

    album_dir = tmp_path / "Trip"
    nested = album_dir / "day1"
    nested.mkdir(parents=True)
    (album_dir / "cover.jpg").write_bytes(b"x")
    (nested / "sunrise.jpg").write_bytes(b"y")  # should be ignored

    mock_router.get("/api/albums").respond(200, json=[])
    mock_router.post("/api/albums").respond(
        201, json={"id": "t-1", "albumName": "Trip", "assetCount": 0}
    )
    _mock_empty_album_contents(mock_router)
    upload_route = mock_router.post("/api/assets").respond(
        201, json={"id": "u-1", "status": "created"}
    )
    mock_router.put("/api/albums/t-1/assets").respond(200, json=[])

    result = runner.invoke(app, ["upload", str(album_dir)])
    assert result.exit_code == 0, result.stderr
    assert upload_route.call_count == 1


def test_upload_missing_env_fails_cleanly(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PYMMICH_URL", raising=False)
    monkeypatch.delenv("PYMMICH_API_KEY", raising=False)
    f = tmp_path / "p.jpg"
    f.write_bytes(b"x")
    result = runner.invoke(app, ["upload", str(f)])
    assert result.exit_code != 0
    assert "PYMMICH_URL" in result.stderr or "PYMMICH_URL" in result.stdout


def test_upload_case_sensitive_creates_separate_album(
    tmp_path: Path, mock_router, media_types_route, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    album_dir = tmp_path / "Trip"
    album_dir.mkdir()
    (album_dir / "a.jpg").write_bytes(b"a")

    mock_router.get("/api/albums").respond(
        200, json=[{"id": "other", "albumName": "trip", "assetCount": 0}]
    )
    create = mock_router.post("/api/albums").respond(
        201, json={"id": "new-trip", "albumName": "Trip", "assetCount": 0}
    )
    _mock_empty_album_contents(mock_router)
    mock_router.post("/api/assets").respond(
        201, json={"id": "u-1", "status": "created"}
    )
    add = mock_router.put("/api/albums/new-trip/assets").respond(200, json=[])

    result = runner.invoke(app, ["upload", str(album_dir), "--case-sensitive"])
    assert result.exit_code == 0, result.stderr
    assert create.called
    assert add.called


def test_upload_mixed_file_and_dir(
    tmp_path: Path, mock_router, media_types_route, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    standalone = tmp_path / "solo.jpg"
    standalone.write_bytes(b"s")
    album_dir = tmp_path / "Album"
    album_dir.mkdir()
    (album_dir / "in_album.jpg").write_bytes(b"a")

    mock_router.get("/api/albums").respond(200, json=[])
    create = mock_router.post("/api/albums").respond(
        201, json={"id": "al-1", "albumName": "Album", "assetCount": 0}
    )
    _mock_empty_album_contents(mock_router)
    _mock_empty_filename_search(mock_router)
    upload_ids = iter(["solo-1", "al-1"])

    def _upload_handler(request):
        import httpx as _httpx
        return _httpx.Response(
            201, json={"id": next(upload_ids), "status": "created"}
        )

    upload_route = mock_router.post("/api/assets").mock(side_effect=_upload_handler)
    add = mock_router.put("/api/albums/al-1/assets").respond(200, json=[])

    result = runner.invoke(app, ["upload", str(standalone), str(album_dir)])
    assert result.exit_code == 0, result.stderr
    assert upload_route.call_count == 2
    assert create.called
    assert add.called


def test_upload_album_option_routes_everything_to_single_album(
    tmp_path: Path, mock_router, media_types_route, base_url, api_key, monkeypatch
):
    """``--album`` puts standalone files AND dir contents into one album."""
    _cli_env(monkeypatch, base_url, api_key)
    standalone = tmp_path / "solo.jpg"
    standalone.write_bytes(b"s")
    album_dir = tmp_path / "Trip"
    album_dir.mkdir()
    (album_dir / "in_dir.jpg").write_bytes(b"a")

    mock_router.get("/api/albums").respond(200, json=[])
    create = mock_router.post("/api/albums").respond(
        201, json={"id": "tgt-1", "albumName": "Target", "assetCount": 0}
    )
    _mock_empty_album_contents(mock_router)
    upload_ids = iter(["u-1", "u-2"])

    def _upload_handler(request):
        import httpx as _httpx
        return _httpx.Response(
            201, json={"id": next(upload_ids), "status": "created"}
        )

    upload_route = mock_router.post("/api/assets").mock(side_effect=_upload_handler)
    add_route = mock_router.put("/api/albums/tgt-1/assets").respond(200, json=[])

    result = runner.invoke(
        app,
        ["upload", str(standalone), str(album_dir), "--album", "Target"],
    )
    assert result.exit_code == 0, result.stderr
    assert upload_route.call_count == 2
    assert create.called
    # Both assets must be added to the single target album in one call.
    import json as _json
    bodies = [_json.loads(c.request.content) for c in add_route.calls]
    assert bodies
    ids = {i for body in bodies for i in body["ids"]}
    assert ids == {"u-1", "u-2"}


def test_upload_renames_on_collision_by_default(
    tmp_path: Path, mock_router, media_types_route, base_url, api_key, monkeypatch
):
    """When the album already contains ``foo.jpg``, a second ``foo.jpg``
    must upload as ``foo_1.jpg`` and a warning must be emitted."""
    _cli_env(monkeypatch, base_url, api_key)
    album_dir = tmp_path / "Trip"
    album_dir.mkdir()
    (album_dir / "foo.jpg").write_bytes(b"x")

    mock_router.get("/api/albums").respond(
        200, json=[{"id": "trip-1", "albumName": "Trip", "assetCount": 1}]
    )
    # Album already has foo.jpg on the server.
    mock_router.get("/api/timeline/buckets").respond(
        200, json=[{"timeBucket": "2024-01-01", "count": 1}]
    )
    mock_router.get("/api/timeline/bucket").respond(
        200, json={"id": ["existing"]}
    )
    mock_router.get("/api/assets/existing").respond(
        200,
        json={
            "id": "existing",
            "originalFileName": "foo.jpg",
            "fileCreatedAt": "2024-01-01T00:00:00.000Z",
            "fileModifiedAt": "2024-01-01T00:00:00.000Z",
            "type": "IMAGE",
        },
    )

    captured_names: list[str] = []

    def _upload_handler(request):
        import httpx as _httpx
        # Pull the filename out of the multipart body.
        body = request.content.decode("latin-1")
        for line in body.splitlines():
            if 'filename="' in line:
                captured_names.append(
                    line.split('filename="', 1)[1].split('"', 1)[0]
                )
                break
        return _httpx.Response(201, json={"id": "u-new", "status": "created"})

    mock_router.post("/api/assets").mock(side_effect=_upload_handler)
    mock_router.put("/api/albums/trip-1/assets").respond(200, json=[])

    result = runner.invoke(app, ["upload", str(album_dir)])
    assert result.exit_code == 0, result.stderr
    assert captured_names == ["foo_1.jpg"]
    assert "foo_1.jpg" in result.stderr


def test_upload_force_keeps_original_name_on_collision(
    tmp_path: Path, mock_router, media_types_route, base_url, api_key, monkeypatch
):
    """With ``--force``, even a colliding filename is uploaded as-is."""
    _cli_env(monkeypatch, base_url, api_key)
    album_dir = tmp_path / "Trip"
    album_dir.mkdir()
    (album_dir / "foo.jpg").write_bytes(b"x")

    mock_router.get("/api/albums").respond(
        200, json=[{"id": "trip-1", "albumName": "Trip", "assetCount": 1}]
    )
    # No album-contents lookup needed with --force, but mock anyway:
    _mock_empty_album_contents(mock_router)

    captured_names: list[str] = []

    def _upload_handler(request):
        import httpx as _httpx
        body = request.content.decode("latin-1")
        for line in body.splitlines():
            if 'filename="' in line:
                captured_names.append(
                    line.split('filename="', 1)[1].split('"', 1)[0]
                )
                break
        return _httpx.Response(201, json={"id": "u", "status": "created"})

    mock_router.post("/api/assets").mock(side_effect=_upload_handler)
    mock_router.put("/api/albums/trip-1/assets").respond(200, json=[])

    result = runner.invoke(app, ["upload", str(album_dir), "--force"])
    assert result.exit_code == 0, result.stderr
    assert captured_names == ["foo.jpg"]
