"""Tests for the ``pymmich unshare`` command."""

from __future__ import annotations

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


def _album_user(user_id: str, name: str, email: str, role: str = "editor") -> dict:
    return {"role": role, "user": _user(user_id, name, email)}


def _album(album_id: str, name: str, users: list[dict] | None = None) -> dict:
    return {
        "id": album_id,
        "albumName": name,
        "assetCount": 0,
        "albumUsers": users or [],
    }


def test_unshare_removes_shared_user(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Vacation")]
    )
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
        ],
    )
    mock_router.get("/api/albums/a1").respond(
        200,
        json=_album(
            "a1",
            "Vacation",
            [_album_user("u2", "Bob", "bob@example.com")],
        ),
    )
    delete = mock_router.delete("/api/albums/a1/user/u2").respond(204)

    result = runner.invoke(
        app, ["unshare", "Vacation", "--with", "bob@example.com"]
    )
    assert result.exit_code == 0, result.stdout
    assert delete.called


def test_unshare_warns_when_user_not_shared(
    mock_router, base_url, api_key, monkeypatch
):
    """Removing a user who is not among the shared users must warn
    but not fail."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Vacation")]
    )
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
        ],
    )
    # Album has no shared users
    mock_router.get("/api/albums/a1").respond(
        200, json=_album("a1", "Vacation", [])
    )
    delete = mock_router.delete("/api/albums/a1/user/u2")

    result = runner.invoke(
        app, ["unshare", "Vacation", "--with", "bob@example.com"]
    )
    assert result.exit_code == 0, result.stdout
    assert not delete.called
    combined = (result.stdout or "") + (result.stderr or "")
    assert "warning" in combined.lower() or "not" in combined.lower()


def test_unshare_glob_multiple_albums(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200,
        json=[
            _album("a1", "Trip 2023"),
            _album("a2", "Trip 2024"),
        ],
    )
    mock_router.get("/api/users").respond(
        200,
        json=[_user("u1", "Alice", "alice@example.com")],
    )
    mock_router.get("/api/albums/a1").respond(
        200,
        json=_album(
            "a1", "Trip 2023", [_album_user("u1", "Alice", "alice@example.com")]
        ),
    )
    mock_router.get("/api/albums/a2").respond(
        200,
        json=_album(
            "a2", "Trip 2024", [_album_user("u1", "Alice", "alice@example.com")]
        ),
    )
    d1 = mock_router.delete("/api/albums/a1/user/u1").respond(204)
    d2 = mock_router.delete("/api/albums/a2/user/u1").respond(204)

    result = runner.invoke(
        app, ["unshare", "Trip *", "--with", "alice@example.com"]
    )
    assert result.exit_code == 0, result.stdout
    assert d1.called and d2.called


def test_unshare_unknown_user_fails(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[_album("a1", "A")])
    mock_router.get("/api/users").respond(200, json=[])
    result = runner.invoke(
        app, ["unshare", "A", "--with", "ghost@example.com"]
    )
    assert result.exit_code != 0


def test_unshare_no_matching_album_fails(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(200, json=[])
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    result = runner.invoke(
        app, ["unshare", "Nope*", "--with", "alice@example.com"]
    )
    assert result.exit_code != 0


def test_unshare_default_hits_both_album_endpoints(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    route = mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Vacation")]
    )
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    mock_router.get("/api/albums/a1").respond(
        200,
        json=_album(
            "a1",
            "Vacation",
            [_album_user("u1", "Alice", "alice@example.com")],
        ),
    )
    mock_router.delete("/api/albums/a1/user/u1").respond(204)
    result = runner.invoke(
        app, ["unshare", "Vacation", "--with", "alice@example.com"]
    )
    assert result.exit_code == 0, result.stdout
    urls = [str(c.request.url) for c in route.calls]
    assert any("shared=true" in u for u in urls)
    assert any("shared=true" not in u for u in urls)


def test_unshare_only_owned_flag(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    route = mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Vacation")]
    )
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    mock_router.get("/api/albums/a1").respond(
        200,
        json=_album(
            "a1",
            "Vacation",
            [_album_user("u1", "Alice", "alice@example.com")],
        ),
    )
    mock_router.delete("/api/albums/a1/user/u1").respond(204)
    result = runner.invoke(
        app,
        [
            "unshare",
            "Vacation",
            "--with",
            "alice@example.com",
            "--only-owned",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert route.call_count == 1
    assert "shared" not in route.calls.last.request.url.params


def test_unshare_mixed_users_some_shared_some_not(
    mock_router, base_url, api_key, monkeypatch
):
    """One user is shared, another is not: both are processed, the
    missing one triggers a warning, the shared one is removed, overall
    exit code stays 0."""
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Vacation")]
    )
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
        ],
    )
    mock_router.get("/api/albums/a1").respond(
        200,
        json=_album(
            "a1",
            "Vacation",
            [_album_user("u2", "Bob", "bob@example.com")],
        ),
    )
    delete_bob = mock_router.delete("/api/albums/a1/user/u2").respond(204)
    delete_alice = mock_router.delete("/api/albums/a1/user/u1")

    result = runner.invoke(
        app,
        [
            "unshare",
            "Vacation",
            "--with",
            "alice@example.com",
            "--with",
            "bob@example.com",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert delete_bob.called
    assert not delete_alice.called
    combined = (result.stdout or "") + (result.stderr or "")
    assert "alice" in combined.lower() or "not shared" in combined.lower()
