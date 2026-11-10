import os
import uuid
import jwt
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.google_oauth.crypto import token_cipher
from app.db.models import User, OAuthAccount, IntegrationConnection

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES_MAP = {
    "identity": [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ],
    "gmail": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.modify"
    ],
    "calendar": [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly"
    ],
    "drive": [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly"
    ],
    "google_all": [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly"
    ]
}

# In-memory store for consumed state nonces (prevents replay attacks while coordinating concurrent in-flight requests and fast retries within a 15-second grace window)
# Structure: nonce -> {"exp": datetime, "consumed_at": datetime, "status": str, "event": asyncio.Event, "ticket": Optional[str], "redirect_url": Optional[str], "response_data": Optional[Dict[str, Any]], "error": Optional[str], "user_id": Optional[str]}
_consumed_nonces: Dict[str, Dict[str, Any]] = {}

# In-memory store for single-use short-lived authorization exchange tickets (prevents exposing JWT in browser URL)
_auth_tickets: Dict[str, Dict[str, Any]] = {}

def _cleanup_expired_records():
    now = datetime.now(timezone.utc)
    expired_nonces = [n for n, data in _consumed_nonces.items() if data.get("exp", now) < now]
    for n in expired_nonces:
        _consumed_nonces.pop(n, None)

    expired_tickets = [t for t, data in _auth_tickets.items() if data["exp"] < now]
    for t in expired_tickets:
        _auth_tickets.pop(t, None)

def create_oauth_state(purpose: str, scope_category: str, user_id: Optional[str] = None) -> str:
    """
    Creates a signed, time-limited, tamper-proof state token to prevent CSRF and replay attacks.
    """
    _cleanup_expired_records()
    payload = {
        "purpose": purpose,                      # "login" | "link"
        "scope_category": scope_category,        # "identity" | "gmail" | "calendar" | "drive" | "google_all"
        "user_id": user_id,                      # Set when linking an existing authenticated user
        "nonce": uuid.uuid4().hex,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, settings.APP_SECRET_KEY, algorithm="HS256")

def decode_and_validate_state_token(state_token: str) -> Dict[str, Any]:
    """
    Decodes and validates the cryptographic signature, expiration, and nonce of an OAuth state token.
    Raises HTTPException for missing, expired, tampered, or invalid tokens.
    """
    _cleanup_expired_records()
    if not state_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth state parameter."
        )
    try:
        payload = jwt.decode(
            state_token,
            settings.APP_SECRET_KEY,
            algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state parameter has expired. Please try again."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state parameter. Possible CSRF attack detected."
        )

    nonce = payload.get("nonce")
    if not nonce:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state missing replay protection nonce."
        )

    return payload

def verify_oauth_state(state_token: str, consume: bool = True) -> Dict[str, Any]:
    """
    Synchronous validation of the OAuth state token signature, expiration, and replay protection.
    Maintains compatibility with synchronous tests and callers.
    """
    payload = decode_and_validate_state_token(state_token)
    nonce = payload["nonce"]

    now = datetime.now(timezone.utc)
    if nonce in _consumed_nonces:
        info = _consumed_nonces[nonce]
        consumed_at = info.get("consumed_at")
        ticket = info.get("ticket")
        redirect_url = info.get("redirect_url")
        status_val = info.get("status", "completed")

        # 15-second grace window for concurrent browser re-entry when ticket or redirect_url was recorded
        if consumed_at and (now - consumed_at) < timedelta(seconds=15) and (ticket or redirect_url):
            payload["_cached_ticket"] = ticket
            payload["_redirect_url"] = redirect_url
            payload["_response_data"] = info.get("response_data")
            payload["_is_deduplicated"] = True
            return payload

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state has already been consumed (replay attempt detected)."
        )

    if consume:
        exp_timestamp = payload.get("exp")
        exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc) if exp_timestamp else now + timedelta(minutes=15)
        _consumed_nonces[nonce] = {
            "exp": exp_dt,
            "consumed_at": now,
            "status": "completed",
            "ticket": None,
            "redirect_url": None,
            "response_data": None,
            "error": None,
            "user_id": payload.get("user_id")
        }

    return payload

async def claim_oauth_state_async(state_token: str) -> Tuple[Dict[str, Any], bool]:
    """
    Atomically verifies and claims the OAuth state token for async callback processing.
    Coordinates concurrent duplicate requests (e.g. Chrome prefetch, double-click, React StrictMode):
    - The first request (leader) claims the state in 'in_flight' status and proceeds to exchange tokens.
    - Concurrent duplicate requests (followers) await the leader's completion and receive the identical result.
    - Replays after the 15-second grace window are strictly rejected (replay attack prevention).
    Returns (payload, is_leader). If is_leader is False, payload contains '_redirect_url' or '_cached_ticket'.
    """
    payload = decode_and_validate_state_token(state_token)
    nonce = payload["nonce"]
    now = datetime.now(timezone.utc)

    if nonce in _consumed_nonces:
        entry = _consumed_nonces[nonce]
        status_val = entry.get("status", "completed")

        if status_val == "in_flight":
            # Another request with the same state is actively in progress.
            # Await leader completion up to 15 seconds.
            event = entry.get("event")
            if event and isinstance(event, asyncio.Event):
                try:
                    await asyncio.wait_for(event.wait(), timeout=15.0)
                except asyncio.TimeoutError:
                    raise HTTPException(
                        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                        detail="OAuth authorization processing timed out."
                    )

            if entry.get("status") == "failed":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=entry.get("error") or "OAuth state exchange failed."
                )

            payload["_cached_ticket"] = entry.get("ticket")
            payload["_redirect_url"] = entry.get("redirect_url")
            payload["_response_data"] = entry.get("response_data")
            payload["_is_deduplicated"] = True
            return payload, False

        elif status_val == "completed":
            consumed_at = entry.get("consumed_at")
            if consumed_at and (now - consumed_at) < timedelta(seconds=15) and (entry.get("ticket") or entry.get("redirect_url")):
                payload["_cached_ticket"] = entry.get("ticket")
                payload["_redirect_url"] = entry.get("redirect_url")
                payload["_response_data"] = entry.get("response_data")
                payload["_is_deduplicated"] = True
                return payload, False

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAuth state has already been consumed (replay attempt detected)."
            )

        elif status_val == "failed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=entry.get("error") or "OAuth state has already been consumed (replay attempt detected)."
            )

    # First request: claim the nonce as leader
    exp_timestamp = payload.get("exp")
    exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc) if exp_timestamp else now + timedelta(minutes=15)
    event = asyncio.Event()
    _consumed_nonces[nonce] = {
        "exp": exp_dt,
        "consumed_at": now,
        "status": "in_flight",
        "event": event,
        "ticket": None,
        "redirect_url": None,
        "response_data": None,
        "error": None,
        "user_id": payload.get("user_id")
    }
    return payload, True

def complete_oauth_state(
    state_token: str,
    ticket: Optional[str] = None,
    redirect_url: Optional[str] = None,
    response_data: Optional[Dict[str, Any]] = None
):
    """
    Marks state as successfully completed and wakes up waiting follower requests.
    """
    try:
        payload = jwt.decode(state_token, settings.APP_SECRET_KEY, algorithms=["HS256"])
        nonce = payload.get("nonce")
        if nonce and nonce in _consumed_nonces:
            entry = _consumed_nonces[nonce]
            entry["status"] = "completed"
            entry["ticket"] = ticket
            entry["redirect_url"] = redirect_url
            entry["response_data"] = response_data
            event = entry.get("event")
            if event and isinstance(event, asyncio.Event):
                event.set()
    except Exception:
        pass

def fail_oauth_state(state_token: str, error_message: str):
    """
    Marks state as failed and wakes up waiting follower requests so they don't hang.
    """
    try:
        payload = jwt.decode(state_token, settings.APP_SECRET_KEY, algorithms=["HS256"])
        nonce = payload.get("nonce")
        if nonce and nonce in _consumed_nonces:
            entry = _consumed_nonces[nonce]
            entry["status"] = "failed"
            entry["error"] = error_message
            event = entry.get("event")
            if event and isinstance(event, asyncio.Event):
                event.set()
    except Exception:
        pass

def record_state_ticket(state_token: str, ticket: str):
    """
    Backwards-compatible helper to associate an issued ticket with state nonce.
    """
    complete_oauth_state(state_token, ticket=ticket)

def create_auth_ticket(user_id: str, token: str, expires_seconds: int = 60) -> str:
    """
    Generates a single-use, 60-second authorization exchange ticket.
    Prevents leaking JWT session tokens in browser URLs or history.
    """
    _cleanup_expired_records()
    ticket = f"tkt_{uuid.uuid4().hex}"
    _auth_tickets[ticket] = {
        "user_id": user_id,
        "token": token,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)
    }
    return ticket

def consume_auth_ticket(ticket: str) -> Optional[Dict[str, Any]]:
    """
    Atomically retrieves and consumes an authorization ticket.
    Returns None if missing or expired.
    """
    _cleanup_expired_records()
    if not ticket or ticket not in _auth_tickets:
        return None

    data = _auth_tickets.pop(ticket)
    if data["exp"] < datetime.now(timezone.utc):
        return None

    return data

def build_google_auth_url(scope_category: str, state: str, prompt: str = "consent") -> str:
    """
    Constructs the standard Google OAuth 2.0 authorization URL.
    """
    scopes = SCOPES_MAP.get(scope_category, SCOPES_MAP["identity"])
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID or "",
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": prompt,
        "state": state
    }
    import urllib.parse
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

async def exchange_code_for_tokens(code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
    """
    Exchanges the authorization code with Google's token endpoint.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth credentials (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET) are not configured."
        )

    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri or settings.GOOGLE_REDIRECT_URI
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(GOOGLE_TOKEN_URL, data=data)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Network error contacting Google token endpoint: {str(e)}"
            )

        if response.status_code != 200:
            error_data = {}
            try:
                error_data = response.json()
            except Exception:
                pass
            error_desc = error_data.get("error_description") or error_data.get("error") or response.text
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Google token exchange failed: {error_desc}"
            )

        return response.json()

async def get_google_user_profile(access_token: str) -> Dict[str, Any]:
    """
    Fetches the authenticated user's profile from Google using the verified access token.
    Enforces verified email address check.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(GOOGLE_USERINFO_URL, headers=headers)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Network error contacting Google userinfo: {str(e)}"
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to retrieve verified user profile from Google."
            )

        profile = response.json()
        if not profile.get("email"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account has no associated email address."
            )

        # Enforce email verification check from Google
        email_verified = profile.get("email_verified")
        if email_verified is False or str(email_verified).lower() == "false":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email is not verified by Google. A verified email is required."
            )

        return profile

async def refresh_google_access_token(encrypted_refresh_token: str) -> Dict[str, Any]:
    """
    Uses the decrypted refresh token to obtain a fresh access token from Google.
    """
    refresh_token = token_cipher.decrypt(encrypted_refresh_token)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing refresh token."
        )

    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(GOOGLE_TOKEN_URL, data=data)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Network error refreshing Google token: {str(e)}"
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to refresh Google access token. Access may have been revoked."
            )

        return response.json()

async def revoke_google_token(encrypted_token: str) -> bool:
    """
    Revokes the OAuth token on Google's servers.
    """
    token = token_cipher.decrypt(encrypted_token)
    if not token:
        return False

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.post(GOOGLE_REVOKE_URL, params={"token": token})
            return res.status_code == 200
        except Exception:
            return False

async def get_valid_user_credentials(user_id: str, provider: str, db: Session) -> Optional[Dict[str, Any]]:
    """
    Retrieves and decrypts the user's OAuth credentials for a given provider.
    Automatically refreshes the access token if it has expired or is expiring soon.
    If the token has expired and no refresh token exists, sets status to 'expired' and returns None.
    """
    account = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user_id,
        OAuthAccount.provider == provider
    ).first()

    if not account:
        # Check if user authorized via google_all or primary google
        for fallback_provider in ["google_all", "google"]:
            candidate = db.query(OAuthAccount).filter(
                OAuthAccount.user_id == user_id,
                OAuthAccount.provider == fallback_provider
            ).first()
            if candidate:
                account = candidate
                break

    if not account:
        return None

    # Check if access token is expired or within 5 minutes of expiring
    needs_refresh = False
    if account.token_expires_at:
        now = datetime.now(timezone.utc)
        expires_at = account.token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at - now < timedelta(minutes=5):
            needs_refresh = True

    if needs_refresh:
        if account.encrypted_refresh_token:
            try:
                refreshed = await refresh_google_access_token(account.encrypted_refresh_token)
                new_access_token = refreshed["access_token"]
                expires_in = refreshed.get("expires_in", 3600)
                account.encrypted_access_token = token_cipher.encrypt(new_access_token)
                account.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                if "refresh_token" in refreshed:
                    account.encrypted_refresh_token = token_cipher.encrypt(refreshed["refresh_token"])
                db.commit()
                db.refresh(account)
            except Exception:
                # Mark integration as expired/error
                conn = db.query(IntegrationConnection).filter(
                    IntegrationConnection.user_id == user_id,
                    IntegrationConnection.provider == provider
                ).first()
                if conn:
                    conn.status = "expired"
                    conn.error_message = "Token refresh failed. Please reconnect your account."
                    db.commit()
                return None
        else:
            # Token is expired and NO refresh token exists to renew it
            conn = db.query(IntegrationConnection).filter(
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.provider == provider
            ).first()
            if conn:
                conn.status = "expired"
                conn.error_message = "Access token expired and no refresh token is stored. Please reconnect."
                db.commit()
            return None

    decrypted_access_token = token_cipher.decrypt(account.encrypted_access_token)
    return {
        "access_token": decrypted_access_token,
        "token_expires_at": account.token_expires_at,
        "scopes": account.scopes or [],
        "email": account.email
    }
