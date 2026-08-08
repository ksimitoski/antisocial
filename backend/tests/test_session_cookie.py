import os
import sys
import importlib.util
import unittest.mock as mock
import pytest

# Load frontend app module directly from file path to avoid conflict with backend app package
frontend_app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/app.py"))
spec = importlib.util.spec_from_file_location("frontend_app", frontend_app_path)
frontend_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frontend_module)
flask_app = frontend_module.app

def test_login_without_remember_me_creates_session_cookie():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        # Mock backend login response
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "fake_token",
            "user_id": 1,
            "username": "testuser",
            "role": "user"
        }

        with mock.patch("requests.post", return_value=mock_resp), \
             mock.patch("requests.get", return_value=mock_resp):
            res = client.post("/login", data={
                "username_or_email": "testuser",
                "password": "Password123!"
            })

            assert res.status_code == 302
            cookie_headers = res.headers.getlist("Set-Cookie")
            session_cookie = [h for h in cookie_headers if "session=" in h]
            assert len(session_cookie) > 0
            # Without remember_me, cookie should NOT contain Expires or Max-Age (browser session cookie)
            assert "Expires=" not in session_cookie[0]
            assert "Max-Age=" not in session_cookie[0]

def test_login_with_remember_me_creates_persistent_cookie():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "fake_token",
            "user_id": 1,
            "username": "testuser",
            "role": "user"
        }

        with mock.patch("requests.post", return_value=mock_resp), \
             mock.patch("requests.get", return_value=mock_resp):
            res = client.post("/login", data={
                "username_or_email": "testuser",
                "password": "Password123!",
                "remember_me": "1"
            })

            assert res.status_code == 302
            cookie_headers = res.headers.getlist("Set-Cookie")
            session_cookie = [h for h in cookie_headers if "session=" in h]
            assert len(session_cookie) > 0
            # With remember_me, cookie should contain Expires or Max-Age (persistent cookie)
            assert ("Expires=" in session_cookie[0] or "Max-Age=" in session_cookie[0])


def test_backend_login_remember_me_token_expiration(client):
    from jose import jwt
    from app.auth import SECRET_KEY, ALGORITHM
    import time

    # Register user
    username = f"remuser_{int(time.time())}"
    email = f"{username}@example.com"
    password = "SecurePassword123!"

    reg = client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    token = reg.json()["token"]
    client.get(f"/api/auth/confirm?token={token}")

    # Login without remember_me
    res_normal = client.post("/api/auth/login", json={
        "username_or_email": username,
        "password": password,
        "remember_me": False
    })
    token_normal = res_normal.json()["access_token"]
    payload_normal = jwt.decode(token_normal, SECRET_KEY, algorithms=[ALGORITHM])

    # Login with remember_me
    res_remember = client.post("/api/auth/login", json={
        "username_or_email": username,
        "password": password,
        "remember_me": True
    })
    token_remember = res_remember.json()["access_token"]
    payload_remember = jwt.decode(token_remember, SECRET_KEY, algorithms=[ALGORITHM])

    # Expire time for remember_me should be significantly greater than normal login
    assert payload_remember["exp"] > payload_normal["exp"] + 86400 * 30


def test_forwarded_ip_recorded_in_session(client):
    import time
    username = f"ipuser_{int(time.time())}"
    email = f"{username}@example.com"
    password = "SecurePassword123!"

    reg = client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    token = reg.json()["token"]
    client.get(f"/api/auth/confirm?token={token}")

    origin_ip = "203.0.113.195"
    res = client.post("/api/auth/login", json={
        "username_or_email": username,
        "password": password
    }, headers={"X-Forwarded-For": f"{origin_ip}, 10.0.0.1"})

    assert res.status_code == 200
    access_token = res.json()["access_token"]

    sess_res = client.get("/api/auth/sessions", headers={"Authorization": f"Bearer {access_token}"})
    assert sess_res.status_code == 200
    sessions = sess_res.json()
    assert len(sessions) > 0
    assert sessions[0]["ip_address"] == origin_ip


def test_frontend_2fa_redirect_flow():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        # Mock 403 response requiring 2FA
        mock_403 = mock.MagicMock()
        mock_403.status_code = 403
        mock_403.json.return_value = {
            "detail": "Two-factor authentication code required. Please enter your 6-digit authenticator code or recovery code."
        }

        # Mock 200 response upon valid 2FA code submission
        mock_200 = mock.MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            "access_token": "valid_2fa_token",
            "user_id": 5,
            "username": "totpuser",
            "role": "user"
        }

        with mock.patch("requests.post", return_value=mock_403):
            res_login = client.post("/login", data={
                "username_or_email": "totpuser",
                "password": "Password123!"
            })
            assert res_login.status_code == 302
            assert "/verify-2fa" in res_login.location

        with mock.patch("requests.post", return_value=mock_200), \
             mock.patch("requests.get", return_value=mock_200):
            res_2fa = client.post("/verify-2fa", data={"totp_code": "123456"})
            assert res_2fa.status_code == 302
            assert "/feed" in res_2fa.location
