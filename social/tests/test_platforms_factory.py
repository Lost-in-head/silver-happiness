"""Tests for src/platforms/factory.py — get_reddit_adapter."""

import pytest
from unittest.mock import patch, MagicMock


class TestGetRedditAdapter:
    def test_returns_reddit_adapter_instance(self):
        from src.platforms.factory import get_reddit_adapter
        from src.platforms.reddit import RedditAdapter

        adapter = get_reddit_adapter({})
        assert isinstance(adapter, RedditAdapter)

    def test_env_username_takes_priority_over_config(self, monkeypatch):
        from src.platforms.factory import get_reddit_adapter

        monkeypatch.setenv("REDDIT_USERNAME", "env_user")
        monkeypatch.setenv("REDDIT_PASSWORD", "env_pass")
        config = {"platforms": {"reddit": {"username": "cfg_user", "password": "cfg_pass"}}}

        adapter = get_reddit_adapter(config)
        assert adapter.username == "env_user"
        assert adapter.password == "env_pass"

    def test_config_credentials_used_when_no_env(self):
        from src.platforms.factory import get_reddit_adapter

        config = {"platforms": {"reddit": {"username": "cfg_user", "password": "cfg_pass"}}}
        adapter = get_reddit_adapter(config)
        assert adapter.username == "cfg_user"
        assert adapter.password == "cfg_pass"

    def test_empty_credentials_when_nothing_set(self):
        from src.platforms.factory import get_reddit_adapter

        adapter = get_reddit_adapter({})
        assert adapter.username == ""
        assert adapter.password == ""

    def test_proxy_url_from_env(self, monkeypatch):
        from src.platforms.factory import get_reddit_adapter

        monkeypatch.setenv("PROXY_URL", "http://proxy.example.com:8080")
        adapter = get_reddit_adapter({})
        assert adapter.proxy_url == "http://proxy.example.com:8080"

    def test_proxy_url_from_config(self):
        from src.platforms.factory import get_reddit_adapter

        config = {"geolocation": {"proxy_url": "http://cfg-proxy:3128"}}
        adapter = get_reddit_adapter(config)
        assert adapter.proxy_url == "http://cfg-proxy:3128"

    def test_env_proxy_takes_priority_over_config(self, monkeypatch):
        from src.platforms.factory import get_reddit_adapter

        monkeypatch.setenv("PROXY_URL", "http://env-proxy:8080")
        config = {"geolocation": {"proxy_url": "http://cfg-proxy:3128"}}
        adapter = get_reddit_adapter(config)
        assert adapter.proxy_url == "http://env-proxy:8080"

    def test_proxy_username_password_from_env(self, monkeypatch):
        from src.platforms.factory import get_reddit_adapter

        monkeypatch.setenv("PROXY_USERNAME", "proxy_user")
        monkeypatch.setenv("PROXY_PASSWORD", "proxy_pass")
        adapter = get_reddit_adapter({})
        assert adapter.proxy_username == "proxy_user"
        assert adapter.proxy_password == "proxy_pass"

    def test_geolocation_timezone_from_config(self):
        from src.platforms.factory import get_reddit_adapter

        config = {"geolocation": {"timezone_id": "Europe/Paris", "locale": "fr-FR"}}
        adapter = get_reddit_adapter(config)
        assert adapter.timezone_id == "Europe/Paris"
        assert adapter.locale == "fr-FR"

    def test_default_geolocation_when_not_set(self):
        from src.platforms.factory import get_reddit_adapter

        adapter = get_reddit_adapter({})
        assert adapter.timezone_id == "America/New_York"
        assert adapter.locale == "en-US"

    def test_headless_true_by_default(self):
        from src.platforms.factory import get_reddit_adapter

        adapter = get_reddit_adapter({})
        assert adapter.headless is True

    def test_headless_false_passthrough(self):
        from src.platforms.factory import get_reddit_adapter

        adapter = get_reddit_adapter({}, headless=False)
        assert adapter.headless is False

    def test_none_config_uses_defaults(self):
        from src.platforms.factory import get_reddit_adapter

        adapter = get_reddit_adapter(None)
        assert adapter.username == ""
        assert adapter.timezone_id == "America/New_York"
