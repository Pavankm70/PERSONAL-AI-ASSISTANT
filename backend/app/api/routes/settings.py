from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get("")
def get_user_settings(user: User = Depends(get_current_user)):
    return {
        "fullName": user.full_name,
        "email": user.email,
        "timezone": user.timezone,
        "onboardingComplete": user.onboarding_complete,
        "autoConflictCheck": True,
        "requireActionConfirmation": True,
        "telemetrySharing": False
    }

@router.patch("")
def update_user_settings(
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if "fullName" in payload:
        user.full_name = payload["fullName"]
    if "timezone" in payload:
        user.timezone = payload["timezone"]
    if "onboardingComplete" in payload:
        user.onboarding_complete = bool(payload["onboardingComplete"])

    db.commit()
    db.refresh(user)
    return {
        "success": True,
        "user": {
            "fullName": user.full_name,
            "timezone": user.timezone,
            "onboardingComplete": user.onboarding_complete
        }
    }

@router.delete("/account")
async def delete_user_account(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Completely and permanently deletes the authenticated user's account and all
    associated data (OAuth tokens, files, chunks, conversations, plans, timetables).
    """
    from app.db.models import (
        OAuthAccount, IntegrationConnection, Document, DocumentChunk,
        TimetableEntry, Plan, PlanTask, Conversation, Message, ToolExecutionLog
    )
    from app.services.google_oauth.oauth_service import revoke_google_token

    # 1. Revoke any Google OAuth tokens
    accounts = db.query(OAuthAccount).filter(OAuthAccount.user_id == user.id).all()
    for acc in accounts:
        if acc.encrypted_access_token:
            await revoke_google_token(acc.encrypted_access_token)
        elif acc.encrypted_refresh_token:
            await revoke_google_token(acc.encrypted_refresh_token)

    # 2. Delete all user-owned records
    db.query(ToolExecutionLog).filter(ToolExecutionLog.user_id == user.id).delete(synchronize_session=False)
    db.query(DocumentChunk).filter(DocumentChunk.user_id == user.id).delete(synchronize_session=False)
    db.query(Document).filter(Document.user_id == user.id).delete(synchronize_session=False)
    db.query(TimetableEntry).filter(TimetableEntry.user_id == user.id).delete(synchronize_session=False)

    user_plans = db.query(Plan).filter(Plan.user_id == user.id).all()
    if user_plans:
        plan_ids = [p.id for p in user_plans]
        db.query(PlanTask).filter(PlanTask.plan_id.in_(plan_ids)).delete(synchronize_session=False)
        db.query(Plan).filter(Plan.user_id == user.id).delete(synchronize_session=False)

    user_convs = db.query(Conversation).filter(Conversation.user_id == user.id).all()
    if user_convs:
        conv_ids = [c.id for c in user_convs]
        db.query(Message).filter(Message.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.user_id == user.id).delete(synchronize_session=False)

    db.query(IntegrationConnection).filter(IntegrationConnection.user_id == user.id).delete(synchronize_session=False)
    db.query(OAuthAccount).filter(OAuthAccount.user_id == user.id).delete(synchronize_session=False)

    # 3. Delete user record
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()

    return {
        "success": True,
        "message": "User account and all associated data have been permanently deleted."
    }
