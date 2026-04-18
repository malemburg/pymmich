"""Tests for the ``pymmich list`` command."""

from __future__ import annotations

import json

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


def _album(
    album_id: str,
    name: str,
    count: int = 0,
    end_date: str | None = None,
) -> dict:
    data: dict = {
        "id": album_id,
        "albumName": name,
        "assetCount": count,
        "albumUsers": [],
    }
    if end_date is not None:
        data["endDate"] = end_date
        data["startDate"] = end_date
    return data


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


def _mock_album_timeline(mock_router, album_id: str, assets: list[dict]) -> None:
    """Wire timeline+asset-info mocks for listing an album's assets."""
    buckets = [{"timeBucket": "2024-01-01", "count": len(assets)}] if assets else []
    mock_router.get("/api/timeline/buckets").respond(200, json=buckets)
    mock_router.get("/api/timeline/bucket").respond(
        200, json={"id": [a["id"] for a in assets]}
    )
    for a in assets:
        mock_router.get(f"/api/assets/{a['id']}").respond(200, json=a)


# ---- default behaviour -----------------------------------------------


def test_list_default_includes_albums_and_assets_json(
    mock_router, base_url, api_key, monkeypatch
):
    """Default: list both albums AND assets; albums DESC by endDate
    come first, then assets DESC by fileCreatedAt."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200,
        json=[
            _album("alb-old", "Old Album", 3, end_date="2023-01-15T10:00:00.000Z"),
            _album("alb-new", "New Album", 5, end_date="2024-07-20T10:00:00.000Z"),
        ],
    )
    mock_router.post("/api/search/metadata").respond(
        200,
        json=_search_response([
            _asset("a1", "one.jpg", "2024-03-10T10:00:00.000Z"),
            _asset("a2", "two.jpg", "2024-02-01T10:00:00.000Z"),
        ]),
    )
    result = runner.invoke(app, ["list", "--format", "json"])
    assert result.exit_code == 0, result.stdout
    # Footer line goes to stderr; stdout has only JSON.
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    parsed = [json.loads(l) for l in lines]
    kinds = [p["kind"] for p in parsed]
    # Albums come first (DESC by end_date), then assets.
    assert kinds[0:2] == ["album", "album"]
    assert [p["id"] for p in parsed[:2]] == ["alb-new", "alb-old"]
    assert all(p["kind"] == "asset" for p in parsed[2:])
    assert [p["id"] for p in parsed[2:]] == ["a1", "a2"]


def test_list_default_format_is_table(
    mock_router, base_url, api_key, monkeypatch
):
    """No --format → output should not be valid JSON (it's a table)."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[])
    mock_router.post("/api/search/metadata").respond(
        200, json=_search_response([_asset("a1", "one.jpg")])
    )
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0, result.stdout
    # rich tables use box-drawing characters
    assert "one.jpg" in result.stdout


def test_list_long_format_has_header(
    mock_router, base_url, api_key, monkeypatch
):
    """--format long must emit a column-title header row before the data."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[])
    mock_router.post("/api/search/metadata").respond(
        200,
        json=_search_response([_asset("a1", "photo.jpg", "2024-03-10T10:00:00.000Z")]),
    )
    result = runner.invoke(app, ["list", "--format", "long"])
    assert result.exit_code == 0, result.stdout
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    # Expect: header line, data line, footer line.
    assert len(lines) >= 2
    header = lines[0].upper()
    for col in ("TYPE", "COUNT", "DATE", "NAME"):
        assert col in header, f"missing {col!r} column header in: {lines[0]!r}"
    # data line has the filename
    assert any("photo.jpg" in l for l in lines[1:])


# ---- argument-based matching -----------------------------------------


def test_list_album_pattern_lists_album_assets(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[_album("alb-1", "Vacation", 2)]
    )
    _mock_album_timeline(
        mock_router,
        "alb-1",
        [
            _asset("a1", "one.jpg"),
            _asset("a2", "two.jpg"),
        ],
    )
    result = runner.invoke(app, ["list", "Vacation", "--format", "json"])
    assert result.exit_code == 0, result.stdout
    lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
    # first should be the album header entry, then its assets
    kinds = [l["kind"] for l in lines]
    assert "album" in kinds
    assert "asset" in kinds


def test_list_filename_glob_falls_back_to_assets(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    # no albums match
    mock_router.get("/api/albums").respond(200, json=[])
    mock_router.post("/api/search/metadata").respond(
        200,
        json=_search_response([_asset("a1", "IMG_0001.heic")]),
    )
    result = runner.invoke(
        app, ["list", "IMG_*.heic", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
    assert [l["id"] for l in lines] == ["a1"]


# ---- --albums-only / --assets-only ----------------------------------


def test_list_albums_only_no_args_lists_albums(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "One"), _album("a2", "Two")]
    )
    result = runner.invoke(
        app, ["list", "--albums-only", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
    assert all(l["kind"] == "album" for l in lines)
    assert {l["id"] for l in lines} == {"a1", "a2"}


def test_list_albums_only_with_pattern(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200,
        json=[
            _album("a1", "Trip 2023"),
            _album("a2", "Trip 2024"),
            _album("a3", "Birthdays"),
        ],
    )
    result = runner.invoke(
        app, ["list", "Trip *", "--albums-only", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
    assert {l["id"] for l in lines} == {"a1", "a2"}


def test_list_assets_only_skips_album_match(
    mock_router, base_url, api_key, monkeypatch
):
    """With --assets-only, a pattern that IS an album name must still
    be treated as a filename glob."""
    _cli_env(monkeypatch, base_url, api_key)
    # There IS an album called 'Vacation' but we want assets only.
    mock_router.get("/api/albums").respond(
        200, json=[_album("alb-1", "Vacation")]
    )
    mock_router.post("/api/search/metadata").respond(
        200, json=_search_response([_asset("a1", "Vacation.jpg")])
    )
    result = runner.invoke(
        app, ["list", "Vacation", "--assets-only", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
    assert all(l["kind"] == "asset" for l in lines)
    assert [l["id"] for l in lines] == ["a1"]


def test_list_rejects_both_albums_only_and_assets_only(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    result = runner.invoke(
        app, ["list", "--albums-only", "--assets-only"]
    )
    assert result.exit_code != 0


# ---- scope flags -----------------------------------------------------


def test_list_only_owned_uses_single_albums_call(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    route = mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Mine")]
    )
    result = runner.invoke(
        app, ["list", "--albums-only", "--only-owned", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    assert route.call_count == 1
    assert "shared" not in route.calls.last.request.url.params


def test_list_only_shared_filters_to_shared_with_me(
    mock_router, base_url, api_key, monkeypatch
):
    """--only-shared must issue a single GET /albums?shared=true call."""
    _cli_env(monkeypatch, base_url, api_key)

    def _handler(request):
        if request.url.params.get("shared") == "true":
            return httpx.Response(
                200, json=[_album("shared-1", "Shared")]
            )
        # The helper should NOT call the owned endpoint.
        return httpx.Response(500, text="should not be called")

    route = mock_router.get("/api/albums").mock(side_effect=_handler)
    result = runner.invoke(
        app, ["list", "--albums-only", "--only-shared", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    assert route.call_count == 1
    lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
    assert [l["id"] for l in lines] == ["shared-1"]


def test_list_rejects_only_owned_and_only_shared_together(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    result = runner.invoke(
        app, ["list", "--only-owned", "--only-shared"]
    )
    assert result.exit_code != 0


# ---- date range / limit ---------------------------------------------


def test_list_since_until_filters(
    mock_router, base_url, api_key, monkeypatch
):
    """--since and --until must be forwarded as takenAfter / takenBefore."""
    _cli_env(monkeypatch, base_url, api_key)

    mock_router.get("/api/albums").respond(200, json=[])

    captured: list[dict] = []

    def _handler(request):
        import json as _json
        body = _json.loads(request.content)
        captured.append(body)
        return httpx.Response(200, json=_search_response([]))

    mock_router.post("/api/search/metadata").mock(side_effect=_handler)
    result = runner.invoke(
        app,
        [
            "list",
            "--since",
            "2024-01-15",
            "--until",
            "2024-03-01",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    # Both the count-only call and the listing call must carry the
    # range; assert at least one of them does (first one is count).
    assert any(
        c.get("takenAfter", "").startswith("2024-01-15") for c in captured
    )
    assert any(
        c.get("takenBefore", "").startswith("2024-03-01") for c in captured
    )


def test_list_limit_caps_results(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[])
    items = [
        _asset(f"a{i}", f"{i}.jpg", f"2024-03-{i:02d}T10:00:00.000Z")
        for i in range(1, 6)
    ]
    mock_router.post("/api/search/metadata").respond(
        200, json=_search_response(items)
    )
    result = runner.invoke(
        app, ["list", "--limit", "3", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) == 3


def test_list_invalid_date_fails(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    result = runner.invoke(
        app, ["list", "--since", "not-a-date"]
    )
    assert result.exit_code != 0


# ---- misc ------------------------------------------------------------


def test_list_invalid_format_fails(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    result = runner.invoke(app, ["list", "--format", "yaml"])
    assert result.exit_code != 0


def test_list_default_limit_is_50(
    mock_router, base_url, api_key, monkeypatch
):
    """With no --limit flag, the CLI should cap output at 50 items."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[])
    items = [
        _asset(f"a{i:03d}", f"{i}.jpg", f"2024-01-01T00:00:00.000Z")
        for i in range(1, 101)
    ]
    # pretend the server knows there are 100 total
    response = _search_response(items[:50])
    response["assets"]["total"] = 100
    mock_router.post("/api/search/metadata").respond(200, json=response)
    result = runner.invoke(app, ["list", "--format", "json"])
    assert result.exit_code == 0, result.stdout
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) == 50


def test_list_footer_when_truncated(
    mock_router, base_url, api_key, monkeypatch
):
    """When more items exist than were displayed, emit a 'showing X
    of Y' footer on stderr (stdout stays pure JSON/table data)."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[])
    items = [
        _asset(f"a{i:03d}", f"{i}.jpg") for i in range(1, 11)
    ]
    response = _search_response(items)
    response["assets"]["total"] = 100
    mock_router.post("/api/search/metadata").respond(200, json=response)
    result = runner.invoke(app, ["list", "--limit", "10", "--format", "json"])
    assert result.exit_code == 0, result.stdout
    combined = result.stdout + (result.stderr or "")
    assert "showing 10 of 100" in combined.lower()


def test_list_footer_when_complete(
    mock_router, base_url, api_key, monkeypatch
):
    """When everything fits, footer says '<total> in total'."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[])
    items = [_asset("a1", "only.jpg")]
    response = _search_response(items)
    response["assets"]["total"] = 1
    mock_router.post("/api/search/metadata").respond(200, json=response)
    result = runner.invoke(app, ["list", "--format", "json"])
    assert result.exit_code == 0, result.stdout
    combined = result.stdout + (result.stderr or "")
    assert "1" in combined and "total" in combined.lower()


def test_list_footer_mentions_albums_and_assets_when_both(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "X", end_date="2024-01-01T00:00:00.000Z")]
    )
    response = _search_response([_asset("ast1", "f.jpg")])
    response["assets"]["total"] = 1
    mock_router.post("/api/search/metadata").respond(200, json=response)
    result = runner.invoke(app, ["list", "--format", "json"])
    assert result.exit_code == 0, result.stdout
    combined = result.stdout + (result.stderr or "")
    assert "album" in combined.lower() and "asset" in combined.lower()


def test_list_no_results_exits_nonzero(
    mock_router, base_url, api_key, monkeypatch
):
    """If a pattern matches nothing, it's an error (like download)."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[])
    mock_router.post("/api/search/metadata").respond(
        200, json=_search_response([])
    )
    result = runner.invoke(app, ["list", "Nothing*"])
    assert result.exit_code != 0
