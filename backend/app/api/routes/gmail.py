from typing import Optional, List
from email.utils import parsedate_to_datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, OAuthAccount
from app.middleware.auth_middleware import get_current_user
from app.core.config import settings
from app.schemas import (
    GmailSummarizeRequest,
    GmailDraftRequest,
    GmailPrepareSendRequest,
    GmailConfirmSendRequest
)
from app.services.google_services.gmail_service import google_gmail_service
from app.services.date_parser import get_user_current_date, get_user_tz

router = APIRouter(prefix="/gmail", tags=["Gmail"])

@router.get("/messages")
async def get_gmail_messages(
    filter: str = Query("all"),
    query: Optional[str] = Query(None),
    max_results: int = Query(20, le=50),
    page_token: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves and searches email messages from the authenticated user's authorized Gmail mailbox.
    Enforces timezone-accurate boundaries for 'today', 'unread', 'read', 'starred', and other filters.
    """
    user_tz_obj = get_user_tz(user.timezone)
    user_today_date = get_user_current_date(user.timezone)

    # Build query filter string
    q_parts = []
    if filter == "unread":
        q_parts.append("is:unread")
    elif filter == "read":
        q_parts.append("is:read")
    elif filter == "starred":
        q_parts.append("is:starred")
    elif filter == "sent":
        q_parts.append("in:sent")
    elif filter == "important":
        q_parts.append("is:important")
    elif filter in ("attachment", "attachments"):
        q_parts.append("has:attachment")
    elif filter == "today":
        # Anchor query using user's local date
        q_parts.append(f"after:{user_today_date.strftime('%Y/%m/%d')}")
    elif filter == "24h":
        q_parts.append("newer_than:1d")
    elif filter == "week":
        q_parts.append("newer_than:7d")

    if query:
        q_parts.append(query)

    search_query = " ".join(q_parts) if q_parts else None

    # Check if user has an authorized connection
    oauth = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider.in_(["gmail", "google_all", "google"])
    ).first()

    if oauth:
        res = await google_gmail_service.list_messages(
            user_id=user.id,
            db=db,
            query=search_query,
            max_results=max_results,
            page_token=page_token
        )
        msgs = res.get("messages", [])

        # Enforce strict local-date boundaries for 'today'
        if filter == "today":
            strictly_today = []
            for m in msgs:
                raw_date = m.get("date")
                if not raw_date:
                    continue
                try:
                    dt = parsedate_to_datetime(raw_date).astimezone(user_tz_obj)
                    if dt.date() == user_today_date:
                        strictly_today.append(m)
                except Exception:
                    if user_today_date.strftime("%Y-%m-%d") in raw_date:
                        strictly_today.append(m)
            return strictly_today

        return msgs

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Gmail account is not connected. Please connect Gmail in Workspace Settings."
    )

@router.get("/messages/{message_id}")
async def get_single_message(
    message_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves full content and metadata for a specific email message.
    """
    msg = await google_gmail_service.get_message(
        user_id=user.id,
        db=db,
        message_id=message_id,
        format="full"
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Email message not found in user's mailbox.")
    return msg

@router.post("/draft")
async def create_email_draft(
    req: GmailDraftRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Creates an email draft in the authenticated user's Gmail account.
    """
    return await google_gmail_service.create_draft(
        user_id=user.id,
        db=db,
        to=req.to,
        subject=req.subject,
        body=req.body
    )

@router.post("/prepare-send")
def prepare_email_send(
    req: GmailPrepareSendRequest,
    user: User = Depends(get_current_user)
):
    """
    Constructs an explicit send proposal showing recipient, subject, and body preview.
    Returns a human confirmation token. No email is sent until this token is confirmed.
    """
    return google_gmail_service.prepare_send_confirmation(
        user_id=user.id,
        to=req.to,
        subject=req.subject,
        body=req.body
    )

@router.post("/confirm-send")
async def confirm_email_send(
    req: GmailConfirmSendRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Sends the email via Gmail API ONLY after validating the explicit user confirmation token.
    """
    return await google_gmail_service.send_email_confirmed(
        user_id=user.id,
        db=db,
        confirmation_token=req.confirmationToken
    )

@router.post("/summarize")
async def summarize_gmail_thread(
    req: GmailSummarizeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    msg = await google_gmail_service.get_message(user_id=user.id, db=db, message_id=req.messageId)
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email message not found in user's mailbox."
        )
    snippet = msg.get("snippet", "")
    body = msg.get("body") or snippet

    if settings.GEMINI_API_KEY:
        from app.services.gemini_client import call_gemini_api
        from app.prompts.gmail import GMAIL_SUMMARY_PROMPT
        prompt = (
            f"Email Subject: {msg.get('subject')}\n"
            f"From: {msg.get('fromName')} <{msg.get('fromEmail')}>\n"
            f"Date: {msg.get('date')}\n"
            f"Content:\n{body[:2500]}\n\n"
            "INSTRUCTIONS:\n"
            "Summarize this email. Extract key points and any action items.\n"
            "Return ONLY valid JSON with 'summary' (str) and 'actionItems' (list of strings)."
        )
        gemini_res = await call_gemini_api(prompt, GMAIL_SUMMARY_PROMPT)
        if gemini_res.success and gemini_res.text:
            import json
            try:
                clean = gemini_res.text.strip()
                if clean.startswith("```json"):
                    clean = clean[7:]
                if clean.startswith("```"):
                    clean = clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                parsed = json.loads(clean.strip())
                if "summary" in parsed:
                    return {
                        "summary": parsed["summary"],
                        "actionItems": parsed.get("actionItems", [])
                    }
            except Exception:
                pass
            return {"summary": gemini_res.text, "actionItems": []}

    return {
        "summary": f"Summary for '{msg.get('subject', 'Email')}': {snippet}",
        "actionItems": []
    }
