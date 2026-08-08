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

def test_direct_messaging_privacy_enforcement(client):
    headers_user1, user1_id = create_and_login_user(client, "msg_user1", "msg_user1@test.com")
    headers_user2, user2_id = create_and_login_user(client, "msg_user2", "msg_user2@test.com")

    # 1. Check default DM privacy is 'friends'
    p1 = client.get("/api/users/profile/msg_user1", headers=headers_user1).json()
    assert p1["profile"]["dm_privacy"] == "friends"

    # 2. Non-friend attempting to message msg_user1 should be rejected (403)
    res_rejected = client.post("/api/messages", headers=headers_user2, json={
        "recipient_username": "msg_user1",
        "content": "Hello non-friend!"
    })
    assert res_rejected.status_code == 403
    assert "only accepts direct messages from friends" in res_rejected.json()["detail"]

    # 3. Establish friendship between msg_user1 and msg_user2
    client.post(f"/api/users/friends/request/msg_user2", headers=headers_user1)
    # Find pending request ID
    freqs = client.get("/api/users/friends/list", headers=headers_user2).json()
    req_id = freqs["pending_requests"][0]["friendship_id"]
    client.post(f"/api/users/friends/respond/{req_id}?action=accept", headers=headers_user2)

    # 4. Now as accepted friends, messaging succeeds (201)
    res_success = client.post("/api/messages", headers=headers_user2, json={
        "recipient_username": "msg_user1",
        "content": "Hello friend!"
    })
    assert res_success.status_code == 201
    assert res_success.json()["content"] == "Hello friend!"

    # 5. User1 updates DM privacy setting to 'none'
    client.put("/api/users/profile/me", headers=headers_user1, json={"dm_privacy": "none"})

    # Messaging user1 is now blocked even for friends (403)
    res_disabled = client.post("/api/messages", headers=headers_user2, json={
        "recipient_username": "msg_user1",
        "content": "Are you there?"
    })
    assert res_disabled.status_code == 403
    assert "disabled direct messaging" in res_disabled.json()["detail"]

    # 6. User1 updates DM privacy setting to 'anyone'
    client.put("/api/users/profile/me", headers=headers_user1, json={"dm_privacy": "anyone"})

    headers_user3, _ = create_and_login_user(client, "msg_user3", "msg_user3@test.com")
    res_anyone = client.post("/api/messages", headers=headers_user3, json={
        "recipient_username": "msg_user1",
        "content": "Message from stranger"
    })
    assert res_anyone.status_code == 201


def test_in_conversation_message_search(client):
    headers_u1, u1_id = create_and_login_user(client, "search_u1", "search_u1@test.com")
    headers_u2, u2_id = create_and_login_user(client, "search_u2", "search_u2@test.com")

    # Set both users DM privacy to anyone
    client.put("/api/users/profile/me", headers=headers_u1, json={"dm_privacy": "anyone"})
    client.put("/api/users/profile/me", headers=headers_u2, json={"dm_privacy": "anyone"})

    # Send several messages
    client.post("/api/messages", headers=headers_u1, json={"recipient_username": "search_u2", "content": "Pineapple pizza debate"})
    client.post("/api/messages", headers=headers_u1, json={"recipient_username": "search_u2", "content": "What about apple pie?"})
    client.post("/api/messages", headers=headers_u2, json={"recipient_username": "search_u1", "content": "I prefer chocolate cake"})

    # Fetch full conversation history
    full_conv = client.get(f"/api/messages/conversations/{u2_id}", headers=headers_u1).json()
    assert len(full_conv["messages"]) == 3

    # Search for 'apple' in conversation thread
    search_res = client.get(f"/api/messages/conversations/{u2_id}?q=apple", headers=headers_u1).json()
    assert len(search_res["messages"]) == 2  # Matches 'Pineapple' and 'apple pie'
    assert any("Pineapple" in m["content"] for m in search_res["messages"])
    assert any("apple pie" in m["content"] for m in search_res["messages"])

    # Search for 'chocolate'
    choc_res = client.get(f"/api/messages/conversations/{u2_id}?q=chocolate", headers=headers_u1).json()
    assert len(choc_res["messages"]) == 1
    assert choc_res["messages"][0]["content"] == "I prefer chocolate cake"


def test_friend_request_by_email_or_username(client):
    headers_req, _ = create_and_login_user(client, "friend_req_user", "friend_req_user@test.com")
    headers_target, _ = create_and_login_user(client, "friend_target_user", "friend_target_user@test.com")

    # 1. Send request using target email
    res_email = client.post("/api/users/friends/request/friend_target_user@test.com", headers=headers_req)
    assert res_email.status_code == 200
    assert "Friend request sent to @friend_target_user" in res_email.json()["message"]

    # Verify pending request on target user side
    freqs = client.get("/api/users/friends/list", headers=headers_target).json()
    assert len(freqs["pending_requests"]) == 1
    assert freqs["pending_requests"][0]["username"] == "friend_req_user"

