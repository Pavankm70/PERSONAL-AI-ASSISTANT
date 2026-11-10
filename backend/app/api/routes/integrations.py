from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, OAuthAccount, IntegrationConnection
from app.middleware.auth_middleware import get_current_user
from app.core.config import settings
from app.services.google_oauth.oauth_service import revoke_google_token, SCOPES_MAP
from app.services.capabilities import (
    get_user_capabilities,
    update_user_capabilities,
    get_capability_metadata_for_user,
    SUPPORTED_CAPABILITIES
)

router = APIRouter(prefix="/integrations", tags=["Integrations"])

class CapabilityUpdateRequest(BaseModel):
    capabilities: Dict[str, bool]

@router.get("")
def get_integrations_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns real connection status, granted OAuth scopes, and application-level capability toggles
    for all workspace integrations for the current authenticated user.
    """
    oauths = db.query(OAuthAccount).filter(OAuthAccount.user_id == user.id).all()
    oauth_by_provider = {o.provider: o for o in oauths}

    connections = db.query(IntegrationConnection).filter(IntegrationConnection.user_id == user.id).all()
    conn_by_provider = {c.provider: c for c in connections}

    def get_provider_details(provider_key: str):
        account = oauth_by_provider.get(provider_key) or oauth_by_provider.get("google_all")
        conn = conn_by_provider.get(provider_key)
        granted_scopes = account.scopes if account and account.scopes else []

        if account:
            # Check if token is expired
            if account.token_expires_at:
                now = datetime.now(timezone.utc)
                exp = account.token_expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < now and not account.encrypted_refresh_token:
                    return "expired", account.email, "Access token expired and no refresh token available.", granted_scopes
            return "connected", account.email, None, granted_scopes

        if conn and conn.status == "connected":
            return "connected", conn.account_email, None, granted_scopes

        err = None
        if not settings.GOOGLE_CLIENT_ID and provider_key in ("gmail", "calendar", "drive"):
            err = "Google OAuth credentials not configured on server."

        return "not_connected", None, err, granted_scopes

    gmail_status, gmail_email, gmail_err, gmail_scopes = get_provider_details("gmail")
    cal_status, cal_email, cal_err, cal_scopes = get_provider_details("calendar")
    drive_status, drive_email, drive_err, drive_scopes = get_provider_details("drive")
    google_status, google_email, _, google_scopes = get_provider_details("google")

    return [
        {
            "id": "int_google",
            "provider": "google",
            "name": "Google Identity",
            "description": "Primary OAuth identity used for application authentication and profile sync.",
            "category": "Identity",
            "icon": "shield",
            "status": google_status,
            "scopes": SCOPES_MAP["identity"],
            "grantedScopes": google_scopes,
            "accountEmail": google_email or user.email,
            "capabilities": {},
            "supportedCapabilities": []
        },
        {
            "id": "int_gmail",
            "provider": "gmail",
            "name": "Gmail Service",
            "description": "Search inbox messages, summarize email threads, extract deadlines, and compose drafts.",
            "category": "Communication",
            "icon": "mail",
            "status": gmail_status,
            "scopes": SCOPES_MAP["gmail"],
            "grantedScopes": gmail_scopes,
            "accountEmail": gmail_email,
            "errorMessage": gmail_err,
            "capabilities": get_user_capabilities(user.id, "gmail", db),
            "supportedCapabilities": get_capability_metadata_for_user(user.id, "gmail", db)
        },
        {
            "id": "int_calendar",
            "provider": "calendar",
            "name": "Google Calendar",
            "description": "Agenda retrieval, scheduling gap analysis, and user-confirmed event insertion.",
            "category": "Scheduling",
            "icon": "calendar",
            "status": cal_status,
            "scopes": SCOPES_MAP["calendar"],
            "grantedScopes": cal_scopes,
            "accountEmail": cal_email,
            "errorMessage": cal_err,
            "capabilities": get_user_capabilities(user.id, "calendar", db),
            "supportedCapabilities": get_capability_metadata_for_user(user.id, "calendar", db)
        },
        {
            "id": "int_drive",
            "provider": "drive",
            "name": "Google Drive",
            "description": "Access project documents, PDFs, and notes stored in authorized Drive folders.",
            "category": "Storage",
            "icon": "hard-drive",
            "status": drive_status,
            "scopes": SCOPES_MAP["drive"],
            "grantedScopes": drive_scopes,
            "accountEmail": drive_email,
            "errorMessage": drive_err,
            "capabilities": get_user_capabilities(user.id, "drive", db),
            "supportedCapabilities": get_capability_metadata_for_user(user.id, "drive", db)
        },
        {
            "id": "int_rag",
            "provider": "rag",
            "name": "Personal Knowledge Base",
            "description": "Tenant-isolated vector retrieval index for personal notes and course syllabi.",
            "category": "Memory",
            "icon": "database",
            "status": "connected",
            "scopes": ["internal_vector_store"],
            "grantedScopes": ["internal_vector_store"],
            "accountEmail": None,
            "capabilities": {},
            "supportedCapabilities": []
        },
        {
            "id": "int_web",
            "provider": "web_search",
            "name": "Live Web Intelligence",
            "description": "Fact retrieval and citation grounding for external research queries.",
            "category": "Research",
            "icon": "search",
            "status": "connected" if settings.WEB_SEARCH_API_KEY else "not_connected",
            "scopes": ["tavily_search"],
            "grantedScopes": ["tavily_search"] if settings.WEB_SEARCH_API_KEY else [],
            "errorMessage": None if settings.WEB_SEARCH_API_KEY else "WEB_SEARCH_API_KEY optional, not configured.",
            "capabilities": {},
            "supportedCapabilities": []
        },
        {
            "id": "int_weather",
            "provider": "weather",
            "name": "Weather Telemetry",
            "description": "Meteorological forecast telemetry for agenda scheduling.",
            "category": "Context",
            "icon": "cloud-sun",
            "status": "connected",
            "scopes": ["openmeteo"],
            "grantedScopes": ["openmeteo"],
            "capabilities": {},
            "supportedCapabilities": []
        }
    ]

@router.patch("/{provider}/capabilities")
@router.post("/{provider}/capabilities")
def update_capabilities_endpoint(
    provider: str,
    payload: CapabilityUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates the application-level capabilities for an integration service.
    Controls what actions Aurelia AI is allowed to perform without revoking Google OAuth grant.
    """
    if provider not in SUPPORTED_CAPABILITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Capability management is not supported for provider '{provider}'."
        )

    updated = update_user_capabilities(
        user_id=user.id,
        provider=provider,
        capabilities=payload.capabilities,
        db=db
    )

    return {
        "success": True,
        "provider": provider,
        "capabilities": updated,
        "supportedCapabilities": get_capability_metadata_for_user(user.id, provider, db)
    }

@router.post("/{provider}/connect")
def connect_integration(
    provider: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns the OAuth authorization start URL for incremental service linking.
    """
    if provider not in ("gmail", "calendar", "drive", "google_all", "google"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider}"
        )

    auth_url = f"{settings.BACKEND_URL}/api/auth/google/start?scope_category={provider}&purpose=link"
    return {
        "success": True,
        "provider": provider,
        "authUrl": auth_url
    }

@router.post("/{provider}/disconnect")
async def disconnect_integration(
    provider: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Revokes the provider token with Google and cleans up stored accounts and connections.
    Strictly tenant-isolated: can only delete current user's records.
    """
    account = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider == provider
    ).first()

    if account:
        if account.encrypted_access_token:
            await revoke_google_token(account.encrypted_access_token)
        elif account.encrypted_refresh_token:
            await revoke_google_token(account.encrypted_refresh_token)

        db.delete(account)

    conn = db.query(IntegrationConnection).filter(
        IntegrationConnection.user_id == user.id,
        IntegrationConnection.provider == provider
    ).first()

    if conn:
        conn.status = "not_connected"
        conn.account_email = None
        conn.error_message = None

    db.commit()
    return {"success": True, "provider": provider, "status": "not_connected"}
