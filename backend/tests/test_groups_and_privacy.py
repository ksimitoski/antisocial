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

def test_group_creation_and_post_visibility(client):
    headers_creator, _ = create_and_login_user(client, "gcreator", "gcreator@test.com")
    headers_outsider, _ = create_and_login_user(client, "goutsider", "goutsider@test.com")

    # 1. Create a group
    g_res = client.post("/api/groups", headers=headers_creator, json={
        "name": "Secret Coding Club",
        "description": "Exclusive developer group",
        "is_private": True
    })
    assert g_res.status_code == 201
    group_id = g_res.json()["id"]

    # 2. Group creator posts inside the group
    post_res = client.post("/api/posts", headers=headers_creator, data={
        "content": "Secret group discussion",
        "group_id": group_id,
        "visibility": "group"
    })
    assert post_res.status_code == 201
    post_id = post_res.json()["post_id"]

    # 3. Creator can post a comment inside group post
    c_res = client.post(f"/api/posts/{post_id}/comments", headers=headers_creator, json={
        "content": "First group comment"
    })
    assert c_res.status_code == 200

    # 4. Outsider who is not in group shouldn't see group posts in general feed
    outsider_feed = client.get("/api/posts", headers=headers_outsider).json()
    assert not any(p["id"] == post_id for p in outsider_feed)


def test_group_admin_management_and_bans(client):
    headers_creator, creator_id = create_and_login_user(client, "gadmin", "gadmin@test.com")
    headers_user, user_id = create_and_login_user(client, "applicant", "applicant@test.com")

    # 1. Create a private group
    g_res = client.post("/api/groups", headers=headers_creator, json={
        "name": "Admin Managed Group",
        "description": "Initial description",
        "is_private": False
    })
    group_id = g_res.json()["id"]

    # 2. Creator updates group settings to private
    update_res = client.put(f"/api/groups/{group_id}", headers=headers_creator, json={
        "name": "Updated Group Name",
        "description": "New updated description",
        "is_private": True
    })
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Updated Group Name"
    assert update_res.json()["is_private"] is True

    # Non-admin user cannot edit settings
    bad_edit = client.put(f"/api/groups/{group_id}", headers=headers_user, json={"name": "Hacked Name"})
    assert bad_edit.status_code == 403

    # 3. Creator invites applicant to invite-only group
    invite_res = client.post(f"/api/groups/{group_id}/invite", headers=headers_creator, json={"username": "applicant"})
    assert invite_res.status_code == 200

    # Verify user is now member
    details = client.get(f"/api/groups/{group_id}", headers=headers_user).json()
    assert details["is_member"] is True

    # 4. Creator removes user from group
    rem_res = client.delete(f"/api/groups/{group_id}/members/{user_id}", headers=headers_creator)
    assert rem_res.status_code == 200
    details_after_rem = client.get(f"/api/groups/{group_id}", headers=headers_user).json()
    assert details_after_rem["is_member"] is False

    # 5. Creator bans user from group
    ban_res = client.post(f"/api/groups/{group_id}/ban/{user_id}", headers=headers_creator)
    assert ban_res.status_code == 200

    # Banned user attempting to view or join is blocked
    get_banned = client.get(f"/api/groups/{group_id}", headers=headers_user)
    assert get_banned.status_code == 403

    join_banned = client.post(f"/api/groups/{group_id}/join", headers=headers_user)
    assert join_banned.status_code == 403

    # 6. Unban user
    unban_res = client.post(f"/api/groups/{group_id}/unban/{user_id}", headers=headers_creator)
    assert unban_res.status_code == 200


def test_admin_and_moderator_group_post_access(client, get_db_session):
    headers_creator, _ = create_and_login_user(client, "g_author", "g_author@test.com")
    headers_admin, admin_id = create_and_login_user(client, "g_admin", "g_admin@test.com")
    headers_regular, _ = create_and_login_user(client, "g_regular", "g_regular@test.com")

    from app import models
    db_session = get_db_session()
    u_admin = db_session.query(models.User).filter(models.User.id == admin_id).first()
    assert u_admin is not None
    u_admin.role = "admin"
    u_admin.is_admin = True
    db_session.commit()
    db_session.close()

    # 1. Creator makes private group and posts in it
    g_res = client.post("/api/groups", headers=headers_creator, json={
        "name": "Staff Oversight Group",
        "description": "Private group testing staff access",
        "is_private": True
    })
    assert g_res.status_code == 201
    group_id = g_res.json()["id"]

    post_res = client.post("/api/posts", headers=headers_creator, data={
        "content": "Secret post inside private group",
        "group_id": group_id,
        "visibility": "group"
    })
    assert post_res.status_code == 201
    post_id = post_res.json()["post_id"]

    # 2. Regular non-member user is blocked
    reg_feed = client.get(f"/api/posts?group_id={group_id}", headers=headers_regular)
    assert reg_feed.status_code == 200
    assert len(reg_feed.json()) == 0

    reg_single = client.get(f"/api/posts/{post_id}", headers=headers_regular)
    assert reg_single.status_code == 403

    # 3. System Admin / Moderator (g_admin) CAN view group posts without joining
    admin_feed = client.get(f"/api/posts?group_id={group_id}", headers=headers_admin)
    assert admin_feed.status_code == 200
    assert len(admin_feed.json()) == 1
    assert admin_feed.json()[0]["id"] == post_id

    admin_single = client.get(f"/api/posts/{post_id}", headers=headers_admin)
    assert admin_single.status_code == 200
    assert admin_single.json()["content"] == "Secret post inside private group"
