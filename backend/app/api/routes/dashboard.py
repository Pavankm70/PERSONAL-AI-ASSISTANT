from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, Document, Plan, PlanTask, IntegrationConnection, OAuthAccount
from app.middleware.auth_middleware import get_current_user
from app.services.google_services.calendar_service import google_calendar_service
from app.services.google_services.gmail_service import google_gmail_service
from app.services.date_parser import get_user_today_bounds, get_user_current_date
from app.core.config import settings

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/overview")
async def get_dashboard_overview(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Retrieve user's actual uploaded documents
    docs = db.query(Document).filter(Document.user_id == user.id).order_by(Document.created_at.desc()).limit(5).all()
    recent_docs = [
        {
            "id": d.id,
            "filename": d.filename,
            "fileSize": d.file_size,
            "mimeType": d.mime_type,
            "chunkCount": d.chunk_count,
            "category": d.category,
            "status": d.status,
            "uploadedAt": d.created_at.isoformat()
        }
        for d in docs
    ]

    # 2. Check OAuth integrations status
    oauths = db.query(OAuthAccount).filter(OAuthAccount.user_id == user.id).all()
    providers_connected = {o.provider for o in oauths}

    integrations_status = {
        "gmail": "connected" if "gmail" in providers_connected or "google_all" in providers_connected else "not_connected",
        "calendar": "connected" if "calendar" in providers_connected or "google_all" in providers_connected else "not_connected",
        "drive": "connected" if "drive" in providers_connected or "google_all" in providers_connected else "not_connected",
        "rag": "connected"
    }

    # 3. Timezone-aware local day boundaries
    user_tz = user.timezone or "UTC"
    start_dt, end_dt, start_iso, end_iso = get_user_today_bounds(user_tz)
    local_today = get_user_current_date(user_tz)
    today_str = local_today.strftime("%Y-%m-%d")

    # 4. Retrieve Persisted Study Plan Tasks for Today
    today_tasks_query = db.query(PlanTask).join(Plan).filter(
        Plan.user_id == user.id,
        (PlanTask.scheduled_date == today_str) | (PlanTask.start_time.like(f"{today_str}%"))
    ).order_by(PlanTask.task_order, PlanTask.start_time, PlanTask.created_at).all()

    today_study_tasks = []
    task_synced_event_ids = set()
    for t in today_tasks_query:
        if t.google_calendar_event_id:
            task_synced_event_ids.add(t.google_calendar_event_id)
        has_time = bool(t.start_time or t.scheduled_time)
        today_study_tasks.append({
            "id": t.id,
            "taskId": t.id,
            "planId": t.plan_id,
            "planTitle": t.plan.title if t.plan else "Study Plan",
            "title": t.title,
            "durationMinutes": t.duration_minutes or 45,
            "priority": t.priority,
            "completed": bool(t.completed),
            "scheduledDate": t.scheduled_date or today_str,
            "scheduledTime": t.scheduled_time,
            "startTime": t.start_time,
            "endTime": t.end_time,
            "isUnscheduled": not has_time,
            "googleCalendarEventId": t.google_calendar_event_id,
            "isSynced": bool(t.google_calendar_event_id)
        })

    # 5. Retrieve REAL Calendar agenda for today if connected
    today_agenda: List[Dict[str, Any]] = []
    calendar_error = None
    if integrations_status["calendar"] == "connected":
        try:
            cal_res = await google_calendar_service.list_events(
                user_id=user.id,
                db=db,
                time_min=start_iso,
                time_max=end_iso,
                max_results=20
            )
            raw_events = cal_res.get("events", [])
            for ev in raw_events:
                ev_id = ev.get("id")
                # Deduplication: If this calendar event is already linked to a study task, mark it as linked
                is_linked_study = ev_id in task_synced_event_ids
                today_agenda.append({
                    "id": ev_id,
                    "title": ev.get("title", "(No Title)"),
                    "startTime": ev.get("startTime"),
                    "endTime": ev.get("endTime"),
                    "location": ev.get("location", ""),
                    "source": "study_plan" if is_linked_study else "google_calendar",
                    "eventType": "study_plan" if is_linked_study else "google_calendar",
                    "isSynced": True,
                    "isAllDay": bool(ev.get("isAllDay"))
                })
        except Exception as e:
            calendar_error = str(e)

    # Merge unlinked study tasks into today's agenda so Overview displays all commitments
    for st in today_study_tasks:
        if not st.get("googleCalendarEventId") or st.get("googleCalendarEventId") not in {a["id"] for a in today_agenda}:
            # Build start/end strings if available
            st_start = st.get("startTime") or (f"{today_str}T09:00:00" if st.get("scheduledTime") else None)
            st_end = st.get("endTime")
            today_agenda.append({
                "id": f"task_{st['id']}",
                "taskId": st["id"],
                "planId": st["planId"],
                "title": st["title"],
                "startTime": st_start,
                "endTime": st_end,
                "location": st["planTitle"],
                "source": "study_plan",
                "eventType": "study_plan",
                "completed": st["completed"],
                "durationMinutes": st["durationMinutes"],
                "isSynced": st["isSynced"],
                "isUnscheduled": st["isUnscheduled"],
                "isAllDay": False
            })

    # Sort agenda chronologically, placing unscheduled tasks at the bottom
    def sort_key(item):
        st = item.get("startTime")
        return (0 if st else 1, st or "")
    today_agenda.sort(key=sort_key)

    # 4. Retrieve REAL Gmail unread/important highlights if connected
    important_emails: List[Dict[str, Any]] = []
    gmail_error = None
    if integrations_status["gmail"] == "connected":
        try:
            g_res = await google_gmail_service.list_messages(
                user_id=user.id,
                db=db,
                query="is:unread",
                max_results=5
            )
            raw_msgs = g_res.get("messages", [])
            for m in raw_msgs:
                important_emails.append({
                    "id": m.get("id"),
                    "threadId": m.get("threadId"),
                    "fromName": m.get("fromName", "Sender"),
                    "fromEmail": m.get("fromEmail", ""),
                    "subject": m.get("subject", "(No Subject)"),
                    "snippet": m.get("snippet", ""),
                    "date": m.get("date"),
                    "isUnread": m.get("isUnread", True),
                    "isImportant": m.get("isImportant", False),
                    "aiPriority": "high" if m.get("isImportant") else "normal"
                })
        except Exception as e:
            gmail_error = str(e)

    # 5. System counts and plans
    total_docs_count = db.query(Document).filter(Document.user_id == user.id).count()
    plans_count = db.query(Plan).filter(Plan.user_id == user.id).count()

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
        "todayDate": today_str,
        "todayAgenda": today_agenda,
        "todayStudyTasks": today_study_tasks,
        "calendarError": calendar_error,
        "importantEmails": important_emails,
        "gmailError": gmail_error,
        "recentDocuments": recent_docs,
        "pendingActions": [],
        "integrationsStatus": integrations_status,
        "systemStats": {
            "totalDocuments": total_docs_count,
            "upcomingEventsCount": len(today_agenda),
            "todayTasksCount": len(today_study_tasks),
            "todayCompletedTasksCount": sum(1 for t in today_study_tasks if t.get("completed")),
            "unreadImportantCount": len(important_emails),
            "activePlansCount": plans_count
        }
    }
