"""Unit tests for core security functions."""
import pytest


class TestAuthMiddleware:
    """Tests for the optional auth middleware."""

    def test_dev_mode_allows_all(self, api_client):
        """In dev mode (AUTH_REQUIRED=false), all requests pass."""
        resp = api_client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_health_endpoint_always_public(self, api_client):
        """Health check should never require auth."""
        resp = api_client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
