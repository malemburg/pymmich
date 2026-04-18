"""Tests for the ImmichClient low-level API wrapper."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import httpx
import pytest

from pymmich.client import ImmichClient, ImmichError


def test_client_sends_api_key_header(client: ImmichClient, mock_router):
    route = mock_router.get("/api/server/ping").respond(
        200, json={"res": "pong"}
    )
    client.ping()
    assert route.called
    request = route.calls.last.request
    assert request.headers["x-api-key"] == "test-api-key-123"
    assert request.headers["accept"] == "application/json"


def test_client_strips_trailing_slash_in_base_url():
    with ImmichClient(base_url="https://host/api/", api_key="k") as c:
        assert c.base_url == "https://host/api"


def test_client_appends_api_suffix_when_missing():
    with ImmichClient(base_url="https://host", api_key="k") as c:
        assert c.base_url == "https://host/api"


def test_ping_raises_on_http_error(client: ImmichClient, mock_router):
    mock_router.get("/api/server/ping").respond(500, text="boom")
    with pytest.raises(ImmichError):
        client.ping()


def test_get_supported_media_types(client: ImmichClient, mock_router):
    mock_router.get("/api/server/media-types").respond(
        200,
        json={
            "image": [".jpg", ".jpeg", ".png"],
            "video": [".mp4", ".mov"],
            "sidecar": [".xmp"],
        },
    )
    types = client.get_supported_media_types()
    assert ".jpg" in types.image
    assert ".mp4" in types.video


def test_list_albums(client: ImmichClient, mock_router):
    mock_router.get("/api/albums").respond(
        200,
        json=[
            {"id": "a1", "albumName": "Vacation 2024", "assetCount": 3},
            {"id": "a2", "albumName": "Birthdays", "assetCount": 7},
        ],
    )
    albums = client.list_albums()
    assert len(albums) == 2
    assert albums[0].id == "a1"
    assert albums[0].album_name == "Vacation 2024"
    assert albums[0].asset_count == 3


def test_create_album(client: ImmichClient, mock_router):
    route = mock_router.post("/api/albums").respond(
        201,
        json={"id": "new-1", "albumName": "Trip", "assetCount": 0},
    )
    album = client.create_album("Trip")
    assert album.id == "new-1"
    assert album.album_name == "Trip"
    request = route.calls.last.request
    import json as _json
    body = _json.loads(request.content)
    assert body == {"albumName": "Trip"}


def test_add_assets_to_album(client: ImmichClient, mock_router):
    route = mock_router.put("/api/albums/album-1/assets").respond(
        200,
        json=[
            {"id": "x", "success": True},
            {"id": "y", "success": False, "error": "duplicate"},
        ],
    )
    results = client.add_assets_to_album("album-1", ["x", "y"])
    assert [r.success for r in results] == [True, False]
    import json as _json
    body = _json.loads(route.calls.last.request.content)
    assert body == {"ids": ["x", "y"]}


def test_upload_asset(client: ImmichClient, tmp_path: Path, mock_router):
    fn = tmp_path / "photo.jpg"
    fn.write_bytes(b"JPEG-bytes")

    route = mock_router.post("/api/assets").respond(
        201, json={"id": "asset-uuid-1", "status": "created"}
    )
    result = client.upload_asset(fn)
    assert result.id == "asset-uuid-1"
    assert result.status == "created"

    request = route.calls.last.request
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content
    assert b"photo.jpg" in body
    assert b"JPEG-bytes" in body
    assert b"fileCreatedAt" in body
    assert b"fileModifiedAt" in body


def test_upload_asset_formats_dates_without_fractional_seconds(
    client: ImmichClient, tmp_path: Path, mock_router
):
    """Regression test. When a file's mtime has microseconds,
    ``datetime.isoformat()`` produces ``2025-11-05T22:13:22.123456+00:00``.
    pymmich previously built the request body via
    ``.replace("+00:00", ".000Z")``, which left an invalid
    ``2025-11-05T22:13:22.123456.000Z`` string and the Immich server
    rejected the upload with ``fileCreatedAt must be a date string``.
    """
    import os
    fn = tmp_path / "photo.jpg"
    fn.write_bytes(b"data")
    # Force an mtime that has a non-zero subsecond fraction.
    os.utime(fn, (1_730_841_202.123456, 1_730_841_202.123456))

    route = mock_router.post("/api/assets").respond(
        201, json={"id": "a-1", "status": "created"}
    )
    client.upload_asset(fn)
    body = route.calls.last.request.content
    # The date fields must match the server's expected `...Z` pattern
    # without a stray fractional-seconds suffix before the ``.000Z``.
    assert b"fileCreatedAt" in body
    import re
    date_re = re.compile(
        rb'name="fileCreatedAt"\r\n\r\n([^\r]+)\r\n', re.DOTALL
    )
    m = date_re.search(body)
    assert m, "fileCreatedAt field not found in multipart body"
    value = m.group(1)
    assert re.fullmatch(
        rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value
    ), f"invalid date format: {value!r}"


def test_upload_asset_duplicate_status(client: ImmichClient, tmp_path: Path, mock_router):
    fn = tmp_path / "p.jpg"
    fn.write_bytes(b"x")
    mock_router.post("/api/assets").respond(
        200, json={"id": "dup-1", "status": "duplicate"}
    )
    r = client.upload_asset(fn)
    assert r.status == "duplicate"


def test_download_asset_original(client: ImmichClient, tmp_path: Path, mock_router):
    mock_router.get("/api/assets/abc/original").respond(
        200, content=b"raw-bytes-here"
    )
    dest = tmp_path / "out.jpg"
    client.download_asset("abc", dest)
    assert dest.read_bytes() == b"raw-bytes-here"


def test_get_asset_info(client: ImmichClient, mock_router):
    mock_router.get("/api/assets/abc").respond(
        200,
        json={
            "id": "abc",
            "originalFileName": "IMG_0001.jpg",
            "fileCreatedAt": "2023-05-10T14:32:10.000Z",
            "fileModifiedAt": "2023-05-10T14:32:10.000Z",
            "type": "IMAGE",
        },
    )
    info = client.get_asset_info("abc")
    assert info.id == "abc"
    assert info.original_file_name == "IMG_0001.jpg"
    assert info.file_created_at == dt.datetime(
        2023, 5, 10, 14, 32, 10, tzinfo=dt.UTC
    )


def test_search_assets_by_album(client: ImmichClient, mock_router):
    """``search_assets_by_album`` must use timeline endpoints, not the
    ``/search/metadata`` endpoint which forcibly filters to
    caller-owned assets and would hide other users' contributions in
    a shared album."""
    mock_router.get("/api/timeline/buckets").respond(
        200,
        json=[
            {"timeBucket": "2024-01-01", "count": 2},
            {"timeBucket": "2024-02-01", "count": 1},
        ],
    )

    def _bucket(request):
        import httpx as _httpx
        bucket = request.url.params.get("timeBucket")
        if bucket == "2024-01-01":
            return _httpx.Response(200, json={"id": ["1", "2"]})
        return _httpx.Response(200, json={"id": ["3"]})

    mock_router.get("/api/timeline/bucket").mock(side_effect=_bucket)

    def _asset_info(request):
        import httpx as _httpx
        # last path segment is the asset id
        asset_id = request.url.path.rsplit("/", 1)[-1]
        return _httpx.Response(
            200,
            json={
                "id": asset_id,
                "originalFileName": f"{asset_id}.jpg",
                "fileCreatedAt": "2024-01-01T00:00:00.000Z",
                "fileModifiedAt": "2024-01-01T00:00:00.000Z",
                "type": "IMAGE",
            },
        )

    mock_router.get(url__regex=r".*/api/assets/[^/]+$").mock(
        side_effect=_asset_info
    )

    assets = list(client.search_assets_by_album("album-id"))
    assert [a.id for a in assets] == ["1", "2", "3"]


def test_search_assets_by_album_forwards_album_id(
    client: ImmichClient, mock_router
):
    """The album id must be sent as a ``?albumId=`` query parameter on
    both timeline endpoints, otherwise we'd be asking for the user's
    entire timeline."""
    buckets_route = mock_router.get("/api/timeline/buckets").respond(
        200, json=[{"timeBucket": "2024-01-01", "count": 0}]
    )
    bucket_route = mock_router.get("/api/timeline/bucket").respond(
        200, json={"id": []}
    )

    list(client.search_assets_by_album("album-xyz"))

    assert buckets_route.calls.last.request.url.params.get("albumId") == "album-xyz"
    assert bucket_route.calls.last.request.url.params.get("albumId") == "album-xyz"
    assert bucket_route.calls.last.request.url.params.get("timeBucket") == "2024-01-01"


def test_list_all_assets_default_order_desc(client: ImmichClient, mock_router):
    """``list_all_assets`` without filters must request ``order=desc``
    and no date filters."""
    calls: list[dict] = []

    def _handler(request):
        import json as _json
        body = _json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200,
            json={
                "albums": {"total": 0, "count": 0, "items": [], "facets": [], "nextPage": None},
                "assets": {
                    "total": 1,
                    "count": 1,
                    "nextPage": None,
                    "facets": [],
                    "items": [{
                        "id": "a1",
                        "originalFileName": "a.jpg",
                        "fileCreatedAt": "2024-01-01T00:00:00.000Z",
                        "fileModifiedAt": "2024-01-01T00:00:00.000Z",
                        "type": "IMAGE",
                    }],
                },
            },
        )

    mock_router.post("/api/search/metadata").mock(side_effect=_handler)
    assets = list(client.list_all_assets())
    assert [a.id for a in assets] == ["a1"]
    assert calls[0]["order"] == "desc"
    assert "takenAfter" not in calls[0]
    assert "takenBefore" not in calls[0]


def test_list_all_assets_with_date_range(client: ImmichClient, mock_router):
    import datetime as dt
    calls: list[dict] = []

    def _handler(request):
        import json as _json
        body = _json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200,
            json={
                "albums": {"total": 0, "count": 0, "items": [], "facets": [], "nextPage": None},
                "assets": {
                    "total": 0, "count": 0, "nextPage": None, "facets": [], "items": []
                },
            },
        )

    mock_router.post("/api/search/metadata").mock(side_effect=_handler)
    since = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
    list(client.list_all_assets(since=since, until=until))
    assert calls[0]["takenAfter"].startswith("2024-01-01")
    assert calls[0]["takenBefore"].startswith("2024-03-01")


def test_list_all_assets_limit_stops_iteration(client: ImmichClient, mock_router):
    """Once ``limit`` results have been yielded, no further pages
    should be requested."""
    # page 1 has 3 items and promises a page 2 — but with limit=2 we
    # must not fetch the second page.
    call_count = {"n": 0}

    def _handler(request):
        import json as _json
        call_count["n"] += 1
        body = _json.loads(request.content)
        page = int(body.get("page", 1))
        if page == 1:
            items = [
                {
                    "id": f"a{i}",
                    "originalFileName": f"{i}.jpg",
                    "fileCreatedAt": "2024-01-01T00:00:00.000Z",
                    "fileModifiedAt": "2024-01-01T00:00:00.000Z",
                    "type": "IMAGE",
                }
                for i in range(1, 4)
            ]
            return httpx.Response(
                200,
                json={
                    "albums": {"total": 0, "count": 0, "items": [], "facets": [], "nextPage": None},
                    "assets": {
                        "total": 6, "count": 3, "nextPage": "2", "facets": [], "items": items,
                    },
                },
            )
        return httpx.Response(500, text="unexpected")

    mock_router.post("/api/search/metadata").mock(side_effect=_handler)
    assets = list(client.list_all_assets(limit=2))
    assert [a.id for a in assets] == ["a1", "a2"]
    assert call_count["n"] == 1


def test_search_assets_by_filename_paginates(client: ImmichClient, mock_router):
    """``search_assets_by_filename`` still uses ``/search/metadata`` and
    must follow its page/nextPage pagination scheme."""
    def _page(page: int, items: list[dict]) -> dict:
        return {
            "albums": {"total": 0, "count": 0, "items": [], "facets": [], "nextPage": None},
            "assets": {
                "total": 3,
                "count": len(items),
                "nextPage": str(page + 1) if page == 1 else None,
                "facets": [],
                "items": items,
            },
        }

    call_count = {"n": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        body = _json.loads(request.content)
        page = int(body.get("page", 1))
        call_count["n"] += 1
        if page == 1:
            return httpx.Response(
                200,
                json=_page(1, [
                    {"id": "1", "originalFileName": "a.jpg", "fileCreatedAt": "2024-01-01T00:00:00.000Z", "fileModifiedAt": "2024-01-01T00:00:00.000Z", "type": "IMAGE"},
                    {"id": "2", "originalFileName": "b.jpg", "fileCreatedAt": "2024-01-01T00:00:00.000Z", "fileModifiedAt": "2024-01-01T00:00:00.000Z", "type": "IMAGE"},
                ]),
            )
        return httpx.Response(
            200,
            json=_page(2, [
                {"id": "3", "originalFileName": "c.jpg", "fileCreatedAt": "2024-01-01T00:00:00.000Z", "fileModifiedAt": "2024-01-01T00:00:00.000Z", "type": "IMAGE"},
            ]),
        )

    mock_router.post("/api/search/metadata").mock(side_effect=_handler)
    assets = list(client.search_assets_by_filename("a"))
    assert [a.id for a in assets] == ["1", "2", "3"]
    assert call_count["n"] == 2


def test_find_album_case_insensitive(client: ImmichClient, mock_router):
    mock_router.get("/api/albums").respond(
        200,
        json=[
            {"id": "a1", "albumName": "Vacation 2024", "assetCount": 0},
            {"id": "a2", "albumName": "Birthdays", "assetCount": 0},
        ],
    )
    found = client.find_album("vacation 2024", case_sensitive=False)
    assert found is not None and found.id == "a1"

    not_found = client.find_album("vacation 2024", case_sensitive=True)
    assert not_found is None

    exact = client.find_album("Vacation 2024", case_sensitive=True)
    assert exact is not None and exact.id == "a1"


def test_ensure_album_reuses_existing(client: ImmichClient, mock_router):
    mock_router.get("/api/albums").respond(
        200,
        json=[{"id": "a1", "albumName": "Holidays", "assetCount": 0}],
    )
    created = mock_router.post("/api/albums")
    album = client.ensure_album("holidays", case_sensitive=False)
    assert album.id == "a1"
    assert not created.called


def test_ensure_album_creates_when_missing(client: ImmichClient, mock_router):
    mock_router.get("/api/albums").respond(200, json=[])
    mock_router.post("/api/albums").respond(
        201, json={"id": "new", "albumName": "Beach Trip", "assetCount": 0}
    )
    album = client.ensure_album("Beach Trip", case_sensitive=False)
    assert album.id == "new"
    # newly created album uses the spelling the user supplied
    assert album.album_name == "Beach Trip"


def test_client_rejects_missing_credentials_from_env(monkeypatch):
    monkeypatch.delenv("PYMMICH_URL", raising=False)
    monkeypatch.delenv("PYMMICH_API_KEY", raising=False)
    with pytest.raises(ImmichError, match="PYMMICH_URL"):
        ImmichClient.from_env()


def test_client_from_env_uses_env_vars(monkeypatch):
    monkeypatch.setenv("PYMMICH_URL", "https://immich.example.com")
    monkeypatch.setenv("PYMMICH_API_KEY", "secret")
    with ImmichClient.from_env() as c:
        assert c.base_url == "https://immich.example.com/api"
        assert c.api_key == "secret"
