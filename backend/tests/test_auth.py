import pytest

from app.services.auth_service import AuthService


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = AuthService.hash_password("mypassword")
        assert AuthService.verify_password("mypassword", hashed)
        assert not AuthService.verify_password("wrongpassword", hashed)


class TestJWT:
    def test_access_token_roundtrip(self):
        payload = {"sub": "user-123", "email": "a@b.com", "name": "Alice"}
        token = AuthService.create_access_token(payload)
        decoded = AuthService.decode_access_token(token)
        assert decoded is not None
        assert decoded["sub"] == "user-123"
        assert decoded["type"] == "access"

    def test_refresh_token_roundtrip(self):
        payload = {"sub": "user-123", "email": "a@b.com", "name": "Alice"}
        token = AuthService.create_refresh_token(payload)
        decoded = AuthService.decode_refresh_token(token)
        assert decoded is not None
        assert decoded["type"] == "refresh"

    def test_access_token_rejected_as_refresh(self):
        payload = {"sub": "u", "email": "a@b.com", "name": "A"}
        access = AuthService.create_access_token(payload)
        assert AuthService.decode_refresh_token(access) is None

    def test_invalid_token_returns_none(self):
        assert AuthService.decode_access_token("not.a.token") is None


class TestAuthEndpoints:
    def test_register_and_login(self, client):
        resp = client.post(
            "/auth/register",
            json={"email": "newuser@test.com", "password": "password1", "name": "New User"},
        )
        assert resp.status_code == 201
        assert resp.json()["email"] == "newuser@test.com"

        resp = client.post(
            "/auth/login",
            json={"email": "newuser@test.com", "password": "password1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    def test_duplicate_email_rejected(self, client):
        client.post(
            "/auth/register",
            json={"email": "dup@test.com", "password": "password1", "name": "Dup"},
        )
        resp = client.post(
            "/auth/register",
            json={"email": "dup@test.com", "password": "password1", "name": "Dup2"},
        )
        assert resp.status_code == 409

    def test_wrong_password_rejected(self, client):
        client.post(
            "/auth/register",
            json={"email": "wp@test.com", "password": "correctpass", "name": "WP"},
        )
        resp = client.post("/auth/login", json={"email": "wp@test.com", "password": "wrongpass"})
        assert resp.status_code == 401

    def test_short_password_rejected(self, client):
        resp = client.post(
            "/auth/register",
            json={"email": "short@test.com", "password": "abc", "name": "Short"},
        )
        assert resp.status_code == 422

    def test_protected_endpoint_requires_token(self, client):
        resp = client.get("/api/history/runs")
        assert resp.status_code == 403

    def test_protected_endpoint_with_valid_token(self, client, auth_headers):
        resp = client.get("/api/history/runs", headers=auth_headers)
        assert resp.status_code == 200
