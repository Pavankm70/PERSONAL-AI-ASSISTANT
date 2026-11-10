"""
AURELIA AI — Website-Level Google Permissions & Capabilities Management
Enforces tenant-isolated application-level capability toggles for Google Calendar, Gmail, and Google Drive.

Security and Invariant Rules:
1. An application-level capability toggle prevents the agent from using that capability, even if the OAuth token has broader access.
2. Disabling a capability does NOT claim to revoke a Google OAuth scope; it enforces backend blocking.
3. Actual OAuth token revocation is handled via the separate disconnect flow.
4. Capability preferences are stored per user in the database and enforced on all tool executions.
5. Disabled capabilities return an explicit error and are never bypassed by the model.
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.db.models import IntegrationConnection, OAuthAccount

SUPPORTED_CAPABILITIES: Dict[str, List[Dict[str, Any]]] = {
    "calendar": [
        {
            "key": "read_events",
            "label": "Read Calendar Events",
            "description": "View scheduled meetings, check availability, and inspect open slots.",
            "requiredScope": "https://www.googleapis.com/auth/calendar.readonly",
            "default": True
        },
        {
            "key": "create_events",
            "label": "Create Events & Study Sessions",
            "description": "Propose and insert new calendar events and study blocks (requires explicit confirmation).",
            "requiredScope": "https://www.googleapis.com/auth/calendar.events",
            "default": True
        },
        {
            "key": "edit_events",
            "label": "Edit & Reschedule Events",
            "description": "Modify event times, descriptions, and locations upon confirmed request.",
            "requiredScope": "https://www.googleapis.com/auth/calendar.events",
            "default": True
        },
        {
            "key": "delete_events",
            "label": "Delete & Cancel Events",
            "description": "Cancel scheduled events and personal study sessions upon explicit confirmation.",
            "requiredScope": "https://www.googleapis.com/auth/calendar.events",
            "default": True
        }
    ],
    "gmail": [
        {
            "key": "read_messages",
            "label": "Search & Read Emails",
            "description": "Search inbox messages, summarize email threads, and extract deadlines and action items.",
            "requiredScope": "https://www.googleapis.com/auth/gmail.readonly",
            "default": True
        },
        {
            "key": "create_drafts",
            "label": "Compose Email Drafts",
            "description": "Prepare proposed email replies and drafts saved in your Gmail account for review.",
            "requiredScope": "https://www.googleapis.com/auth/gmail.compose",
            "default": True
        },
        {
            "key": "send_messages",
            "label": "Send Approved Emails",
            "description": "Dispatch emails through Gmail only after you explicitly inspect and approve the final draft.",
            "requiredScope": "https://www.googleapis.com/auth/gmail.modify",
            "default": False
        }
    ],
    "drive": [
        {
            "key": "search_files",
            "label": "Search Drive Files",
            "description": "Search and list documents, PDFs, and spreadsheets in your authorized Google Drive.",
            "requiredScope": "https://www.googleapis.com/auth/drive.metadata.readonly",
            "default": True
        },
        {
            "key": "read_file_content",
            "label": "Read & Ground on Documents",
            "description": "Extract text content from Drive documents and PDFs to answer evidence-grounded questions.",
            "requiredScope": "https://www.googleapis.com/auth/drive.readonly",
            "default": True
        },
        {
            "key": "create_edit_files",
            "label": "Create & Modify Files",
            "description": "Upload or edit documents directly in Google Drive (when supported).",
            "requiredScope": "https://www.googleapis.com/auth/drive.file",
            "default": False
        }
    ]
}

def get_default_capabilities(provider: str) -> Dict[str, bool]:
    """Returns the default boolean settings for all capabilities of a given provider."""
    caps_meta = SUPPORTED_CAPABILITIES.get(provider, [])
    return {c["key"]: c["default"] for c in caps_meta}

def get_user_capabilities(user_id: str, provider: str, db: Session) -> Dict[str, bool]:
    """
    Retrieves the persisted capability preferences for a user and provider.
    Merges saved overrides on top of defaults.
    """
    defaults = get_default_capabilities(provider)
    conn = db.query(IntegrationConnection).filter(
        IntegrationConnection.user_id == user_id,
        IntegrationConnection.provider == provider
    ).first()

    if not conn or not conn.capabilities:
        return defaults

    saved = conn.capabilities if isinstance(conn.capabilities, dict) else {}
    merged = dict(defaults)
    merged.update(saved)
    return merged

def update_user_capabilities(
    user_id: str,
    provider: str,
    capabilities: Dict[str, bool],
    db: Session
) -> Dict[str, bool]:
    """
    Persists user capability preferences into the database.
    Strictly tenant-isolated by user_id.
    """
    if provider not in SUPPORTED_CAPABILITIES:
        raise ValueError(f"Unknown provider '{provider}' for capability management.")

    conn = db.query(IntegrationConnection).filter(
        IntegrationConnection.user_id == user_id,
        IntegrationConnection.provider == provider
    ).first()

    current = get_user_capabilities(user_id, provider, db)
    # Validate and filter to supported keys
    valid_keys = {c["key"] for c in SUPPORTED_CAPABILITIES[provider]}
    for k, v in capabilities.items():
        if k in valid_keys:
            current[k] = bool(v)

    if not conn:
        conn = IntegrationConnection(
            user_id=user_id,
            provider=provider,
            status="not_connected",
            capabilities=current
        )
        db.add(conn)
    else:
        conn.capabilities = dict(current)

    db.commit()
    db.refresh(conn)
    return current

def is_capability_enabled(user_id: str, provider: str, capability_key: str, db: Session) -> bool:
    """
    Backend enforcement: checks if an individual capability is enabled for the user.
    Returns False if capability is turned off or unknown.
    """
    caps = get_user_capabilities(user_id, provider, db)
    return caps.get(capability_key, False)

def get_capability_metadata_for_user(user_id: str, provider: str, db: Session) -> List[Dict[str, Any]]:
    """
    Returns the full list of capabilities for a provider decorated with the user's current toggle state.
    """
    user_caps = get_user_capabilities(user_id, provider, db)
    caps_meta = SUPPORTED_CAPABILITIES.get(provider, [])
    result = []
    for c in caps_meta:
        result.append({
            "key": c["key"],
            "label": c["label"],
            "description": c["description"],
            "requiredScope": c["requiredScope"],
            "enabled": user_caps.get(c["key"], c["default"])
        })
    return result
