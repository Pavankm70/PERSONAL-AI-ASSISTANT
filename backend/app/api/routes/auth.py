import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.db.session import get_db
from app.db.models import User, OAuthAccount, IntegrationConnection
from app.middleware.auth_middleware import get_current_user
from app.schemas import UserProfileResponse, DevLoginRequest, AuthTokenResponse
from app.services.google_oauth.crypto import token_cipher
from app.services.google_oauth.oauth_service import (
    create_oauth_state,
    verify_oauth_state,
    claim_oauth_state_async,
    complete_oauth_state,
    fail_oauth_state,
    record_state_ticket,
    create_auth_ticket,
    consume_auth_ticket,
    build_google_auth_url,
    exchange_code_for_tokens,
    get_google_user_profile,
    revoke_google_token,
    SCOPES_MAP
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class TicketExchangeRequest(BaseModel):
    ticket: str

def is_browser_request(request: Request) -> bool:
    """
    Checks if the request originated from a direct browser navigation.
    """
    accept = request.headers.get("accept", "")
    return "text/html" in accept

@router.get("/google/start")
@router.get("/google/url")
def google_oauth_start(
    request: Request,
    scope_category: str = Query("identity"),
    purpose: str = Query(None),
    auth_token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Constructs Google OAuth authorization URL with signed state parameter.
    Differentiates between initial login and incremental service linking.
    """
    if not purpose:
        purpose = "login" if scope_category == "identity" else "link"

    user_id = None
    if purpose == "link":
        # Resolve authenticated user from Bearer header or auth_token query parameter
        token = auth_token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to connect external Google services."
            )

        if token == "mock_jwt_token_aurelia_dev" and settings.APP_ENV != "production":
            dev_user = db.query(User).filter(User.email == "alex.chen@university.edu").first()
            if dev_user:
                user_id = dev_user.id
            else:
                raise HTTPException(status_code=401, detail="User account not found.")
        else:
            payload = decode_access_token(token)
            user_id = payload.get("sub")
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=401, detail="User account not found.")

    # Create tamper-proof signed state with single-use nonce
    state = create_oauth_state(purpose=purpose, scope_category=scope_category, user_id=user_id)

    if settings.GOOGLE_CLIENT_ID:
        auth_url = build_google_auth_url(scope_category=scope_category, state=state)
        return RedirectResponse(url=auth_url)

    if settings.APP_ENV == "production":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth is not configured on this server."
        )

    # In local development without Google credentials, redirect to dev callback for offline UI preview
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/auth/callback?code=mock_dev_code_auto&state={urllib.parse.quote(state)}"
    )

@router.get("/google/callback")
async def google_oauth_callback(
    request: Request,
    code: str = Query(None),
    state: str = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Exchanges code for tokens, verifies identity, encrypts tokens at rest,
    and either logs the user in or links the service to their account.
    Prevents token exposure in URLs using the single-use ticket pattern.
    Safe against concurrent duplicate requests and browser prefetching.
    """
    if error:
        if is_browser_request(request):
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/auth/callback?error={urllib.parse.quote(error)}"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth authorization error: {error}"
        )

    if not code or not state:
        if is_browser_request(request):
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/auth/callback?error={urllib.parse.quote('Both code and state parameters are required.')}"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'code' and 'state' parameters are required."
        )

    try:
        # 1. Cryptographically verify the state parameter and coordinate duplicate requests
        state_data, is_leader = await claim_oauth_state_async(state)

        if not is_leader:
            redirect_url = state_data.get("_redirect_url")
            ticket = state_data.get("_cached_ticket")
            if is_browser_request(request):
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                if ticket:
                    return RedirectResponse(url=f"{settings.FRONTEND_URL}/auth/callback?ticket={ticket}")
            if ticket:
                return {"ticket": ticket, "deduplicated": True}
            return state_data.get("_response_data", {"success": True, "deduplicated": True})

        purpose = state_data.get("purpose", "login")
        scope_category = state_data.get("scope_category", "identity")
        state_user_id = state_data.get("user_id")

        # 2. Check for offline development simulation fallback
        if code == "mock_dev_code_auto" and settings.APP_ENV != "production" and not settings.GOOGLE_CLIENT_ID:
            email = "alex.chen@university.edu"
            full_name = "Alex Chen"
            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(
                    email=email,
                    full_name=full_name,
                    timezone="America/Los_Angeles",
                    onboarding_complete=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)

            jwt_token = create_access_token({"sub": user.id, "email": user.email})
            ticket = create_auth_ticket(user_id=user.id, token=jwt_token, expires_seconds=60)
            redirect_url = f"{settings.FRONTEND_URL}/auth/callback?ticket={ticket}"
            resp_data = {
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "fullName": user.full_name,
                    "avatarUrl": user.avatar_url,
                    "timezone": user.timezone,
                    "onboardingComplete": user.onboarding_complete,
                    "createdAt": user.created_at.isoformat()
                },
                "token": jwt_token
            }
            complete_oauth_state(state, ticket=ticket, redirect_url=redirect_url, response_data=resp_data)
            if is_browser_request(request):
                return RedirectResponse(url=redirect_url)
            return resp_data

        # 3. Real Google OAuth Token Exchange
        token_data = await exchange_code_for_tokens(code)
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No access token returned by Google."
            )

        # 4. Fetch verified user profile from Google (validates email & email_verified)
        profile = await get_google_user_profile(access_token)
        google_sub = profile.get("sub")
        email = profile["email"].lower().strip()
        full_name = profile.get("name") or email.split("@")[0]
        avatar_url = profile.get("picture")

        # 5. Encrypt tokens at rest
        encrypted_access_token = token_cipher.encrypt(access_token)
        encrypted_refresh_token = token_cipher.encrypt(token_data["refresh_token"]) if token_data.get("refresh_token") else None

        expires_in = token_data.get("expires_in", 3600)
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        scopes_list = token_data.get("scope", "").split() if token_data.get("scope") else SCOPES_MAP.get(scope_category, [])

        # 6. Process based on Purpose
        if purpose == "login":
            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(
                    email=email,
                    full_name=full_name,
                    avatar_url=avatar_url,
                    timezone="UTC",
                    onboarding_complete=False
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                if avatar_url and not user.avatar_url:
                    user.avatar_url = avatar_url
                    db.commit()

            # Upsert primary Google identity account
            account = db.query(OAuthAccount).filter(
                OAuthAccount.user_id == user.id,
                OAuthAccount.provider == "google"
            ).first()

            if not account:
                account = OAuthAccount(
                    user_id=user.id,
                    provider="google",
                    external_user_id=google_sub,
                    email=email,
                    encrypted_access_token=encrypted_access_token,
                    encrypted_refresh_token=encrypted_refresh_token,
                    scopes=scopes_list,
                    token_expires_at=token_expires_at
                )
                db.add(account)
            else:
                account.external_user_id = google_sub
                account.email = email
                account.encrypted_access_token = encrypted_access_token
                if encrypted_refresh_token:
                    account.encrypted_refresh_token = encrypted_refresh_token
                account.scopes = scopes_list
                account.token_expires_at = token_expires_at

            db.commit()

            # Issue AURELIA JWT session token
            jwt_token = create_access_token({"sub": user.id, "email": user.email})
            ticket = create_auth_ticket(user_id=user.id, token=jwt_token, expires_seconds=60)
            redirect_url = f"{settings.FRONTEND_URL}/auth/callback?ticket={ticket}"
            resp_data = {
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "fullName": user.full_name,
                    "avatarUrl": user.avatar_url,
                    "timezone": user.timezone,
                    "onboardingComplete": user.onboarding_complete,
                    "createdAt": user.created_at.isoformat()
                },
                "token": jwt_token
            }
            complete_oauth_state(state, ticket=ticket, redirect_url=redirect_url, response_data=resp_data)

            if is_browser_request(request):
                return RedirectResponse(url=redirect_url)
            return resp_data

        elif purpose == "link":
            if not state_user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="State missing target user identifier for service linking."
                )

            target_user = db.query(User).filter(User.id == state_user_id).first()
            if not target_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Authenticated user account not found for linking."
                )

            provider_name = scope_category

            # Prevent cross-user account takeover/replacement:
            conflict = db.query(OAuthAccount).filter(
                OAuthAccount.provider == provider_name,
                OAuthAccount.external_user_id == google_sub,
                OAuthAccount.user_id != target_user.id
            ).first()

            if conflict:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This Google account is already linked to a different AURELIA user."
                )

            account = db.query(OAuthAccount).filter(
                OAuthAccount.user_id == target_user.id,
                OAuthAccount.provider == provider_name
            ).first()

            if not account:
                account = OAuthAccount(
                    user_id=target_user.id,
                    provider=provider_name,
                    external_user_id=google_sub,
                    email=email,
                    encrypted_access_token=encrypted_access_token,
                    encrypted_refresh_token=encrypted_refresh_token,
                    scopes=scopes_list,
                    token_expires_at=token_expires_at
                )
                db.add(account)
            else:
                account.external_user_id = google_sub
                account.email = email
                account.encrypted_access_token = encrypted_access_token
                # Preserve existing refresh token if Google did not re-issue one
                if encrypted_refresh_token:
                    account.encrypted_refresh_token = encrypted_refresh_token
                account.scopes = scopes_list
                account.token_expires_at = token_expires_at

            # Update integration connection status
            conn = db.query(IntegrationConnection).filter(
                IntegrationConnection.user_id == target_user.id,
                IntegrationConnection.provider == provider_name
            ).first()

            if not conn:
                conn = IntegrationConnection(
                    user_id=target_user.id,
                    provider=provider_name,
                    status="connected",
                    account_email=email,
                    last_synced_at=datetime.now(timezone.utc)
                )
                db.add(conn)
            else:
                conn.status = "connected"
                conn.account_email = email
                conn.error_message = None
                conn.last_synced_at = datetime.now(timezone.utc)

            db.commit()

            redirect_url = f"{settings.FRONTEND_URL}/app/integrations?status=connected&provider={provider_name}"
            resp_data = {
                "success": True,
                "provider": provider_name,
                "status": "connected",
                "accountEmail": email
            }
            complete_oauth_state(state, redirect_url=redirect_url, response_data=resp_data)

            if is_browser_request(request):
                return RedirectResponse(url=redirect_url)
            return resp_data

        else:
            raise HTTPException(status_code=400, detail=f"Unrecognized OAuth purpose: {purpose}")

    except HTTPException as exc:
        if state:
            fail_oauth_state(state, str(exc.detail))
        if is_browser_request(request):
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/auth/callback?error={urllib.parse.quote(str(exc.detail))}"
            )
        raise
    except Exception as exc:
        if state:
            fail_oauth_state(state, "Internal authentication error during Google OAuth.")
        if is_browser_request(request):
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/auth/callback?error={urllib.parse.quote('Internal authentication error during Google OAuth.')}"
            )
        raise

@router.post("/exchange-ticket")
def exchange_ticket(req: TicketExchangeRequest, db: Session = Depends(get_db)):
    """
    Exchanges a single-use authorization ticket for the user session token.
    Ticket is atomically consumed and valid for 60 seconds.
    """
    data = consume_auth_ticket(req.ticket)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired authorization ticket."
        )

    user = db.query(User).filter(User.id == data["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "fullName": user.full_name,
            "avatarUrl": user.avatar_url,
            "timezone": user.timezone,
            "onboardingComplete": user.onboarding_complete,
            "createdAt": user.created_at.isoformat()
        },
        "token": data["token"]
    }

@router.post("/dev-login")
def dev_login(req: DevLoginRequest, db: Session = Depends(get_db)):
    """
    Fast developer sign-in without external OAuth credentials.
    Strictly blocked in production environments.
    """
    if settings.APP_ENV.lower() == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development login is disabled in production environment."
        )

    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        user = User(
            email=req.email,
            full_name=req.fullName,
            timezone="America/Los_Angeles",
            onboarding_complete=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": user.id, "email": user.email})
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "fullName": user.full_name,
            "avatarUrl": user.avatar_url,
            "timezone": user.timezone,
            "onboardingComplete": user.onboarding_complete,
            "createdAt": user.created_at.isoformat()
        },
        "token": token
    }

@router.get("/me")
def get_current_user_profile(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "fullName": user.full_name,
        "avatarUrl": user.avatar_url,
        "timezone": user.timezone,
        "onboardingComplete": user.onboarding_complete,
        "createdAt": user.created_at.isoformat()
    }

@router.post("/logout")
def logout(user: User = Depends(get_current_user)):
    return {"success": True, "message": "Logged out successfully"}

@router.post("/google/disconnect")
async def disconnect_google(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Revokes Google OAuth tokens and deletes all linked Google accounts for this user.
    """
    accounts = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider.in_(["google", "gmail", "calendar", "drive", "google_all"])
    ).all()

    revoked_count = 0
    for acc in accounts:
        # Prioritize revoking refresh token, then access token
        if acc.encrypted_refresh_token:
            if await revoke_google_token(acc.encrypted_refresh_token):
                revoked_count += 1
        elif acc.encrypted_access_token:
            if await revoke_google_token(acc.encrypted_access_token):
                revoked_count += 1

    db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider.in_(["google", "gmail", "calendar", "drive", "google_all"])
    ).delete(synchronize_session=False)

    db.query(IntegrationConnection).filter(
        IntegrationConnection.user_id == user.id,
        IntegrationConnection.provider.in_(["google", "gmail", "calendar", "drive"])
    ).update({"status": "not_connected", "account_email": None}, synchronize_session=False)

    db.commit()
    return {
        "success": True,
        "message": "All Google accounts disconnected and tokens revoked.",
        "tokensRevoked": revoked_count
    }
