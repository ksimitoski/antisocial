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


def test_friend_follow_and_post_notifications(client):
    h1, u1_id = create_and_login_user(client, "flw_user1", "flw_user1@example.com")
    h2, u2_id = create_and_login_user(client, "flw_user2", "flw_user2@example.com")

    # Attempt to follow before being friends -> 400 Error
    res_follow_nofriend = client.post("/api/users/flw_user2/follow", headers=h1)
    assert res_follow_nofriend.status_code == 400
    assert "friends with" in res_follow_nofriend.json()["detail"]

    # Send and accept friend request
    res_req = client.post("/api/users/friends/request/flw_user2", headers=h1)
    assert res_req.status_code == 200

    # Get friendship id from flw_user2 profile
    res_p2 = client.get("/api/users/profile/flw_user2", headers=h1)
    fs_id = res_p2.json()["friendship_status"]["id"]

    res_acc = client.post(f"/api/users/friends/respond/{fs_id}?action=accept", headers=h2)
    assert res_acc.status_code == 200

    # Check profile - friends accepted, but not following yet
    res_p2_after = client.get("/api/users/profile/flw_user2", headers=h1)
    assert res_p2_after.json()["friendship_status"]["status"] == "accepted"
    assert res_p2_after.json()["is_following"] is False

    # Toggle follow on flw_user2 -> should become True
    res_flw1 = client.post("/api/users/flw_user2/follow", headers=h1)
    assert res_flw1.status_code == 200
    assert res_flw1.json()["is_following"] is True

    res_p2_flw = client.get("/api/users/profile/flw_user2", headers=h1)
    assert res_p2_flw.json()["is_following"] is True

    # User 2 creates a post
    post_res1 = client.post("/api/posts", data={"content": "Exciting update from User 2!"}, headers=h2)
    assert post_res1.status_code == 201
    post1_id = post_res1.json()["post_id"]

    # User 1 polls notifications -> should receive notification about User 2's post
    poll_res1 = client.get("/api/notifications/poll", headers=h1)
    assert poll_res1.status_code == 200
    data1 = poll_res1.json()
    assert "posts" in data1
    assert len(data1["posts"]) == 1
    assert data1["posts"][0]["id"] == post1_id
    assert data1["posts"][0]["author_username"] == "flw_user2"
    assert data1["posts"][0]["content"] == "Exciting update from User 2!"

    # Test email digest notification generation for User 1
    res_email = client.post("/api/notifications/send-email-digest?force=true", headers=h1)
    assert res_email.status_code == 200
    assert res_email.json()["emails_sent"] >= 1

    # Server time from first poll for delta checking
    server_time = data1["server_time"]

    # Toggle follow on flw_user2 -> should unfollow (become False)
    res_flw2 = client.post("/api/users/flw_user2/follow", headers=h1)
    assert res_flw2.status_code == 200
    assert res_flw2.json()["is_following"] is False

    # User 2 creates a second post
    post_res2 = client.post("/api/posts", data={"content": "Second post from User 2!"}, headers=h2)
    assert post_res2.status_code == 201

    # User 1 polls notifications since last server_time -> should NOT receive notification for the new post
    poll_res2 = client.get(f"/api/notifications/poll?since={server_time}", headers=h1)
    assert poll_res2.status_code == 200
    data2 = poll_res2.json()
    assert len(data2["posts"]) == 0

