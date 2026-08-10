import os
import time
import base64
import pytest
from app.security_utils import generate_captcha_challenge, verify_captcha_token

def test_captcha_generation_and_verification():
    captcha_id, captcha_image = generate_captcha_challenge(expires_in=60)
    assert captcha_id is not None
    assert captcha_image.startswith("data:image/png;base64,")

    # Decode answer from generated challenge for testing
    decoded = base64.urlsafe_b64decode(captcha_id.encode()).decode()
    parts = decoded.split(":")
    assert len(parts) == 3

    # Test invalid answer
    is_valid, msg = verify_captcha_token(captcha_id, "WRONG")
    assert not is_valid
    assert msg == "Incorrect CAPTCHA solution"

    # Test missing answer
    is_valid, msg = verify_captcha_token(captcha_id, "")
    assert not is_valid

def test_captcha_expiration():
    # Expired token (expires_in = -10)
    captcha_id, _ = generate_captcha_challenge(expires_in=-10)
    is_valid, msg = verify_captcha_token(captcha_id, "ANYTHING")
    assert not is_valid
    assert "expired" in msg.lower()

def test_captcha_register_endpoint(client, monkeypatch):
    monkeypatch.setenv("DISABLE_CAPTCHA", "0")

    # Fetch fresh captcha from API
    res = client.get("/api/auth/captcha")
    assert res.status_code == 200
    data = res.json()
    assert "captcha_id" in data
    assert "captcha_image" in data
    captcha_id = data["captcha_id"]

    # Register attempt with invalid captcha answer
    res = client.post("/api/auth/register", json={
        "username": "captchatestuser",
        "email": "captcha_test@example.com",
        "password": "Password123!",
        "password_confirm": "Password123!",
        "captcha_id": captcha_id,
        "captcha_answer": "wrongcode"
    })
    assert res.status_code == 400
    assert "Incorrect" in res.json().get("detail", "")
