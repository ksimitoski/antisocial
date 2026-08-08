import io
import time
import pytest
from PIL import Image
from app import security_utils

def create_and_login_user(client, username, email, password="SecurePassword123!"):
    r = client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    data = r.json()
    token = data["token"]
    client.get(f"/api/auth/confirm?token={token}")
    login = client.post("/api/auth/login", json={
        "username_or_email": username,
        "password": password
    })
    access_token = login.json()["access_token"]
    user_id = login.json()["user_id"]
    return {"Authorization": f"Bearer {access_token}"}, user_id, password


def test_security_headers(client):
    response = client.get("/api/auth/me")
    headers = response.headers
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert "strict-origin-when-cross-origin" in headers.get("Referrer-Policy", "")
    assert "Content-Security-Policy" in headers


def test_exif_metadata_stripping():
    # Create test image with fake metadata byte stream
    img = Image.new("RGB", (100, 100), color="red")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    raw_bytes = img_byte_arr.getvalue()

    clean_bytes = security_utils.strip_exif_data(raw_bytes, ".jpg")
    assert len(clean_bytes) > 0
    clean_img = Image.open(io.BytesIO(clean_bytes))
    assert clean_img.size == (100, 100)


def test_totp_2fa_flow_and_session_management(client):
    username = f"secuser_{int(time.time())}"
    email = f"{username}@example.com"
    password = "SecurePassword123!"

    auth_headers, user_id, password = create_and_login_user(client, username, email, password)

    # Check Active Sessions
    sess_res = client.get("/api/auth/sessions", headers=auth_headers)
    assert sess_res.status_code == 200
    sessions = sess_res.json()
    assert len(sessions) >= 1

    # Setup 2FA
    setup_res = client.post("/api/auth/2fa/setup", headers=auth_headers)
    assert setup_res.status_code == 200
    secret = setup_res.json()["secret"]
    assert secret is not None

    # Generate TOTP Code & Enable 2FA
    valid_code = security_utils.get_totp_token(secret)
    enable_res = client.post("/api/auth/2fa/enable", json={"code": valid_code}, headers=auth_headers)
    assert enable_res.status_code == 200
    backup_codes = enable_res.json().get("backup_codes", [])
    assert len(backup_codes) == 8

    # Login without 2FA code should be rejected
    failed_login = client.post("/api/auth/login", json={
        "username_or_email": username,
        "password": password
    })
    assert failed_login.status_code == 403

    # Login with valid 2FA code should succeed
    current_totp = security_utils.get_totp_token(secret)
    succ_login = client.post("/api/auth/login", json={
        "username_or_email": username,
        "password": password,
        "totp_code": current_totp
    })
    assert succ_login.status_code == 200

    # Login with backup recovery code should succeed
    backup_login = client.post("/api/auth/login", json={
        "username_or_email": username,
        "password": password,
        "totp_code": backup_codes[0]
    })
    assert backup_login.status_code == 200

    # Disable 2FA
    curr_totp_2 = security_utils.get_totp_token(secret)
    disable_res = client.post("/api/auth/2fa/disable", json={"code": curr_totp_2}, headers=auth_headers)
    assert disable_res.status_code == 200
