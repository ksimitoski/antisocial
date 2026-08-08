from app import models
from app.main import init_system_admin

def test_initial_admin_and_deletion_protection(client, get_db_session):
    # 1. System admin should be auto-created by init_system_admin()
    db = get_db_session()
    admin_user = db.query(models.User).filter(models.User.is_system_admin == True).first()
    assert admin_user is not None
    assert admin_user.username == "admin"
    assert admin_user.is_admin is True
    assert admin_user.is_system_admin is True
    db.close()

    # Calling init_system_admin again should NOT create duplicate admin or error out
    init_system_admin()

    # 2. Register Alice (regular user) and make Alice admin via system admin
    r1 = client.post("/api/auth/register", json={
        "username": "alice",
        "email": "alice@test.com",
        "password": "Password123!"
    })
    assert r1.status_code == 201
    confirm_token_alice = r1.json()["token"]
    client.get(f"/api/auth/confirm?token={confirm_token_alice}")

    # Login Alice
    login_alice = client.post("/api/auth/login", json={
        "username_or_email": "alice",
        "password": "Password123!"
    })
    assert login_alice.status_code == 200
    token_alice = login_alice.json()["access_token"]
    headers_alice = {"Authorization": f"Bearer {token_alice}"}

    # Elevate Alice to admin in DB for testing admin operations
    db = get_db_session()
    alice_db = db.query(models.User).filter(models.User.username == "alice").first()
    alice_db.is_admin = True
    db.commit()
    db.close()

    # 3. Attempting to delete the system admin by another admin MUST be blocked (HTTP 400)
    del_admin_attempt = client.delete(f"/api/admin/users/{admin_user.id}", headers=headers_alice)
    assert del_admin_attempt.status_code == 400
    assert "initial system administrator" in del_admin_attempt.json()["detail"]

    # 4. Register Bob (regular user)
    r2 = client.post("/api/auth/register", json={
        "username": "bob",
        "email": "bob@test.com",
        "password": "Password123!"
    })
    assert r2.status_code == 201
    confirm_token_bob = r2.json()["token"]
    client.get(f"/api/auth/confirm?token={confirm_token_bob}")

    login_bob = client.post("/api/auth/login", json={
        "username_or_email": "bob",
        "password": "Password123!"
    })
    assert login_bob.status_code == 200
    token_bob = login_bob.json()["access_token"]
    headers_bob = {"Authorization": f"Bearer {token_bob}"}

    # 5. Bob changes password
    pwd_res = client.post("/api/users/change-password", headers=headers_bob, json={
        "current_password": "Password123!",
        "new_password": "NewSecretPassword456!"
    })
    assert pwd_res.status_code == 200

    # Bob logs in with new password
    login_bob_new = client.post("/api/auth/login", json={
        "username_or_email": "bob",
        "password": "NewSecretPassword456!"
    })
    assert login_bob_new.status_code == 200

    # 6. Bob sets per-field privacy and publishes posts
    client.put("/api/users/profile/me", headers=headers_bob, json={
        "bio": "Bob's bio",
        "bio_visibility": "public",
        "birthdate": "1995-05-15",
        "birthdate_visibility": "private"
    })

    client.post("/api/posts", headers=headers_bob, data={"content": "Bob public post", "visibility": "public"})
    client.post("/api/posts", headers=headers_bob, data={"content": "Bob private post", "visibility": "private"})

    # Alice views Bob's profile -> birthdate should be hidden (privacy check)
    p_view = client.get("/api/users/profile/bob", headers=headers_alice).json()
    assert p_view["profile"]["birthdate"] is None

    # Account deletion with invalid password fails
    del_bad = client.request("DELETE", "/api/users/me", headers=headers_bob, json={"password": "wrongpassword"})
    assert del_bad.status_code == 400
    assert "Incorrect password" in del_bad.json()["detail"]

    # 6. Immediate Cascade Account Deletion Test for Bob with valid password
    del_bob = client.request("DELETE", "/api/users/me", headers=headers_bob, json={"password": "NewSecretPassword456!"})
    assert del_bob.status_code == 200

    feed_after = client.get("/api/posts", headers=headers_alice).json()
    assert len(feed_after) == 0


def test_email_update_and_privacy(client):
    # Register User 1
    r1 = client.post("/api/auth/register", json={
        "username": "email_u1",
        "email": "email_u1@test.com",
        "password": "Password123!"
    })
    token1 = r1.json()["token"]
    client.get(f"/api/auth/confirm?token={token1}")
    l1 = client.post("/api/auth/login", json={"username_or_email": "email_u1", "password": "Password123!"})
    headers1 = {"Authorization": f"Bearer {l1.json()['access_token']}"}

    # Register User 2
    r2 = client.post("/api/auth/register", json={
        "username": "email_u2",
        "email": "email_u2@test.com",
        "password": "Password123!"
    })
    token2 = r2.json()["token"]
    client.get(f"/api/auth/confirm?token={token2}")
    l2 = client.post("/api/auth/login", json={"username_or_email": "email_u2", "password": "Password123!"})
    headers2 = {"Authorization": f"Bearer {l2.json()['access_token']}"}

    # 1. Default email privacy for email_u1 is 'private'
    p1_own = client.get("/api/users/profile/email_u1", headers=headers1).json()
    assert p1_own["profile"]["email"] == "email_u1@test.com"
    assert p1_own["profile"]["email_visibility"] == "private"

    # Viewer email_u2 looking at email_u1 should NOT see email (None)
    p1_viewer = client.get("/api/users/profile/email_u1", headers=headers2).json()
    assert p1_viewer["profile"]["email"] is None

    # 2. Update email to an existing email (email_u2@test.com) should fail with 400
    dup_res = client.put("/api/users/profile/me", headers=headers1, json={"email": "email_u2@test.com"})
    assert dup_res.status_code == 400
    assert "already in use" in dup_res.json()["detail"]

    # 3. Update email to new valid email
    update_res = client.put("/api/users/profile/me", headers=headers1, json={
        "email": "new_email_u1@test.com",
        "email_visibility": "public"
    })
    assert update_res.status_code == 200

    # Owner checks profile
    p1_updated_own = client.get("/api/users/profile/email_u1", headers=headers1).json()
    assert p1_updated_own["profile"]["email"] == "new_email_u1@test.com"
    assert p1_updated_own["profile"]["email_visibility"] == "public"

    # Viewer email_u2 can now see updated public email
    p1_updated_viewer = client.get("/api/users/profile/email_u1", headers=headers2).json()
    assert p1_updated_viewer["profile"]["email"] == "new_email_u1@test.com"

