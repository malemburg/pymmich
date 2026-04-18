"""Tests for the ``pymmich list-users`` command and its client support."""

from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from pymmich.cli import app
from pymmich.client import ImmichClient


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


# ---- client: find_users_matching ---------------------------------------


def test_find_users_matching_no_patterns_returns_all(
    client: ImmichClient, mock_router
):
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
        ],
    )
    users = client.find_users_matching([])
    assert [u.id for u in users] == ["u1", "u2"]


def test_find_users_matching_by_name_glob(
    client: ImmichClient, mock_router
):
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Albert", "albert@example.com"),
            _user("u3", "Bob", "bob@example.com"),
        ],
    )
    users = client.find_users_matching(["Al*"])
    assert {u.id for u in users} == {"u1", "u2"}


def test_find_users_matching_by_email_substring(
    client: ImmichClient, mock_router
):
    """A plain name (no glob chars) should match if it's a substring
    of either name OR email — so e.g. the domain can be used."""
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@acme.test"),
            _user("u2", "Bob", "bob@other.test"),
            _user("u3", "Carol", "carol@acme.test"),
        ],
    )
    users = client.find_users_matching(["acme"])
    assert {u.id for u in users} == {"u1", "u3"}


def test_find_users_matching_case_insensitive_default(
    client: ImmichClient, mock_router
):
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    users = client.find_users_matching(["alice"])
    assert [u.id for u in users] == ["u1"]


def test_find_users_matching_case_sensitive(
    client: ImmichClient, mock_router
):
    # Capitalise both name and email so a lowercase pattern can't
    # hit the email substring by accident.
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "Alice@Example.COM")]
    )
    users = client.find_users_matching(["alice"], case_sensitive=True)
    assert users == []
    users = client.find_users_matching(["Alice"], case_sensitive=True)
    assert [u.id for u in users] == ["u1"]


def test_find_users_matching_dedupes_across_patterns(
    client: ImmichClient, mock_router
):
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
        ],
    )
    users = client.find_users_matching(["Alice", "alice@example.com"])
    assert [u.id for u in users] == ["u1"]


# ---- CLI: list-users ---------------------------------------------------


def test_list_users_default_json(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
        ],
    )
    result = runner.invoke(app, ["list-users", "--format", "json"])
    assert result.exit_code == 0, result.stdout
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    parsed = [json.loads(l) for l in lines]
    assert {p["id"] for p in parsed} == {"u1", "u2"}
    assert all(p["kind"] == "user" for p in parsed)
    # each record must include both name and email
    assert all("name" in p and "email" in p for p in parsed)


def test_list_users_default_format_is_table(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0, result.stdout
    assert "Alice" in result.stdout
    assert "alice@example.com" in result.stdout


def test_list_users_long_format_has_header(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    result = runner.invoke(app, ["list-users", "--format", "long"])
    assert result.exit_code == 0, result.stdout
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) >= 2
    header = lines[0].upper()
    assert "NAME" in header and "EMAIL" in header
    # data line
    assert any("Alice" in l for l in lines[1:])
    assert any("alice@example.com" in l for l in lines[1:])


def test_list_users_with_pattern(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
            _user("u3", "Albert", "albert@example.com"),
        ],
    )
    result = runner.invoke(
        app, ["list-users", "Al*", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
    assert {l["id"] for l in lines} == {"u1", "u3"}


def test_list_users_no_match_fails(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    result = runner.invoke(
        app, ["list-users", "Nobody*", "--format", "json"]
    )
    assert result.exit_code != 0


def test_list_users_default_limit_50(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    users = [
        _user(f"u{i}", f"User{i}", f"user{i}@example.com")
        for i in range(1, 61)
    ]
    mock_router.get("/api/users").respond(200, json=users)
    result = runner.invoke(app, ["list-users", "--format", "json"])
    assert result.exit_code == 0, result.stdout
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) == 50


def test_list_users_footer_when_truncated(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    users = [
        _user(f"u{i}", f"User{i}", f"user{i}@example.com")
        for i in range(1, 21)
    ]
    mock_router.get("/api/users").respond(200, json=users)
    result = runner.invoke(
        app, ["list-users", "--limit", "5", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    combined = result.stdout + (result.stderr or "")
    assert "showing 5 of 20 users" in combined.lower()


def test_list_users_footer_when_complete(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/users").respond(
        200,
        json=[_user("u1", "Alice", "alice@example.com")],
    )
    result = runner.invoke(app, ["list-users", "--format", "json"])
    assert result.exit_code == 0, result.stdout
    combined = result.stdout + (result.stderr or "")
    assert "1 user" in combined.lower() and "total" in combined.lower()


def test_list_users_limit_zero_disables_cap(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    users = [
        _user(f"u{i}", f"User{i}", f"user{i}@example.com")
        for i in range(1, 71)
    ]
    mock_router.get("/api/users").respond(200, json=users)
    result = runner.invoke(
        app, ["list-users", "--limit", "0", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) == 70


def test_list_users_invalid_format_fails(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    result = runner.invoke(app, ["list-users", "--format", "yaml"])
    assert result.exit_code != 0


def test_list_users_case_sensitive(
    mock_router, base_url, api_key, monkeypatch
):
    _cli_env(monkeypatch, base_url, api_key)
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "Alice@Example.COM")]
    )
    # With --case-sensitive, 'alice' (lowercase) must not match 'Alice'
    # or the capitalised email.
    result = runner.invoke(
        app, ["list-users", "alice", "--case-sensitive", "--format", "json"]
    )
    assert result.exit_code != 0
