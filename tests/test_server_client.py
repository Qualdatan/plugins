# SPDX-License-Identifier: AGPL-3.0-only
"""Tests fuer :mod:`qualdatan_plugins.server_client`.

Nutzt ``httpx.MockTransport`` — keine Netzwerkzugriffe.
"""

from __future__ import annotations

import httpx
import pytest

from qualdatan_plugins.server_client import (
    PluginServerClient,
    PluginServerError,
    TapEntry,
    TapVersion,
)

# --- Fixtures ----------------------------------------------------------------

SAMPLE_ENTRY = {
    "namespace": "qualdatan",
    "name": "bim-basic",
    "repo_url": "https://github.com/qualdatan/bim-basic",
    "latest_version": "0.3.0",
    "label": "BIM Basic",
    "description": "Grundbegriffe BIM",
    "keywords": ["bim", "bau"],
    "license": "CC-BY-NC-SA-4.0",
}

SAMPLE_VERSION = {
    "version": "0.3.0",
    "tag": "v0.3.0",
    "commit_sha": "deadbeef" * 5,
    "published_at": "2026-04-01T12:00:00Z",
}


def _make_client(handler, *, token: str | None = None) -> PluginServerClient:
    transport = httpx.MockTransport(handler)
    return PluginServerClient(
        base_url="http://test.local",
        token=token,
        client=httpx.Client(transport=transport),
    )


# --- search ------------------------------------------------------------------


def test_search_parses_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/index/search"
        assert request.url.params["q"] == "bim"
        assert request.url.params["limit"] == "10"
        return httpx.Response(200, json={"results": [SAMPLE_ENTRY]})

    with _make_client(handler) as client:
        hits = client.search("bim", limit=10)

    assert len(hits) == 1
    assert isinstance(hits[0], TapEntry)
    assert hits[0].id == "qualdatan/bim-basic"
    assert hits[0].keywords == ("bim", "bau")


def test_search_empty_query_defaults():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    with _make_client(handler) as client:
        assert client.search() == []


# --- get_tap -----------------------------------------------------------------


def test_get_tap_returns_entry_and_versions():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/index/taps/qualdatan/bim-basic"
        return httpx.Response(
            200,
            json={"entry": SAMPLE_ENTRY, "versions": [SAMPLE_VERSION]},
        )

    with _make_client(handler) as client:
        entry, versions = client.get_tap("qualdatan", "bim-basic")

    assert entry.id == "qualdatan/bim-basic"
    assert len(versions) == 1
    assert isinstance(versions[0], TapVersion)
    assert versions[0].version == "0.3.0"
    assert versions[0].tag == "v0.3.0"


# --- error handling ----------------------------------------------------------


def test_404_raises_plugin_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    with _make_client(handler) as client:
        with pytest.raises(PluginServerError, match="404"):
            client.get_tap("qualdatan", "missing")


def test_500_raises_plugin_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with _make_client(handler) as client:
        with pytest.raises(PluginServerError, match="500"):
            client.search("anything")


def test_malformed_json_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"not-json{", headers={"content-type": "application/json"}
        )

    with _make_client(handler) as client:
        with pytest.raises(PluginServerError, match="malformed JSON"):
            client.search("x")


def test_missing_required_field_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        bad = {k: v for k, v in SAMPLE_ENTRY.items() if k != "namespace"}
        return httpx.Response(200, json={"results": [bad]})

    with _make_client(handler) as client:
        with pytest.raises(PluginServerError, match="missing required field"):
            client.search("x")


def test_search_wrong_envelope_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})  # wrong key

    with _make_client(handler) as client:
        with pytest.raises(PluginServerError, match="results"):
            client.search()


# --- healthz -----------------------------------------------------------------


def test_healthz_happy_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/healthz"
        return httpx.Response(200, json={"status": "ok", "version": "1.2.3"})

    with _make_client(handler) as client:
        data = client.healthz()
    assert data == {"status": "ok", "version": "1.2.3"}


# --- register_tap ------------------------------------------------------------


def test_register_tap_sends_authorization_header():
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        assert request.method == "POST"
        assert request.url.path == "/taps"
        return httpx.Response(201, json={"entry": SAMPLE_ENTRY})

    with _make_client(handler, token="secret-token-123") as client:
        entry = client.register_tap("qualdatan", "https://github.com/qualdatan/bim-basic")

    assert seen_headers.get("authorization") == "Bearer secret-token-123"
    assert entry.id == "qualdatan/bim-basic"


def test_register_tap_without_token_raises():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not hit the network")

    with _make_client(handler) as client:
        with pytest.raises(PluginServerError, match="bearer token"):
            client.register_tap("qualdatan", "https://x/y")


# --- base URL resolution -----------------------------------------------------


def test_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("QUALDATAN_PLUGIN_SERVER", "https://env.example.com")
    c = PluginServerClient()
    try:
        assert c._base_url == "https://env.example.com"
    finally:
        c.close()


def test_ctor_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("QUALDATAN_PLUGIN_SERVER", "https://env.example.com")
    c = PluginServerClient(base_url="https://explicit.example.com/")
    try:
        assert c._base_url == "https://explicit.example.com"
    finally:
        c.close()


def test_default_url_when_nothing_set(monkeypatch):
    monkeypatch.delenv("QUALDATAN_PLUGIN_SERVER", raising=False)
    c = PluginServerClient()
    try:
        assert c._base_url == PluginServerClient.DEFAULT_URL
    finally:
        c.close()


# --- ownership of injected client -------------------------------------------


def test_injected_client_is_not_closed_on_exit():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "ok"}))
    injected = httpx.Client(transport=transport)
    with PluginServerClient(base_url="http://t", client=injected) as c:
        c.healthz()
    # injected client must still be usable (close() on client is idempotent but
    # we check the internal flag by using it again):
    assert not injected.is_closed
    injected.close()
