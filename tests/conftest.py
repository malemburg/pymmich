"""Shared pytest fixtures for the pymmich test suite."""

from __future__ import annotations

import pytest
import respx

from pymmich.client import ImmichClient


BASE_URL = "https://immich.example.com"
API_KEY = "test-api-key-123"


@pytest.fixture
def base_url() -> str:
    """Base URL of the mocked Immich server."""
    return BASE_URL


@pytest.fixture
def api_key() -> str:
    """API key used to authenticate against the mocked server."""
    return API_KEY


@pytest.fixture
def mock_router():
    """Provide a respx router that catches all outgoing HTTP calls."""
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        yield router


@pytest.fixture
def client(base_url: str, api_key: str):
    """An ImmichClient configured against the mocked server."""
    with ImmichClient(base_url=base_url, api_key=api_key) as c:
        yield c
