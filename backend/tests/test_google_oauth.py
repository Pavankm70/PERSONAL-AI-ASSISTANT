import pytest
import jwt
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock
from fastapi import status

from app.core.config import settings
from app.db.models import User, OAuthAccount, IntegrationConnection
from app.services.google_oauth.crypto import token_cipher
from app.services.google_oauth.oauth_service import (
    create_oauth_state,
    verify_oauth_state,
    create_auth_ticket,
    consume_auth_ticket,
    get_valid_user_credentials
)

# 1. State Token Generation & Verification
def test_oauth_state_creation_and_validation():
    state = create_oauth_state(purpose="login", scope_category="identity")
    decoded = verify_oauth_state(state, consume=False)
    assert decoded["purpose"] == "login"
    assert decoded["scope_category"] == "identity"
    assert "nonce" in decoded

def test_oauth_state_tampered_rejected():
    state = create_oauth_state(purpose="login", scope_category="identity")
    tampered_state = state[:-5] + "ABCDE"
    with pytest.raises(Exception):
        verify_oauth_state(tampered_state)

def test_oauth_state_expired_rejected():
    expired_payload = {
        "purpose": "login",
        "scope_category": "identity",
        "nonce": "test_expired_nonce",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        "iat": datetime.now(timezone.utc) - timedelta(minutes=10)
    }
    expired_state = jwt.encode(expired_payload, settings.APP_SECRET_KEY, algorithm="HS256")
    with pytest.raises(Exception):
        verify_oauth_state(expired_state)

def test_oauth_state_nonce_replay_rejected():
    state = create_oauth_state(purpose="login", scope_category="identity")
    # First consumption succeeds
    decoded = verify_oauth_state(state, consume=True)
    assert decoded["purpose"] == "login"

    # Second consumption of the same state fails (replay protection when no ticket is recorded)
    with pytest.raises(Exception) as excinfo:
        verify_oauth_state(state, consume=True)
    assert "already been consumed" in str(excinfo.value)

def test_oauth_state_idempotent_retry_within_grace_window():
    from app.services.google_oauth.oauth_service import record_state_ticket
    state = create_oauth_state(purpose="login", scope_category="identity")
    decoded = verify_oauth_state(state, consume=True)
    assert decoded["purpose"] == "login"

    # Associate an issued auth ticket with the consumed state
    record_state_ticket(state, "tkt_idempotent_999")

    # Immediate second call within 15-second grace window succeeds idempotently
    retry_decoded = verify_oauth_state(state, consume=True)
    assert retry_decoded.get("_is_deduplicated") is True
    assert retry_decoded.get("_cached_ticket") == "tkt_idempotent_999"

# 2. Callback Validation & Failure Handling
def test_google_oauth_callback_missing_params(client):
    res = client.get("/api/auth/google/callback")
    assert res.status_code == status.HTTP_400_BAD_REQUEST

def test_google_oauth_callback_error_param(client):
    res = client.get("/api/auth/google/callback?error=access_denied")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "access_denied" in res.json()["detail"]

# 3. Google OAuth Login Flow (Mocked Google Endpoints)
@pytest.mark.asyncio
async def test_google_oauth_login_flow(client, db_session):
    state = create_oauth_state(purpose="login", scope_category="identity")

    mock_tokens = {
        "access_token": "ya29.mock_real_google_access_token_12345",
        "refresh_token": "1//mock_real_google_refresh_token_67890",
        "expires_in": 3600,
        "scope": "openid email profile"
    }
    mock_profile = {
        "sub": "google_sub_987654321",
        "email": "verified.student@university.edu",
        "name": "Verified Student",
        "picture": "https://lh3.googleusercontent.com/photo.jpg",
        "email_verified": True
    }

    with patch("app.api.routes.auth.exchange_code_for_tokens", new_callable=AsyncMock) as mock_exchange, \
         patch("app.api.routes.auth.get_google_user_profile", new_callable=AsyncMock) as mock_userinfo:
        
        mock_exchange.return_value = mock_tokens
        mock_userinfo.return_value = mock_profile

        res = client.get(
            f"/api/auth/google/callback?code=mock_auth_code_xyz&state={state}",
            headers={"Accept": "application/json"}
        )

        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert "token" in data
        assert data["user"]["email"] == "verified.student@university.edu"
        assert data["user"]["fullName"] == "Verified Student"

        # Verify User was persisted in DB
        user = db_session.query(User).filter(User.email == "verified.student@university.edu").first()
        assert user is not None

        # Verify OAuthAccount was persisted with encrypted tokens
        account = db_session.query(OAuthAccount).filter(
            OAuthAccount.user_id == user.id,
            OAuthAccount.provider == "google"
        ).first()
        assert account is not None
        assert account.external_user_id == "google_sub_987654321"

        # Verify tokens are encrypted at rest with AES-GCM and NEVER stored in plaintext
        assert account.encrypted_access_token != "ya29.mock_real_google_access_token_12345"
        assert account.encrypted_refresh_token != "1//mock_real_google_refresh_token_67890"

        # Verify decryption restores original tokens
        decrypted_access = token_cipher.decrypt(account.encrypted_access_token)
        decrypted_refresh = token_cipher.decrypt(account.encrypted_refresh_token)
        assert decrypted_access == "ya29.mock_real_google_access_token_12345"
        assert decrypted_refresh == "1//mock_real_google_refresh_token_67890"

# 4. Unverified Google Email Rejected
@pytest.mark.asyncio
async def test_unverified_google_email_rejected(client):
    state = create_oauth_state(purpose="login", scope_category="identity")

    mock_tokens = {
        "access_token": "ya29.unverified_access_token",
        "expires_in": 3600
    }
    mock_profile = {
        "sub": "google_sub_unverified",
        "email": "unverified@untrusted.com",
        "email_verified": False
    }

    with patch("app.api.routes.auth.exchange_code_for_tokens", new_callable=AsyncMock) as mock_exchange, \
         patch("app.api.routes.auth.get_google_user_profile", new_callable=AsyncMock) as mock_userinfo:

        mock_exchange.return_value = mock_tokens
        from fastapi import HTTPException
        mock_userinfo.side_effect = HTTPException(status_code=400, detail="Google account email is not verified by Google.")

        res = client.get(
            f"/api/auth/google/callback?code=mock_code&state={state}",
            headers={"Accept": "application/json"}
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "not verified" in res.json()["detail"]

# 5. Separate Service Linking Flow (Gmail Connect)
@pytest.mark.asyncio
async def test_google_oauth_service_linking(client, db_session, test_user):
    state = create_oauth_state(purpose="link", scope_category="gmail", user_id=test_user.id)

    mock_tokens = {
        "access_token": "ya29.gmail_specific_access_token",
        "refresh_token": "1//gmail_refresh_token",
        "expires_in": 3600,
        "scope": "https://www.googleapis.com/auth/gmail.readonly"
    }
    mock_profile = {
        "sub": "google_sub_test_user",
        "email": test_user.email,
        "name": test_user.full_name,
        "email_verified": True
    }

    with patch("app.api.routes.auth.exchange_code_for_tokens", new_callable=AsyncMock) as mock_exchange, \
         patch("app.api.routes.auth.get_google_user_profile", new_callable=AsyncMock) as mock_userinfo:

        mock_exchange.return_value = mock_tokens
        mock_userinfo.return_value = mock_profile

        res = client.get(
            f"/api/auth/google/callback?code=mock_gmail_code&state={state}",
            headers={"Accept": "application/json"}
        )

        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["success"] is True
        assert data["provider"] == "gmail"

        # Verify OAuthAccount created for test_user with provider='gmail'
        acc = db_session.query(OAuthAccount).filter(
            OAuthAccount.user_id == test_user.id,
            OAuthAccount.provider == "gmail"
        ).first()
        assert acc is not None
        assert token_cipher.decrypt(acc.encrypted_access_token) == "ya29.gmail_specific_access_token"

        # Verify IntegrationConnection updated to connected
        conn = db_session.query(IntegrationConnection).filter(
            IntegrationConnection.user_id == test_user.id,
            IntegrationConnection.provider == "gmail"
        ).first()
        assert conn is not None
        assert conn.status == "connected"

# 6. Cross-User Linking Prevention (Conflict 409)
@pytest.mark.asyncio
async def test_cross_user_account_linking_rejected(client, db_session, test_user):
    # User A has already linked Google sub 'google_sub_alice'
    account_a = OAuthAccount(
        user_id=test_user.id,
        provider="gmail",
        external_user_id="google_sub_alice",
        email=test_user.email,
        encrypted_access_token=token_cipher.encrypt("token_a")
    )
    db_session.add(account_a)
    db_session.commit()

    # User B exists
    user_b = User(id="usr_b_202", email="user_b@univ.edu", full_name="User B")
    db_session.add(user_b)
    db_session.commit()

    # User B attempts to link the exact same Google account
    state = create_oauth_state(purpose="link", scope_category="gmail", user_id="usr_b_202")

    mock_tokens = {"access_token": "token_b", "expires_in": 3600}
    mock_profile = {"sub": "google_sub_alice", "email": "user_a@gmail.com", "email_verified": True}

    with patch("app.api.routes.auth.exchange_code_for_tokens", new_callable=AsyncMock) as mock_exchange, \
         patch("app.api.routes.auth.get_google_user_profile", new_callable=AsyncMock) as mock_userinfo:

        mock_exchange.return_value = mock_tokens
        mock_userinfo.return_value = mock_profile

        res = client.get(
            f"/api/auth/google/callback?code=code_b&state={state}",
            headers={"Accept": "application/json"}
        )
        assert res.status_code == status.HTTP_409_CONFLICT
        assert "already linked to a different AURELIA user" in res.json()["detail"]

# 7. Single-Use Auth Ticket Exchange (No JWT in URL)
def test_single_use_auth_ticket_exchange(client, test_user):
    token = "test_jwt_session_value"
    ticket = create_auth_ticket(user_id=test_user.id, token=token, expires_seconds=60)

    # First exchange succeeds
    res = client.post("/api/auth/exchange-ticket", json={"ticket": ticket})
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["token"] == token
    assert data["user"]["id"] == test_user.id

    # Second exchange with the same ticket fails (single use)
    res_second = client.post("/api/auth/exchange-ticket", json={"ticket": ticket})
    assert res_second.status_code == status.HTTP_400_BAD_REQUEST

# 8. Token Auto-Refresh When Expired
@pytest.mark.asyncio
async def test_token_auto_refresh(db_session, test_user):
    expired_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    account = OAuthAccount(
        user_id=test_user.id,
        provider="calendar",
        encrypted_access_token=token_cipher.encrypt("old_expired_access_token"),
        encrypted_refresh_token=token_cipher.encrypt("valid_refresh_token_123"),
        token_expires_at=expired_time
    )
    db_session.add(account)
    db_session.commit()

    mock_refresh_res = {
        "access_token": "newly_refreshed_access_token_999",
        "expires_in": 3600
    }

    with patch("app.services.google_oauth.oauth_service.refresh_google_access_token", new_callable=AsyncMock) as mock_refresh:
        mock_refresh.return_value = mock_refresh_res

        creds = await get_valid_user_credentials(test_user.id, "calendar", db_session)
        assert creds is not None
        assert creds["access_token"] == "newly_refreshed_access_token_999"

        # Check that DB was updated with new encrypted token
        db_session.refresh(account)
        assert token_cipher.decrypt(account.encrypted_access_token) == "newly_refreshed_access_token_999"

# 9. Disconnect & Revocation Behavior
@pytest.mark.asyncio
async def test_disconnect_integration(client, db_session, test_user, auth_headers):
    account = OAuthAccount(
        user_id=test_user.id,
        provider="drive",
        encrypted_access_token=token_cipher.encrypt("active_drive_token")
    )
    conn = IntegrationConnection(
        user_id=test_user.id,
        provider="drive",
        status="connected",
        account_email=test_user.email
    )
    db_session.add_all([account, conn])
    db_session.commit()

    with patch("app.api.routes.integrations.revoke_google_token", new_callable=AsyncMock) as mock_revoke:
        mock_revoke.return_value = True

        res = client.post("/api/integrations/drive/disconnect", headers=auth_headers)
        assert res.status_code == status.HTTP_200_OK

        # Verify OAuthAccount is erased
        remaining_acc = db_session.query(OAuthAccount).filter(
            OAuthAccount.user_id == test_user.id,
            OAuthAccount.provider == "drive"
        ).first()
        assert remaining_acc is None

        # Verify connection status is not_connected
        db_session.refresh(conn)
        assert conn.status == "not_connected"
        assert conn.account_email is None

# 10. Tenant Isolation in Disconnect
def test_tenant_isolation_disconnect(client, db_session, test_user, auth_headers):
    user_b = User(
        id="usr_victim_999",
        email="victim@university.edu",
        full_name="Victim User"
    )
    account_b = OAuthAccount(
        user_id="usr_victim_999",
        provider="gmail",
        encrypted_access_token=token_cipher.encrypt("victim_token")
    )
    db_session.add_all([user_b, account_b])
    db_session.commit()

    res = client.post("/api/integrations/gmail/disconnect", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK

    intact_b = db_session.query(OAuthAccount).filter(OAuthAccount.user_id == "usr_victim_999").first()
    assert intact_b is not None

# 11. Production Safety Invariant Checks
def test_production_safety_invariants(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "APP_SECRET_KEY", "insecure-secret")
    with pytest.raises(ValueError) as exc:
        settings.check_production_safety()
    assert "Insecure or default APP_SECRET_KEY" in str(exc.value)

# 12. Dev-Login Blocked in Production
def test_dev_login_blocked_in_production(client, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    res = client.post(
        "/api/auth/dev-login",
        json={"email": "attacker@evil.com", "fullName": "Attacker"}
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

# 13. Protected Endpoints Reject Unauthenticated Access
def test_unauthenticated_request_rejected(client):
    res = client.get("/api/auth/me")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED

# 14. Callback State Validation & Error Redirects
def test_google_oauth_callback_expired_state(client):
    expired_payload = {
        "purpose": "login",
        "scope_category": "identity",
        "nonce": "test_nonce_expired_cb",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        "iat": datetime.now(timezone.utc) - timedelta(minutes=10)
    }
    expired_state = jwt.encode(expired_payload, settings.APP_SECRET_KEY, algorithm="HS256")
    res = client.get(
        f"/api/auth/google/callback?code=mock_code&state={expired_state}",
        headers={"Accept": "application/json"}
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "expired" in res.json()["detail"].lower()

def test_google_oauth_callback_invalid_state(client):
    res = client.get(
        "/api/auth/google/callback?code=mock_code&state=not.a.valid.jwt.state",
        headers={"Accept": "application/json"}
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "invalid oauth state" in res.json()["detail"].lower()

def test_google_oauth_callback_browser_error_redirect(client):
    res = client.get(
        "/api/auth/google/callback?error=access_denied",
        headers={"Accept": "text/html,application/xhtml+xml"},
        follow_redirects=False
    )
    assert res.status_code in (status.HTTP_307_TEMPORARY_REDIRECT, status.HTTP_302_FOUND)
    assert f"{settings.FRONTEND_URL}/auth/callback?error=" in res.headers["location"]

# 15. Callback Duplicate & Concurrency Deduplication
@pytest.mark.asyncio
async def test_google_oauth_callback_concurrent_duplicate_requests(client, db_session):
    state = create_oauth_state(purpose="login", scope_category="identity")

    mock_tokens = {
        "access_token": "ya29.concurrent_test_token",
        "expires_in": 3600,
        "scope": "openid email profile"
    }
    mock_profile = {
        "sub": "google_sub_concurrent",
        "email": "concurrent.user@university.edu",
        "name": "Concurrent User",
        "picture": "https://lh3.googleusercontent.com/photo.jpg",
        "email_verified": True
    }

    call_count = 0
    import asyncio
    async def slow_exchange(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return mock_tokens

    with patch("app.api.routes.auth.exchange_code_for_tokens", side_effect=slow_exchange), \
         patch("app.api.routes.auth.get_google_user_profile", new_callable=AsyncMock) as mock_userinfo:
        mock_userinfo.return_value = mock_profile

        loop = asyncio.get_event_loop()
        res1, res2 = await asyncio.gather(
            loop.run_in_executor(None, lambda: client.get(
                f"/api/auth/google/callback?code=code_concurrent&state={state}",
                headers={"Accept": "application/json"}
            )),
            loop.run_in_executor(None, lambda: client.get(
                f"/api/auth/google/callback?code=code_concurrent&state={state}",
                headers={"Accept": "application/json"}
            ))
        )

        assert res1.status_code == status.HTTP_200_OK
        assert res2.status_code == status.HTTP_200_OK
        assert call_count == 1

def test_google_oauth_callback_replayed_after_grace_window_rejected(client):
    state = create_oauth_state(purpose="login", scope_category="identity")
    verify_oauth_state(state, consume=True)
    payload = jwt.decode(state, settings.APP_SECRET_KEY, algorithms=["HS256"])
    nonce = payload["nonce"]

    # Simulate expired grace window (> 15 seconds)
    from app.services.google_oauth.oauth_service import _consumed_nonces
    _consumed_nonces[nonce]["consumed_at"] = datetime.now(timezone.utc) - timedelta(seconds=30)

    res = client.get(
        f"/api/auth/google/callback?code=mock_code&state={state}",
        headers={"Accept": "application/json"}
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "OAuth state has already been consumed (replay attempt detected)." == res.json()["detail"]

