import pytest

def create_and_login_user(client, username, email, password="Password123!"):
    r = client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    token = r.json()["token"]
    client.get(f"/api/auth/confirm?token={token}")
    login = client.post("/api/auth/login", json={
        "username_or_email": username,
        "password": password
    })
    access_token = login.json()["access_token"]
    user_id = login.json()["user_id"]
    return {"Authorization": f"Bearer {access_token}"}, user_id

def test_notification_settings_and_polling(client):
    h1, u1_id = create_and_login_user(client, "n_user1", "n_user1@example.com")
    h2, u2_id = create_and_login_user(client, "n_user2", "n_user2@example.com")

    # Set dm_privacy to 'anyone' for easy testing
    client.put("/api/users/profile/me", headers=h1, json={"dm_privacy": "anyone"})

    # Check default notification settings
    res_me = client.get("/api/users/profile/n_user1", headers=h1)
    assert res_me.status_code == 200
    p1 = res_me.json()["profile"]
    assert p1["notify_messages"] is True
    assert p1["notify_comments"] is True
    assert p1["notification_mode"] == "constant"
    assert p1["obscure_notification_content"] is False

    # Update notification settings to limited mode, disable comments, and obscure content
    res_update = client.put(
        "/api/users/profile/me",
        json={
            "notify_messages": True,
            "notify_comments": False,
            "notification_mode": "limited",
            "obscure_notification_content": True
        },
        headers=h1
    )
    assert res_update.status_code == 200

    res_me2 = client.get("/api/users/profile/n_user1", headers=h1)
    p2 = res_me2.json()["profile"]
    assert p2["notify_messages"] is True
    assert p2["notify_comments"] is False
    assert p2["notification_mode"] == "limited"
    assert p2["obscure_notification_content"] is True

    # User 1 creates a post
    p_res = client.post("/api/posts", data={"content": "Post by user 1"}, headers=h1)
    assert p_res.status_code == 201
    post_id = p_res.json()["post_id"]

    # User 2 comments on User 1's post
    c_res = client.post(f"/api/posts/{post_id}/comments", json={"content": "Great post user 1!"}, headers=h2)
    assert c_res.status_code == 200

    # User 2 sends direct message to User 1
    res_msg = client.post(
        "/api/messages",
        json={"recipient_username": "n_user1", "content": "Hello user 1!"},
        headers=h2
    )
    assert res_msg.status_code == 201

    # Poll notifications for User 1
    res_poll = client.get("/api/notifications/poll", headers=h1)
    assert res_poll.status_code == 200
    data = res_poll.json()
    assert data["notify_messages"] is True
    assert data["notify_comments"] is False
    assert data["notification_mode"] == "limited"
    assert data["obscure_notification_content"] is True
    assert len(data["messages"]) == 1
    assert data["messages"][0]["content"] == "Hello user 1!"
    # Since notify_comments is False, comments array should be empty
    assert len(data["comments"]) == 0

    # Now enable notify_comments for User 1 and poll again
    client.put("/api/users/profile/me", headers=h1, json={"notify_comments": True})
    res_poll2 = client.get("/api/notifications/poll", headers=h1)
    data2 = res_poll2.json()
    assert data2["notify_comments"] is True
    assert len(data2["comments"]) == 1
    assert data2["comments"][0]["content"] == "Great post user 1!"

def test_avatar_upload_image_scaling(client):
    import io, os
    from PIL import Image

    h1, u1_id = create_and_login_user(client, "avatar_user", "avatar_user@example.com")

    # Create large image (1600x1200)
    large_img = Image.new("RGB", (1600, 1200), color="blue")
    img_byte_arr = io.BytesIO()
    large_img.save(img_byte_arr, format="JPEG")
    img_byte_arr.seek(0)

    # Upload avatar
    response = client.post(
        "/api/users/profile/avatar",
        headers=h1,
        files={"file": ("large_avatar.jpg", img_byte_arr, "image/jpeg")}
    )
    assert response.status_code == 200
    avatar_url = response.json()["avatar_url"]
    assert avatar_url.startswith("/uploads/")

    # Locate uploaded file on disk and verify dimensions
    filename = avatar_url.replace("/uploads/", "")
    upload_dir = os.environ.get("UPLOAD_DIR", "./uploads")
    uploaded_file_path = os.path.join(upload_dir, filename)
    assert os.path.exists(uploaded_file_path)

    saved_img = Image.open(uploaded_file_path)
    assert saved_img.width <= 512
    assert saved_img.height <= 512
    # Check aspect ratio maintained (1600x1200 -> 512x384)
    assert saved_img.width == 512
    assert saved_img.height == 384

def test_email_batch_digest_notifications(client):
    h1, u1_id = create_and_login_user(client, "e_user1", "e_user1@example.com")
    h2, u2_id = create_and_login_user(client, "e_user2", "e_user2@example.com")

    # Set dm_privacy to 'anyone'
    client.put("/api/users/profile/me", headers=h1, json={"dm_privacy": "anyone"})

    # Check default email notification settings
    p1 = client.get("/api/users/profile/e_user1", headers=h1).json()["profile"]
    assert p1["email_notify_messages"] is True
    assert p1["email_notify_comments"] is True
    assert p1["email_notification_frequency"] == "30min"

    # User 1 updates email notification frequency to 'daily'
    up_res = client.put(
        "/api/users/profile/me",
        headers=h1,
        json={
            "email_notify_messages": True,
            "email_notify_comments": True,
            "email_notification_frequency": "daily"
        }
    )
    assert up_res.status_code == 200

    p2 = client.get("/api/users/profile/e_user1", headers=h1).json()["profile"]
    assert p2["email_notification_frequency"] == "daily"

    # User 2 sends direct message to User 1
    msg_res = client.post("/api/messages", headers=h2, json={"recipient_username": "e_user1", "content": "Batch digest test message"})
    assert msg_res.status_code == 201

    # Trigger email digest process endpoint with force=true
    digest_res = client.post("/api/notifications/send-email-digest?force=true", headers=h1)
    assert digest_res.status_code == 200
    # Digest processor processed the notification successfully
    assert "Processed email notification digests" in digest_res.json()["message"]


def test_user_timezone_preference(client):
    h, u_id = create_and_login_user(client, "tz_user", "tz_user@example.com")
    
    # Check default timezone
    p = client.get("/api/users/profile/tz_user", headers=h).json()["profile"]
    assert p["timezone"] == "UTC"

    # Update timezone to America/New_York
    up_res = client.put(
        "/api/users/profile/me",
        headers=h,
        json={"timezone": "America/New_York"}
    )
    assert up_res.status_code == 200

    p_updated = client.get("/api/users/profile/tz_user", headers=h).json()["profile"]
    assert p_updated["timezone"] == "America/New_York"


def test_email_privacy_and_posts_settings(client):
    h, u_id = create_and_login_user(client, "emp_user", "emp_user@example.com")

    # Check default email settings
    p = client.get("/api/users/profile/emp_user", headers=h).json()["profile"]
    assert p["email_notify_posts"] is True
    assert p["email_obscure_notification_content"] is False

    # Update email settings
    up_res = client.put(
        "/api/users/profile/me",
        headers=h,
        json={
            "email_notify_posts": False,
            "email_obscure_notification_content": True
        }
    )
    assert up_res.status_code == 200

    p_updated = client.get("/api/users/profile/emp_user", headers=h).json()["profile"]
    assert p_updated["email_notify_posts"] is False
    assert p_updated["email_obscure_notification_content"] is True



