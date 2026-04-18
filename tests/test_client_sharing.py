"""Tests for the user/sharing-related ImmichClient methods."""

from __future__ import annotations

import json

import httpx
import pytest

from pymmich.client import ImmichClient, ImmichError


# ---- /users ------------------------------------------------------------


def _user(user_id: str, name: str, email: str) -> dict:
    return {
        "id": user_id,
        "name": name,
        "email": email,
        "avatarColor": "primary",
        "profileChangedAt": "2024-01-01T00:00:00.000Z",
        "profileImagePath": "",
    }


def test_list_users(client: ImmichClient, mock_router):
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
        ],
    )
    users = client.list_users()
    assert [u.id for u in users] == ["u1", "u2"]
    assert users[0].name == "Alice"
    assert users[0].email == "alice@example.com"


def test_find_user_by_email_case_insensitive(client: ImmichClient, mock_router):
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
        ],
    )
    u = client.find_user("ALICE@example.COM")
    assert u is not None and u.id == "u1"


def test_find_user_by_name_case_insensitive(client: ImmichClient, mock_router):
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alice", "alice@example.com"),
            _user("u2", "Bob", "bob@example.com"),
        ],
    )
    u = client.find_user("alice")
    assert u is not None and u.id == "u1"


def test_find_user_email_wins_over_name(client: ImmichClient, mock_router):
    """If the identifier matches a different user's email exactly but
    someone else's name partially, the email match wins."""
    mock_router.get("/api/users").respond(
        200,
        json=[
            # user whose name matches the identifier by coincidence
            _user("u1", "charlie@example.com", "unrelated@example.com"),
            # user whose email matches the identifier
            _user("u2", "Charlie", "charlie@example.com"),
        ],
    )
    u = client.find_user("charlie@example.com")
    assert u is not None and u.id == "u2"


def test_find_user_not_found(client: ImmichClient, mock_router):
    mock_router.get("/api/users").respond(
        200, json=[_user("u1", "Alice", "alice@example.com")]
    )
    assert client.find_user("nobody") is None


def test_find_user_ambiguous_name_raises(client: ImmichClient, mock_router):
    mock_router.get("/api/users").respond(
        200,
        json=[
            _user("u1", "Alex", "alex1@example.com"),
            _user("u2", "Alex", "alex2@example.com"),
        ],
    )
    with pytest.raises(ImmichError, match="ambiguous"):
        client.find_user("alex")


# ---- GET /albums/{id} -------------------------------------------------


def test_get_album_parses_album_users(client: ImmichClient, mock_router):
    mock_router.get("/api/albums/alb-1").respond(
        200,
        json={
            "id": "alb-1",
            "albumName": "Trip",
            "assetCount": 0,
            "albumUsers": [
                {
                    "role": "editor",
                    "user": _user("u1", "Alice", "alice@example.com"),
                },
                {
                    "role": "viewer",
                    "user": _user("u2", "Bob", "bob@example.com"),
                },
            ],
        },
    )
    album = client.get_album("alb-1")
    assert album.id == "alb-1"
    assert len(album.album_users) == 2
    assert album.album_users[0].role == "editor"
    assert album.album_users[0].user.id == "u1"
    assert album.album_users[1].role == "viewer"


def test_list_albums_without_album_users_field(client: ImmichClient, mock_router):
    """``albumUsers`` may be missing on the list endpoint; default to []."""
    mock_router.get("/api/albums").respond(
        200,
        json=[{"id": "a1", "albumName": "X", "assetCount": 0}],
    )
    albums = client.list_albums()
    assert albums[0].album_users == []


# ---- PUT /albums/{id}/users ------------------------------------------


def test_add_users_to_album_default_role(client: ImmichClient, mock_router):
    route = mock_router.put("/api/albums/alb-1/users").respond(
        200,
        json={"id": "alb-1", "albumName": "T", "assetCount": 0, "albumUsers": []},
    )
    album = client.add_users_to_album("alb-1", ["u1", "u2"])
    assert album.id == "alb-1"
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "albumUsers": [
            {"userId": "u1", "role": "editor"},
            {"userId": "u2", "role": "editor"},
        ]
    }


def test_add_users_to_album_with_role(client: ImmichClient, mock_router):
    route = mock_router.put("/api/albums/alb-1/users").respond(
        200,
        json={"id": "alb-1", "albumName": "T", "assetCount": 0, "albumUsers": []},
    )
    client.add_users_to_album("alb-1", ["u1"], role="viewer")
    body = json.loads(route.calls.last.request.content)
    assert body == {"albumUsers": [{"userId": "u1", "role": "viewer"}]}


def test_add_users_to_album_empty_is_noop(client: ImmichClient, mock_router):
    """Calling with zero user ids must not hit the server."""
    route = mock_router.put("/api/albums/alb-1/users")
    album = client.add_users_to_album("alb-1", [])
    assert album is None
    assert not route.called


# ---- DELETE /albums/{id}/user/{userId} -------------------------------


def test_remove_user_from_album(client: ImmichClient, mock_router):
    route = mock_router.delete("/api/albums/alb-1/user/u1").respond(204)
    client.remove_user_from_album("alb-1", "u1")
    assert route.called


def test_remove_user_from_album_raises_on_error(client: ImmichClient, mock_router):
    mock_router.delete("/api/albums/alb-1/user/u1").respond(404, text="not found")
    with pytest.raises(ImmichError):
        client.remove_user_from_album("alb-1", "u1")


# ---- album glob matching ---------------------------------------------


def _album(album_id: str, name: str) -> dict:
    return {"id": album_id, "albumName": name, "assetCount": 0}


def test_find_albums_matching_plain_name(client: ImmichClient, mock_router):
    mock_router.get("/api/albums").respond(
        200,
        json=[_album("a1", "Trip"), _album("a2", "Vacation")],
    )
    found = client.find_albums_matching(["Trip"])
    assert [a.id for a in found] == ["a1"]


def test_find_albums_matching_glob(client: ImmichClient, mock_router):
    mock_router.get("/api/albums").respond(
        200,
        json=[
            _album("a1", "Trip 2023"),
            _album("a2", "Trip 2024"),
            _album("a3", "Birthdays"),
        ],
    )
    found = client.find_albums_matching(["Trip *"])
    assert {a.id for a in found} == {"a1", "a2"}


def test_find_albums_matching_is_case_insensitive_by_default(
    client: ImmichClient, mock_router
):
    mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Vacation")]
    )
    found = client.find_albums_matching(["vacation"])
    assert [a.id for a in found] == ["a1"]


def test_find_albums_matching_case_sensitive(
    client: ImmichClient, mock_router
):
    mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Vacation")]
    )
    found = client.find_albums_matching(["vacation"], case_sensitive=True)
    assert found == []


def test_find_albums_matching_dedupes_across_patterns(
    client: ImmichClient, mock_router
):
    mock_router.get("/api/albums").respond(
        200,
        json=[_album("a1", "Trip 2024"), _album("a2", "Trip 2025")],
    )
    found = client.find_albums_matching(["Trip *", "*2024"])
    # 'a1' matches both patterns, must only appear once
    assert [a.id for a in found] == ["a1", "a2"]


# ---- list_albums(shared=...) --------------------------------------------


def test_list_albums_default_sends_no_shared_param(
    client: ImmichClient, mock_router
):
    route = mock_router.get("/api/albums").respond(200, json=[])
    client.list_albums()
    assert route.called
    url = route.calls.last.request.url
    assert "shared" not in url.params


def test_list_albums_shared_true_sends_shared_query(
    client: ImmichClient, mock_router
):
    route = mock_router.get("/api/albums").respond(200, json=[])
    client.list_albums(shared=True)
    url = route.calls.last.request.url
    assert url.params.get("shared") == "true"


def test_list_albums_shared_false_sends_shared_query(
    client: ImmichClient, mock_router
):
    route = mock_router.get("/api/albums").respond(200, json=[])
    client.list_albums(shared=False)
    url = route.calls.last.request.url
    assert url.params.get("shared") == "false"


def test_find_album_include_shared_issues_both_requests(
    client: ImmichClient, mock_router
):
    """``include_shared=True`` must fetch both owned (``GET /albums``)
    and shared (``GET /albums?shared=true``) and merge them."""
    route = mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Trip")]
    )
    client.find_album("Trip", include_shared=True)
    urls = [str(c.request.url) for c in route.calls]
    assert any("shared=true" in u for u in urls)
    assert any("shared=true" not in u for u in urls)


def test_find_album_only_owned_issues_single_request(
    client: ImmichClient, mock_router
):
    route = mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Trip")]
    )
    client.find_album("Trip", include_shared=False)
    assert route.call_count == 1
    assert "shared" not in route.calls.last.request.url.params


def test_find_album_merges_owned_and_shared(
    client: ImmichClient, mock_router
):
    """Albums unique to either endpoint must both be considered."""
    def _handler(request):
        import httpx as _httpx
        if request.url.params.get("shared") == "true":
            return _httpx.Response(
                200,
                json=[
                    _album("shared-1", "Shared With Me"),
                    _album("both-1", "Overlap"),  # also in owned
                ],
            )
        return _httpx.Response(
            200,
            json=[
                _album("owned-1", "Mine"),
                _album("both-1", "Overlap"),
            ],
        )

    mock_router.get("/api/albums").mock(side_effect=_handler)

    assert client.find_album("Mine", include_shared=True).id == "owned-1"
    assert (
        client.find_album("Shared With Me", include_shared=True).id
        == "shared-1"
    )
    # Deduplication: the overlap album must not be duplicated in the
    # results of find_albums_matching.
    matched = client.find_albums_matching(["*"], include_shared=True)
    ids = [a.id for a in matched]
    assert ids.count("both-1") == 1
    assert set(ids) == {"owned-1", "both-1", "shared-1"}


def test_ensure_album_propagates_include_shared(
    client: ImmichClient, mock_router
):
    route = mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Trip")]
    )
    client.ensure_album("Trip", include_shared=True)
    # Two calls: owned + shared
    assert route.call_count == 2


def test_find_albums_matching_only_owned_single_call(
    client: ImmichClient, mock_router
):
    route = mock_router.get("/api/albums").respond(
        200, json=[_album("a1", "Trip 2024")]
    )
    client.find_albums_matching(["Trip *"], include_shared=False)
    assert route.call_count == 1
    assert "shared" not in route.calls.last.request.url.params


def test_list_albums_shared_true_returns_shared_with_me(
    client: ImmichClient, mock_router
):
    """With ``shared=True`` the server returns both owned and shared albums.
    pymmich must expose those verbatim."""
    mock_router.get("/api/albums").respond(
        200,
        json=[
            {"id": "mine", "albumName": "Mine", "assetCount": 0},
            {"id": "theirs", "albumName": "Shared with me", "assetCount": 5},
        ],
    )
    albums = client.list_albums(shared=True)
    assert {a.id for a in albums} == {"mine", "theirs"}
