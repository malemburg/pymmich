"""Tests for the ``pymmich share`` command."""

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


def _user(user_id: str, name: str, email: str) -> dict:
    return {
        "id": user_id,
        "name": name,
        "email": email,
        "avatarColor": "primary",
        "profileChangedAt": "2024-01-01T00:00:00.000Z",
        "profileImagePath": "",
    }


def _album(album_id: str, name: str, users: list[dict] | None = None) -> dict:
    return {
        "id": album_id,
        "albumName": name,
        "assetCount": 0,
        "albumUsers": users or [],
    }


# ---- share -----------------------------------------------------------


def test_share_single_album_single_user_by_email(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)

    mock_router.get("/api/albums").respond(
        200, json=[_album("alb-1", "Vacation")]
    )
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
        ],
    )
    share = mock_router.put("/api/albums/alb-1/users").respond(
        200, json=_album("alb-1", "Vacation")
    )

    result = runner.invoke(
        app, ["share", "Vacation", "--with", "bob@example.com"]
    )
    assert result.exit_code == 0, result.stdout
    body = json.loads(share.calls.last.request.content)
    assert body == {"albumUsers": [{"userId": "u2", "role": "editor"}]}


def test_share_glob_matches_multiple_albums(
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
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    r1 = mock_router.put("/api/albums/a1/users").respond(
        200, json=_album("a1", "Trip 2023")
    )
    r2 = mock_router.put("/api/albums/a2/users").respond(
        200, json=_album("a2", "Trip 2024")
    )

    result = runner.invoke(
        app, ["share", "Trip *", "--with", "alice@example.com"]
    )
    assert result.exit_code == 0, result.stdout
    assert r1.called and r2.called


def test_share_multiple_users_by_name_and_email(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "A")]
    )
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
        ],
    )
    share = mock_router.put("/api/albums/a1/users").respond(
        200, json=_album("a1", "A")
    )

    result = runner.invoke(
        app,
        [
            "share",
            "A",
            "--with",
            "Alice",
            "--with",
            "bob@example.com",
        ],
    )
    assert result.exit_code == 0, result.stdout
    body = json.loads(share.calls.last.request.content)
    user_ids = {e["userId"] for e in body["albumUsers"]}
    assert user_ids == {"u1", "u2"}
    assert all(e["role"] == "editor" for e in body["albumUsers"])


def test_share_with_viewer_role(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[_album("a1", "A")])
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    share = mock_router.put("/api/albums/a1/users").respond(
        200, json=_album("a1", "A")
    )
    result = runner.invoke(
        app,
        [
            "share",
            "A",
            "--with",
            "alice@example.com",
            "--role",
            "viewer",
        ],
    )
    assert result.exit_code == 0, result.stdout
    body = json.loads(share.calls.last.request.content)
    assert body["albumUsers"][0]["role"] == "viewer"


def test_share_invalid_role(mock_router, base_url, api_key, monkeypatch):
    _cli_env(monkeypatch, base_url, api_key)
    result = runner.invoke(
        app,
        [
            "share",
            "A",
            "--with",
            "alice@example.com",
            "--role",
            "owner",  # not allowed
        ],
    )
    assert result.exit_code != 0


def test_share_no_matching_album_fails(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[])
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    result = runner.invoke(
        app, ["share", "Nope", "--with", "alice@example.com"]
    )
    assert result.exit_code != 0


def test_share_unknown_user_fails(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "A")]
    )
    mock_router.get("/api/users").respond(200, json=[])
    result = runner.invoke(
        app, ["share", "A", "--with", "ghost@example.com"]
    )
    assert result.exit_code != 0


def test_share_requires_with_option(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    result = runner.invoke(app, ["share", "A"])
    # Either typer rejects (missing required option) or we do.
    assert result.exit_code != 0


def test_share_case_sensitive_flag(
    mock_router, base_url, api_key, monkeypatch
):
    """With --case-sensitive, a lowercase pattern should not match 'Vacation'."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Vacation")]
    )
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    result = runner.invoke(
        app,
        [
            "share",
            "vacation",
            "--with",
            "alice@example.com",
            "--case-sensitive",
        ],
    )
    assert result.exit_code != 0


def test_share_default_hits_both_album_endpoints(
    mock_router, base_url, api_key, monkeypatch
):
    """Default ``pymmich share`` must hit both owned and shared album
    endpoints so shared-with-me albums are visible too."""
    _cli_env(monkeypatch, base_url, api_key)
    route = mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Vacation")]
    )
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    mock_router.put("/api/albums/a1/users").respond(
        200, json=_album("a1", "Vacation")
    )
    result = runner.invoke(
        app, ["share", "Vacation", "--with", "alice@example.com"]
    )
    assert result.exit_code == 0, result.stdout
    urls = [str(c.request.url) for c in route.calls]
    assert any("shared=true" in u for u in urls)
    assert any("shared=true" not in u for u in urls)


def test_share_only_owned_flag(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    route = mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Vacation")]
    )
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    mock_router.put("/api/albums/a1/users").respond(
        200, json=_album("a1", "Vacation")
    )
    result = runner.invoke(
        app,
        [
            "share",
            "Vacation",
            "--with",
            "alice@example.com",
            "--only-owned",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert route.call_count == 1
    assert "shared" not in route.calls.last.request.url.params
