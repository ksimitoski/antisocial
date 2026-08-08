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

def test_comments_sorting_and_creation(client):
    headers_user1, _ = create_and_login_user(client, "user1", "user1@test.com")
    headers_user2, _ = create_and_login_user(client, "user2", "user2@test.com")

    # 1. User 1 creates a public post
    post_res = client.post("/api/posts", headers=headers_user1, data={
        "content": "Public post for testing comments",
        "visibility": "public"
    })
    assert post_res.status_code == 201
    post_id = post_res.json()["post_id"]

    # 2. Add multiple comments to the post
    c1_res = client.post(f"/api/posts/{post_id}/comments", headers=headers_user1, json={"content": "First comment"})
    assert c1_res.status_code == 200
    c1_id = c1_res.json()["id"]

    c2_res = client.post(f"/api/posts/{post_id}/comments", headers=headers_user2, json={"content": "Second comment"})
    assert c2_res.status_code == 200
    c2_id = c2_res.json()["id"]

    c3_res = client.post(f"/api/posts/{post_id}/comments", headers=headers_user1, json={"content": "Third comment (latest)"})
    assert c3_res.status_code == 200
    c3_id = c3_res.json()["id"]

    # 3. Retrieve public posts via endpoint
    feed = client.get("/api/posts", headers=headers_user2).json()
    target_post = next(p for p in feed if p["id"] == post_id)
    
    assert len(target_post["comments"]) == 3
    # Verify latest-first comment sorting
    assert target_post["comments"][0]["id"] == c3_id
    assert target_post["comments"][0]["content"] == "Third comment (latest)"
    assert target_post["comments"][1]["id"] == c2_id
    assert target_post["comments"][2]["id"] == c1_id

def test_comment_deletion_permissions(client):
    headers_author, _ = create_and_login_user(client, "author", "author@test.com")
    headers_commenter, _ = create_and_login_user(client, "commenter", "commenter@test.com")
    headers_other, _ = create_and_login_user(client, "other", "other@test.com")

    post_res = client.post("/api/posts", headers=headers_author, data={
        "content": "Author post",
        "visibility": "public"
    })
    post_id = post_res.json()["post_id"]

    c_res = client.post(f"/api/posts/{post_id}/comments", headers=headers_commenter, json={"content": "Comment to delete"})
    comment_id = c_res.json()["id"]

    # Other non-author, non-mod user should be forbidden (403) from deleting
    del_forbidden = client.delete(f"/api/posts/{post_id}/comments/{comment_id}", headers=headers_other)
    assert del_forbidden.status_code == 403

    # Comment author can delete their comment
    del_success = client.delete(f"/api/posts/{post_id}/comments/{comment_id}", headers=headers_commenter)
    assert del_success.status_code == 200

    # Verify comment was removed
    feed = client.get("/api/posts", headers=headers_author).json()
    target_post = next(p for p in feed if p["id"] == post_id)
    assert len(target_post["comments"]) == 0


def test_post_privacy_update_permissions(client):
    headers_author, _ = create_and_login_user(client, "priv_author", "priv_author@test.com")
    headers_other, _ = create_and_login_user(client, "priv_other", "priv_other@test.com")

    # 1. Author creates a public post
    p_res = client.post("/api/posts", headers=headers_author, data={
        "content": "Post with privacy changes",
        "visibility": "public"
    })
    post_id = p_res.json()["post_id"]

    # 2. Non-author attempts to change privacy -> 403 Forbidden
    other_update = client.put(f"/api/posts/{post_id}/privacy", headers=headers_other, json={
        "visibility": "private"
    })
    assert other_update.status_code == 403

    # 3. Post author changes privacy to 'private' -> 200 OK
    author_update = client.put(f"/api/posts/{post_id}/privacy", headers=headers_author, json={
        "visibility": "private"
    })
    assert author_update.status_code == 200
    assert author_update.json()["visibility"] == "private"

    # 3b. Post author changes privacy to 'internal-only' -> 200 OK
    internal_update = client.put(f"/api/posts/{post_id}/privacy", headers=headers_author, json={
        "visibility": "internal-only"
    })
    assert internal_update.status_code == 200
    assert internal_update.json()["visibility"] == "internal-only"

    # Revert to private for step 4
    client.put(f"/api/posts/{post_id}/privacy", headers=headers_author, json={"visibility": "private"})

    # 4. Outsider should no longer see private post in feed
    feed_other = client.get("/api/posts", headers=headers_other).json()
    assert not any(p["id"] == post_id for p in feed_other)

    # 5. Author can see their private post
    feed_author = client.get("/api/posts", headers=headers_author).json()
    assert any(p["id"] == post_id for p in feed_author)


def test_protected_media_file_privacy(client):
    import io
    headers_author, _ = create_and_login_user(client, "media_author", "media_author@test.com")
    headers_other, _ = create_and_login_user(client, "media_other", "media_other@test.com")

    # 1. Author creates a private post with an image attachment
    fake_image = ("secret.png", io.BytesIO(b"fake image bytes"), "image/png")
    p_res = client.post("/api/posts", headers=headers_author, data={
        "content": "Secret image post",
        "visibility": "private"
    }, files={"file": fake_image})

    assert p_res.status_code == 201
    media_url = p_res.json()["media_url"]
    filename = media_url.replace("/uploads/", "")

    # 2. Unauthenticated request to /uploads/<filename> -> 403 Forbidden
    unauth_get = client.get(f"/uploads/{filename}")
    assert unauth_get.status_code == 403

    # 3. Non-author request to /uploads/<filename> -> 403 Forbidden
    other_get = client.get(f"/uploads/{filename}", headers=headers_other)
    assert other_get.status_code == 403

    # 4. Author request to /uploads/<filename> -> 200 OK
    author_get = client.get(f"/uploads/{filename}", headers=headers_author)
    assert author_get.status_code == 200
    assert author_get.content == b"fake image bytes"


def test_post_editing_author_only(client):
    headers_author, _ = create_and_login_user(client, "edit_author", "edit_author@test.com")
    headers_other, _ = create_and_login_user(client, "edit_other", "edit_other@test.com")

    # 1. Author creates a post
    p_res = client.post("/api/posts", headers=headers_author, data={
        "content": "Original Post Content",
        "visibility": "public"
    })
    post_id = p_res.json()["post_id"]

    # 2. Non-author attempts to edit -> 403 Forbidden
    other_edit = client.put(f"/api/posts/{post_id}", headers=headers_other, json={
        "content": "Hacked content!"
    })
    assert other_edit.status_code == 403
    assert "Only the user who created this post can edit it" in other_edit.json()["detail"]

    # 3. Post author edits post -> 200 OK
    author_edit = client.put(f"/api/posts/{post_id}", headers=headers_author, json={
        "content": "Updated Post Content"
    })
    assert author_edit.status_code == 200
    assert author_edit.json()["content"] == "Updated Post Content"

    # Verify updated content in feed
    feed_res = client.get("/api/posts", headers=headers_author).json()
    edited_post = next(p for p in feed_res if p["id"] == post_id)
    assert edited_post["content"] == "Updated Post Content"


def test_video_upload_disallowed(client):
    import io
    headers_author, _ = create_and_login_user(client, "video_user", "video_user@test.com")

    fake_video = ("sample.mp4", io.BytesIO(b"fake video content"), "video/mp4")
    p_res = client.post("/api/posts", headers=headers_author, data={
        "content": "Video post attempt",
        "visibility": "public"
    }, files={"file": fake_video})

    assert p_res.status_code == 400
    assert "Only image attachments are accepted" in p_res.json()["detail"]


def test_get_single_post(client):
    h_author, _ = create_and_login_user(client, "single_p_author", "single_author@test.com")
    h_viewer, _ = create_and_login_user(client, "single_p_viewer", "single_viewer@test.com")

    # Create public post
    res = client.post("/api/posts", headers=h_author, data={
        "content": "Single post content link test",
        "visibility": "public"
    })
    assert res.status_code == 201
    post_id = res.json()["post_id"]

    # Retrieve single post
    get_res = client.get(f"/api/posts/{post_id}", headers=h_viewer)
    assert get_res.status_code == 200
    post_data = get_res.json()
    assert post_data["id"] == post_id
    assert post_data["content"] == "Single post content link test"
    assert post_data["author_username"] == "single_p_author"

    # Create private post
    priv_res = client.post("/api/posts", headers=h_author, data={
        "content": "Private single post content",
        "visibility": "private"
    })
    priv_post_id = priv_res.json()["post_id"]

    # Viewer should be forbidden (403) from accessing private single post
    forbidden_res = client.get(f"/api/posts/{priv_post_id}", headers=h_viewer)
    assert forbidden_res.status_code == 403

    # Non-existent post returns 404
    not_found_res = client.get("/api/posts/999999", headers=h_viewer)
    assert not_found_res.status_code == 404



