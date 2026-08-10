import pytest
from app.schemas import UserRegister

def test_username_valid_cases():
    valid_usernames = [
        "a",
        "valid_username",
        "a123_456",
        "A_User_1",
        "a" * 40,
    ]
    for un in valid_usernames:
        user = UserRegister(
            username=un,
            email="test@example.com",
            password="Password123!"
        )
        assert user.username == un.lower().strip()

def test_username_invalid_cases():
    invalid_usernames = [
        "a" * 41,        # Over 40 chars
        "1user",         # Starts with digit
        "_user",         # Starts with underscore
        "user-name",     # Hyphen
        "user.name",     # Dot
        "user@name",     # At sign
        "user name",     # Space inside
        "",              # Empty
        "   ",           # Whitespace
    ]
    for un in invalid_usernames:
        with pytest.raises(Exception):
            UserRegister(
                username=un,
                email="test@example.com",
                password="Password123!"
            )

def test_register_api_username_validation(client):
    # Test registered with invalid starting char
    res = client.post("/api/auth/register", json={
        "username": "123user",
        "email": "invalid_start@example.com",
        "password": "Password123!",
        "password_confirm": "Password123!"
    })
    assert res.status_code == 422

    # Test registered with invalid char
    res = client.post("/api/auth/register", json={
        "username": "user-name",
        "email": "invalid_char@example.com",
        "password": "Password123!",
        "password_confirm": "Password123!"
    })
    assert res.status_code == 422

    # Test registered with username over 40 chars
    res = client.post("/api/auth/register", json={
        "username": "a" * 41,
        "email": "too_long@example.com",
        "password": "Password123!",
        "password_confirm": "Password123!"
    })
    assert res.status_code == 422

    # Test registered with valid username of 40 chars starting with letter
    valid_40 = "a" + "b" * 39
    res = client.post("/api/auth/register", json={
        "username": valid_40,
        "email": "valid_40@example.com",
        "password": "Password123!",
        "password_confirm": "Password123!"
    })
    assert res.status_code == 201
