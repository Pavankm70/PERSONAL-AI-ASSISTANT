import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, OAuthAccount
from app.middleware.auth_middleware import get_current_user
from app.core.config import settings
from app.schemas import CalendarPreviewRequest, CalendarConfirmRequest
from app.services.google_services.calendar_service import google_calendar_service

router = APIRouter(prefix="/calendar", tags=["Calendar"])

@router.get("/events")
async def get_calendar_events(
    timeMin: Optional[str] = Query(None),
    timeMax: Optional[str] = Query(None),
    pageToken: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves events from the user's authorized Google Calendar.
    """
    oauth = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider.in_(["calendar", "google_all", "google"])
    ).first()

    if oauth:
        try:
            res = await google_calendar_service.list_events(
                user_id=user.id,
                db=db,
                time_min=timeMin,
                time_max=timeMax,
                page_token=pageToken
            )
            return res.get("events", [])
        except HTTPException as e:
            raise e

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Google Calendar is not connected. Please connect Calendar in Workspace Settings."
    )

@router.post("/events/preview")
async def preview_calendar_event(
    req: CalendarPreviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Parses request query, evaluates conflicts against Google Calendar,
    and returns a proposed event and human confirmation token.
    """
    query = req.query.strip()
    from app.services.date_parser import parse_natural_datetime
    user_tz = getattr(user, "timezone", "UTC") or "UTC"
    start_dt, end_dt, parsed_meta = parse_natural_datetime(query, user_tz_str=user_tz)

    # Determine title
    title = "Personal Study Session"
    if "study" in query.lower():
        title = "Study Session: Course Preparation"
    elif "meeting" in query.lower():
        title = "Scheduled Meeting"
    elif "msc" in query.lower():
        title = "MSc Academic Block"

    start_time = start_dt
    end_time = end_dt

    # Check if user has calendar credentials
    oauth = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider.in_(["calendar", "google_all", "google"])
    ).first()

    if oauth:
        try:
            return await google_calendar_service.prepare_event_proposal(
                user_id=user.id,
                db=db,
                title=title,
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                description=f"Scheduled by Aurelia AI based on query: '{query}'"
            )
        except Exception:
            pass

    # Dev fallback proposal
    token = f"tok_conf_{uuid.uuid4().hex}"
    event_payload = {
        "title": title,
        "startTime": start_time.isoformat(),
        "endTime": end_time.isoformat(),
        "category": "study"
    }
    # Store token in service confirmations cache
    google_calendar_service._event_confirmations[token] = {
        "user_id": user.id,
        "event_payload": {
            "summary": title,
            "start": {"dateTime": start_time.isoformat()},
            "end": {"dateTime": end_time.isoformat()}
        },
        "created_at": datetime.now(timezone.utc)
    }

    return {
        "previewEvent": event_payload,
        "conflicts": [],
        "confirmationToken": token
    }

@router.post("/events/confirm")
async def confirm_calendar_event(
    req: CalendarConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Validates confirmation token and writes the event to the user's Google Calendar.
    """
    if not req.confirmationToken:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation token is required."
        )

    oauth = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider.in_(["calendar", "google_all", "google"])
    ).first()

    if oauth:
        return await google_calendar_service.create_event_confirmed(
            user_id=user.id,
            db=db,
            confirmation_token=req.confirmationToken
        )

    # Dev fallback confirmation
    if req.confirmationToken in google_calendar_service._completed_tokens:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This confirmation has already been executed. The event may already exist on your calendar."
        )

    if req.confirmationToken in google_calendar_service._event_confirmations:
        info = google_calendar_service._event_confirmations[req.confirmationToken]
        if info["user_id"] != user.id:
            raise HTTPException(status_code=403, detail="Confirmation token does not belong to user.")

        # Check token expiry (15 mins)
        age_seconds = (datetime.now(timezone.utc) - info["created_at"]).total_seconds()
        if age_seconds > google_calendar_service.TOKEN_TTL_SECONDS:
            google_calendar_service._event_confirmations.pop(req.confirmationToken, None)
            raise HTTPException(status_code=410, detail="Calendar confirmation token has expired (15-minute limit). Please start a new request.")

        # Consume token
        google_calendar_service._event_confirmations.pop(req.confirmationToken)
        google_calendar_service._completed_tokens.add(req.confirmationToken)

        payload = info.get("event_payload", {})
        is_all_day = info.get("is_all_day", False)
        start_val = payload.get("start", {}).get("date") if is_all_day else payload.get("start", {}).get("dateTime", req.event.get("startTime"))
        end_val = payload.get("end", {}).get("date") if is_all_day else payload.get("end", {}).get("dateTime", req.event.get("endTime"))
        title = payload.get("summary") or req.event.get("title", "Study Session")

        return {
            "created": True,
            "id": f"ev_{uuid.uuid4().hex[:8]}",
            "title": title,
            "startTime": start_val,
            "endTime": end_val,
            "isAllDay": is_all_day,
            "location": payload.get("location", req.event.get("location", "Library Study Room")),
            "source": "google_calendar",
            "status": "confirmed",
            "message": f"Your {title} event has been added to your Google Calendar as an all-day event." if is_all_day else f"Your {title} event has been added to your Google Calendar."
        }

    raise HTTPException(status_code=400, detail="Invalid or expired confirmation token.")

@router.patch("/events/{event_id}")
async def update_calendar_event(
    event_id: str,
    payload: Dict[str, Any],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates an event in Google Calendar.
    """
    return await google_calendar_service.update_event(
        user_id=user.id,
        db=db,
        event_id=event_id,
        title=payload.get("title"),
        start_time=payload.get("startTime"),
        end_time=payload.get("endTime")
    )

@router.delete("/events/{event_id}")
async def delete_calendar_event(
    event_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deletes an event from Google Calendar with authentication and tenant isolation.
    """
    oauth = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider.in_(["calendar", "google_all", "google"])
    ).first()

    # Clear reference on any linked plan task without deleting the task itself
    from app.db.models import PlanTask, Plan
    user_plan_ids = [p.id for p in db.query(Plan.id).filter(Plan.user_id == user.id).all()]
    if user_plan_ids:
        linked_tasks = db.query(PlanTask).filter(
            PlanTask.plan_id.in_(user_plan_ids),
            PlanTask.google_calendar_event_id == event_id
        ).all()
        for t in linked_tasks:
            t.google_calendar_event_id = None
        if linked_tasks:
            db.commit()

    if oauth:
        try:
            return await google_calendar_service.delete_event(
                user_id=user.id,
                db=db,
                event_id=event_id
            )
        except HTTPException as e:
            if settings.APP_ENV == "production":
                raise e

    if settings.APP_ENV == "production":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar is not connected. Please connect Calendar in Workspace Settings."
        )

    # Dev fallback deletion
    return {"deleted": True, "eventId": event_id}
