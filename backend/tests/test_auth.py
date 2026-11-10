from fastapi import status

def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "ok"

def test_dev_login(client):
    res = client.post(
        "/api/auth/dev-login",
        json={"email": "tester@test.com", "fullName": "Tester Human"}
    )
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "token" in data
    assert data["user"]["email"] == "tester@test.com"

def test_me_endpoint_authorized(client, auth_headers, test_user):
    res = client.get("/api/auth/me", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["id"] == test_user.id
    assert data["email"] == test_user.email

def test_invalid_token_rejected(client):
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer fake_invalid_jwt_token"})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
