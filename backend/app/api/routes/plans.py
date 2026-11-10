from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, Plan, PlanTask
from app.middleware.auth_middleware import get_current_user
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta, date as date_type
import zoneinfo

from app.services.study_plan_generator import (
    generate_study_plan_roadmap,
    calculate_plan_dates,
    parse_plan_duration
)
from app.services.google_services.calendar_service import google_calendar_service

router = APIRouter(prefix="/plans", tags=["Personal Plans"])

def format_task(t: PlanTask) -> dict:
    return {
        "id": t.id,
        "planId": t.plan_id,
        "title": t.title,
        "durationMinutes": t.duration_minutes,
        "priority": t.priority,
        "completed": bool(t.completed),
        "scheduledTime": t.scheduled_time,
        "scheduledDate": t.scheduled_date,
        "startTime": t.start_time,
        "endTime": t.end_time,
        "timezone": t.timezone,
        "googleCalendarEventId": t.google_calendar_event_id,
        "monthNumber": t.month_number,
        "weekNumber": t.week_number,
        "dayNumber": t.day_number,
        "taskOrder": t.task_order or 0,
        "taskType": t.task_type or "daily",
        "dayLabel": t.day_label,
        "weekLabel": t.week_label,
        "monthLabel": t.month_label,
        "milestoneGroup": t.milestone_group,
        "createdAt": t.created_at.isoformat() if getattr(t, "created_at", None) else None,
        "updatedAt": t.updated_at.isoformat() if getattr(t, "updated_at", None) else None,
    }

def format_plan(p: Plan, tasks=None) -> dict:
    if tasks is None:
        tasks = p.tasks or []
    return {
        "id": p.id,
        "title": p.title,
        "period": p.period or "Sprint",
        "subject": p.subject,
        "learningGoal": p.learning_goal,
        "startDate": p.start_date,
        "endDate": p.end_date,
        "durationDays": p.duration_days,
        "dailyHoursTarget": p.daily_hours_target or 2.0,
        "preferredStudyDays": p.preferred_study_days or [],
        "generationStatus": p.generation_status or "complete",
        "goals": p.goals or [],
        "suggestedStudyBlocks": p.suggested_study_blocks or [],
        "tasks": [format_task(t) for t in tasks],
        "createdAt": p.created_at.isoformat() if getattr(p, "created_at", None) else None,
        "updatedAt": p.updated_at.isoformat() if getattr(p, "updated_at", None) else None
    }

@router.get("")
def get_plans(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve all saved plans for the authenticated user.
    Strictly isolated: returns [] if the user has no saved plans.
    Never returns hardcoded, mock, or auto-generated starter plans.
    """
    plans = (
        db.query(Plan)
        .filter(Plan.user_id == user.id)
        .order_by(Plan.created_at.desc())
        .all()
    )
    return [format_plan(p) for p in plans]

@router.post("")
async def create_plan(
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Creates a new study plan. Supports durations from 1 day up to 6 months.
    If no explicit tasks are provided, automatically generates a full-duration
    learning roadmap organized by month, week, and day.
    """
    title = (payload.get("title") or "").strip()
    period = (payload.get("period") or "").strip()
    subject = (payload.get("subject") or "").strip()
    learning_goal = (payload.get("learningGoal") or payload.get("goal") or "").strip()
    start_date_str = payload.get("startDate")
    duration_str = payload.get("duration") or period
    duration_days = payload.get("durationDays")
    daily_hours = float(payload.get("dailyHours") or payload.get("dailyHoursTarget") or 2.0)
    preferred_days = payload.get("preferredStudyDays") or []
    initial_tasks = payload.get("tasks", [])
    goals = payload.get("goals") or []
    suggested_blocks = payload.get("suggestedStudyBlocks") or []

    # If subject was not explicitly given, extract from title
    if not subject:
        subject = title.replace("Study Plan", "").replace("Roadmap", "").replace("Sprint", "").strip() or "Academic"
    if not title:
        title = f"{duration_str or 'Study'} {subject} Plan".strip()

    user_tz_str = getattr(user, "timezone", None) or "UTC"
    start_d, end_d, calc_days = calculate_plan_dates(
        start_date_str=start_date_str,
        duration_text=duration_str,
        duration_days=duration_days,
        user_tz_str=user_tz_str
    )

    plan = Plan(
        user_id=user.id,
        title=title,
        period=period or f"{calc_days} Days",
        subject=subject,
        learning_goal=learning_goal or f"Master {subject} in {calc_days} days",
        start_date=start_d.isoformat(),
        end_date=end_d.isoformat(),
        duration_days=calc_days,
        daily_hours_target=daily_hours,
        preferred_study_days=preferred_days,
        generation_status="complete",
        goals=goals,
        suggested_study_blocks=suggested_blocks
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    created_tasks = []

    # Case A: Explicit tasks were passed (e.g. tests or custom imports)
    if initial_tasks and isinstance(initial_tasks, list) and len(initial_tasks) > 0:
        for idx, t in enumerate(initial_tasks):
            if isinstance(t, dict):
                task_title = (t.get("title") or "Task").strip()
                pt = PlanTask(
                    plan_id=plan.id,
                    title=task_title,
                    duration_minutes=int(t.get("durationMinutes", int(daily_hours * 60))),
                    priority=str(t.get("priority", "high")),
                    completed=bool(t.get("completed", False)),
                    scheduled_time=t.get("scheduledTime"),
                    scheduled_date=t.get("scheduledDate"),
                    start_time=t.get("startTime"),
                    end_time=t.get("endTime"),
                    timezone=t.get("timezone", user_tz_str),
                    google_calendar_event_id=t.get("googleCalendarEventId"),
                    month_number=t.get("monthNumber", 1),
                    week_number=t.get("weekNumber", 1),
                    day_number=t.get("dayNumber", idx + 1),
                    task_order=t.get("taskOrder", idx + 1),
                    task_type=str(t.get("taskType", "daily")),
                    day_label=t.get("dayLabel", f"Day {idx + 1}"),
                    week_label=t.get("weekLabel", "Week 1"),
                    month_label=t.get("monthLabel", "Month 1"),
                    milestone_group=t.get("milestoneGroup")
                )
                db.add(pt)
                created_tasks.append(pt)
        db.commit()
        for pt in created_tasks:
            db.refresh(pt)

    # Case B: No tasks given -> generate full-duration roadmap automatically!
    else:
        roadmap_res = await generate_study_plan_roadmap(
            subject=subject,
            learning_goal=learning_goal,
            duration_text=duration_str,
            duration_days=calc_days,
            start_date_str=start_date_str,
            daily_hours=daily_hours,
            preferred_days=preferred_days,
            user_tz_str=user_tz_str
        )

        # Update plan title and goals if auto-generated
        if not goals and roadmap_res.get("goals"):
            plan.goals = roadmap_res["goals"]
        if not payload.get("title") and roadmap_res.get("title"):
            plan.title = roadmap_res["title"]

        for t in roadmap_res.get("tasks", []):
            pt = PlanTask(
                plan_id=plan.id,
                title=t["title"],
                duration_minutes=t.get("durationMinutes", int(daily_hours * 60)),
                priority=t.get("priority", "high"),
                completed=False,
                scheduled_date=t.get("scheduledDate"),
                start_time=t.get("startTime"),
                end_time=t.get("endTime"),
                timezone=t.get("timezone", user_tz_str),
                month_number=t.get("monthNumber"),
                week_number=t.get("weekNumber"),
                day_number=t.get("dayNumber"),
                task_order=t.get("taskOrder", 0),
                task_type=t.get("taskType", "daily"),
                day_label=t.get("dayLabel"),
                week_label=t.get("weekLabel"),
                month_label=t.get("monthLabel"),
                milestone_group=t.get("milestoneGroup")
            )
            db.add(pt)
            created_tasks.append(pt)

        db.commit()
        db.refresh(plan)
        for pt in created_tasks:
            db.refresh(pt)

    return format_plan(plan, created_tasks)

@router.get("/{plan_id}")
def get_plan(
    plan_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves a single study plan and its tasks for the authenticated user.
    """
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    return format_plan(plan)

@router.patch("/{plan_id}")
def update_plan(
    plan_id: str,
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates plan metadata (title, period, goals, suggested study blocks)
    or bulk-updates tasks.
    """
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    if "title" in payload:
        plan.title = payload["title"]
    if "period" in payload:
        plan.period = payload["period"]
    if "goals" in payload:
        plan.goals = payload["goals"]
    if "suggestedStudyBlocks" in payload:
        plan.suggested_study_blocks = payload["suggestedStudyBlocks"]

    if "tasks" in payload and isinstance(payload["tasks"], list):
        # Replace all tasks with new task set
        db.query(PlanTask).filter(PlanTask.plan_id == plan.id).delete()
        for t in payload["tasks"]:
            if isinstance(t, dict):
                pt = PlanTask(
                    plan_id=plan.id,
                    title=t.get("title", ""),
                    duration_minutes=int(t.get("durationMinutes", 45)),
                    priority=t.get("priority", "high"),
                    completed=bool(t.get("completed", False)),
                    scheduled_time=t.get("scheduledTime"),
                    scheduled_date=t.get("scheduledDate"),
                    start_time=t.get("startTime"),
                    end_time=t.get("endTime"),
                    timezone=t.get("timezone"),
                    google_calendar_event_id=t.get("googleCalendarEventId")
                )
                db.add(pt)

    db.commit()
    db.refresh(plan)
    return format_plan(plan)

@router.post("/generate-proposal")
async def generate_plan_proposal(
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generates a full-duration roadmap and daily schedule preview WITHOUT saving to database.
    Allows user to review, edit dates, times, durations, rest days, and batch shift times
    prior to explicit persistence.
    """
    subject = payload.get("subject", "General Academic Study")
    period = payload.get("period", "30 days")
    daily_hours = float(payload.get("daily_hours_target", payload.get("dailyHoursTarget", 2.0)))
    learning_goal = payload.get("learning_goal", payload.get("learningGoal", f"Master {subject} in {period}"))
    user_tz_str = getattr(user, "timezone", "UTC") or "UTC"
    preferred_days = payload.get("preferred_study_days")

    calc_days = parse_plan_duration(period)
    start_date_str = payload.get("start_date") or payload.get("startDate")

    roadmap_res = await generate_study_plan_roadmap(
        subject=subject,
        learning_goal=learning_goal,
        duration_text=period,
        duration_days=calc_days,
        start_date_str=start_date_str,
        daily_hours=daily_hours,
        preferred_days=preferred_days,
        user_tz_str=user_tz_str
    )

    return roadmap_res

@router.delete("/{plan_id}")
async def delete_plan(
    plan_id: str,
    delete_google_events: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Permanently deletes a study plan and cascades deletion to associated tasks.
    If delete_google_events is True, also deletes linked events from Google Calendar.
    """
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    tasks = db.query(PlanTask).filter(PlanTask.plan_id == plan.id).all()
    deleted_calendar_events = 0
    if delete_google_events:
        for t in tasks:
            if t.google_calendar_event_id:
                try:
                    await google_calendar_service.delete_event(
                        user_id=user.id,
                        db=db,
                        event_id=t.google_calendar_event_id
                    )
                    deleted_calendar_events += 1
                except Exception:
                    pass

    db.query(PlanTask).filter(PlanTask.plan_id == plan.id).delete()
    db.delete(plan)
    db.commit()
    return {
        "success": True,
        "deletedPlanId": plan_id,
        "deletedCalendarEvents": deleted_calendar_events
    }

@router.post("/reconcile-orphans")
async def reconcile_orphaned_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Scans the user's tasks and Google Calendar for orphaned study blocks.
    Identifies tasks whose linked Google Calendar events were manually deleted,
    and clears the broken reference while leaving genuine meetings and quizzes untouched.
    """
    tasks = db.query(PlanTask).join(Plan).filter(
        Plan.user_id == user.id,
        PlanTask.google_calendar_event_id.isnot(None)
    ).all()

    reconciled = 0
    try:
        events_res = await google_calendar_service.list_events(user_id=user.id, db=db, max_results=250)
        live_event_ids = {e["id"] for e in events_res.get("events", [])}
        for t in tasks:
            if t.google_calendar_event_id not in live_event_ids:
                t.google_calendar_event_id = None
                reconciled += 1
        db.commit()
    except Exception:
        pass

    return {"reconciledCount": reconciled}

# --- Hierarchical Roadmap Endpoints ---

@router.get("/{plan_id}/roadmap")
def get_plan_roadmap(
    plan_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns the complete hierarchical learning roadmap (Months -> Weeks -> Days -> Tasks)
    for a study plan, derived strictly from persisted records.
    Calculates accurate progress and workload metrics at each level.
    """
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    tasks = (
        db.query(PlanTask)
        .filter(PlanTask.plan_id == plan.id)
        .order_by(PlanTask.task_order, PlanTask.scheduled_date, PlanTask.created_at)
        .all()
    )

    months_map = {}
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t.completed)
    total_minutes = sum(t.duration_minutes or 0 for t in tasks)
    completed_minutes = sum(t.duration_minutes or 0 for t in tasks if t.completed)

    for t in tasks:
        m_num = t.month_number or 1
        w_num = t.week_number or 1
        d_num = t.day_number or 1

        if m_num not in months_map:
            months_map[m_num] = {
                "monthNumber": m_num,
                "monthLabel": t.month_label or f"Month {m_num}",
                "milestone": t.milestone_group or f"Month {m_num} Milestone",
                "weeks_map": {},
                "tasks": []
            }

        m_data = months_map[m_num]
        m_data["tasks"].append(t)

        if w_num not in m_data["weeks_map"]:
            m_data["weeks_map"][w_num] = {
                "weekNumber": w_num,
                "weekLabel": t.week_label or f"Week {w_num}",
                "milestone": t.milestone_group or f"Week {w_num} Target",
                "days_map": {},
                "tasks": []
            }

        w_data = m_data["weeks_map"][w_num]
        w_data["tasks"].append(t)

        day_key = t.scheduled_date or f"Day_{d_num}"
        if day_key not in w_data["days_map"]:
            w_data["days_map"][day_key] = {
                "dayNumber": d_num,
                "date": t.scheduled_date,
                "dayLabel": t.day_label or f"Day {d_num}",
                "isRestDay": False,
                "tasks": []
            }
        w_data["days_map"][day_key]["tasks"].append(format_task(t))

    months_list = []
    for m_num in sorted(months_map.keys()):
        m_info = months_map[m_num]
        m_tasks = m_info["tasks"]
        m_comp = sum(1 for t in m_tasks if t.completed)
        m_tot_mins = sum(t.duration_minutes or 0 for t in m_tasks)
        m_comp_mins = sum(t.duration_minutes or 0 for t in m_tasks if t.completed)

        weeks_list = []
        for w_num in sorted(m_info["weeks_map"].keys()):
            w_info = m_info["weeks_map"][w_num]
            w_tasks = w_info["tasks"]
            w_comp = sum(1 for t in w_tasks if t.completed)
            w_tot_mins = sum(t.duration_minutes or 0 for t in w_tasks)
            w_comp_mins = sum(t.duration_minutes or 0 for t in w_tasks if t.completed)

            days_list = []
            for d_key in sorted(w_info["days_map"].keys()):
                d_info = w_info["days_map"][d_key]
                d_tasks = d_info["tasks"]
                d_tot_mins = sum(t.get("durationMinutes", 0) for t in d_tasks)
                days_list.append({
                    "dayNumber": d_info["dayNumber"],
                    "date": d_info["date"],
                    "dayLabel": d_info["dayLabel"],
                    "isRestDay": False,
                    "totalPlannedMinutes": d_tot_mins,
                    "tasks": d_tasks
                })

            w_dates = [d["date"] for d in days_list if d.get("date")]
            weeks_list.append({
                "weekNumber": w_num,
                "weekLabel": w_info["weekLabel"],
                "startDate": w_dates[0] if w_dates else None,
                "endDate": w_dates[-1] if w_dates else None,
                "goal": f"Complete {w_info['weekLabel']} milestones",
                "milestone": w_info["milestone"],
                "totalTasks": len(w_tasks),
                "completedTasks": w_comp,
                "plannedHours": round(w_tot_mins / 60.0, 1),
                "completedHours": round(w_comp_mins / 60.0, 1),
                "progress": round((w_comp / len(w_tasks)) * 100) if w_tasks else 0,
                "days": days_list
            })

        m_dates = [w["startDate"] for w in weeks_list if w.get("startDate")]
        m_end_dates = [w["endDate"] for w in weeks_list if w.get("endDate")]
        months_list.append({
            "monthNumber": m_num,
            "monthLabel": m_info["monthLabel"],
            "startDate": m_dates[0] if m_dates else None,
            "endDate": m_end_dates[-1] if m_end_dates else None,
            "objectives": [f"Master core competencies for {m_info['monthLabel']}", f"Complete {m_info['milestone']}"],
            "milestone": m_info["milestone"],
            "totalTasks": len(m_tasks),
            "completedTasks": m_comp,
            "plannedHours": round(m_tot_mins / 60.0, 1),
            "completedHours": round(m_comp_mins / 60.0, 1),
            "progress": round((m_comp / len(m_tasks)) * 100) if m_tasks else 0,
            "weeks": weeks_list
        })

    summary = {
        "totalTasks": total_tasks,
        "completedTasks": completed_tasks,
        "pendingTasks": total_tasks - completed_tasks,
        "completionPercentage": round((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0,
        "plannedStudyHours": round(total_minutes / 60.0, 1),
        "completedStudyHours": round(completed_minutes / 60.0, 1),
        "totalMonths": len(months_list),
        "totalWeeks": sum(len(m["weeks"]) for m in months_list),
        "totalDays": plan.duration_days or sum(len(w["days"]) for m in months_list for w in m["weeks"])
    }

    return {
        "planId": plan.id,
        "title": plan.title,
        "period": plan.period,
        "subject": plan.subject,
        "learningGoal": plan.learning_goal,
        "startDate": plan.start_date,
        "endDate": plan.end_date,
        "durationDays": plan.duration_days,
        "totalDays": summary["totalDays"],
        "totalTasks": summary["totalTasks"],
        "completedTasks": summary["completedTasks"],
        "dailyHoursTarget": plan.daily_hours_target or 2.0,
        "summary": summary,
        "months": months_list
    }

@router.post("/{plan_id}/generate-roadmap")
async def generate_plan_roadmap_endpoint(
    plan_id: str,
    payload: dict = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generates (or regenerates) a full-duration learning roadmap for an existing plan.
    Preserves completed tasks and existing Google Calendar links.
    """
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    if payload is None:
        payload = {}
    replace = bool(payload.get("replace", True))
    subject = payload.get("subject") or plan.subject or plan.title
    duration_str = payload.get("duration") or plan.period
    daily_hours = float(payload.get("dailyHours") or plan.daily_hours_target or 2.0)
    user_tz_str = getattr(user, "timezone", None) or "UTC"

    plan.generation_status = "generating"
    db.commit()

    try:
        roadmap_res = await generate_study_plan_roadmap(
            subject=subject,
            learning_goal=plan.learning_goal,
            duration_text=duration_str,
            duration_days=plan.duration_days,
            start_date_str=plan.start_date,
            daily_hours=daily_hours,
            preferred_days=plan.preferred_study_days,
            user_tz_str=user_tz_str
        )

        if replace:
            # Delete uncompleted tasks that have no external Google Calendar event linked
            db.query(PlanTask).filter(
                PlanTask.plan_id == plan.id,
                PlanTask.completed == False,
                PlanTask.google_calendar_event_id == None
            ).delete()

        created = []
        for t in roadmap_res.get("tasks", []):
            pt = PlanTask(
                plan_id=plan.id,
                title=t["title"],
                duration_minutes=t.get("durationMinutes", int(daily_hours * 60)),
                priority=t.get("priority", "high"),
                completed=False,
                scheduled_date=t.get("scheduledDate"),
                start_time=t.get("startTime"),
                end_time=t.get("endTime"),
                timezone=t.get("timezone", user_tz_str),
                month_number=t.get("monthNumber"),
                week_number=t.get("weekNumber"),
                day_number=t.get("dayNumber"),
                task_order=t.get("taskOrder", 0),
                task_type=t.get("taskType", "daily"),
                day_label=t.get("dayLabel"),
                week_label=t.get("weekLabel"),
                month_label=t.get("monthLabel"),
                milestone_group=t.get("milestoneGroup")
            )
            db.add(pt)
            created.append(pt)

        plan.generation_status = "complete"
        plan.duration_days = roadmap_res.get("durationDays", plan.duration_days)
        plan.start_date = roadmap_res.get("startDate", plan.start_date)
        plan.end_date = roadmap_res.get("endDate", plan.end_date)
        if roadmap_res.get("goals") and not plan.goals:
            plan.goals = roadmap_res["goals"]
        db.commit()
        db.refresh(plan)
        return format_plan(plan)
    except Exception as exc:
        plan.generation_status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Roadmap generation failed: {str(exc)}")

# --- Granular Task Operations ---

@router.post("/{plan_id}/tasks")
def add_task_to_plan(
    plan_id: str,
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Adds a single task to an existing plan.
    """
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    task = PlanTask(
        plan_id=plan.id,
        title=(payload.get("title") or "New Task").strip(),
        duration_minutes=int(payload.get("durationMinutes", 45)),
        priority=str(payload.get("priority", "high")),
        completed=bool(payload.get("completed", False)),
        scheduled_time=payload.get("scheduledTime"),
        scheduled_date=payload.get("scheduledDate"),
        start_time=payload.get("startTime"),
        end_time=payload.get("endTime"),
        timezone=payload.get("timezone", getattr(user, "timezone", None) or "UTC"),
        google_calendar_event_id=payload.get("googleCalendarEventId"),
        month_number=payload.get("monthNumber"),
        week_number=payload.get("weekNumber"),
        day_number=payload.get("dayNumber"),
        task_order=payload.get("taskOrder", 0),
        task_type=str(payload.get("taskType", "daily")),
        day_label=payload.get("dayLabel"),
        week_label=payload.get("weekLabel"),
        month_label=payload.get("monthLabel"),
        milestone_group=payload.get("milestoneGroup")
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return format_task(task)

@router.patch("/{plan_id}/tasks/{task_id}")
def update_task_in_plan(
    plan_id: str,
    task_id: str,
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates details, completion, or scheduling of an individual task.
    """
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    task = db.query(PlanTask).filter(PlanTask.id == task_id, PlanTask.plan_id == plan.id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    if "title" in payload:
        task.title = str(payload["title"]).strip()
    if "durationMinutes" in payload:
        task.duration_minutes = int(payload["durationMinutes"])
    if "priority" in payload:
        task.priority = str(payload["priority"])
    if "completed" in payload:
        task.completed = bool(payload["completed"])
    if "scheduledTime" in payload:
        task.scheduled_time = payload["scheduledTime"]
    if "scheduledDate" in payload:
        task.scheduled_date = payload["scheduledDate"]
    if "startTime" in payload:
        task.start_time = payload["startTime"]
    if "endTime" in payload:
        task.end_time = payload["endTime"]
    if "timezone" in payload:
        task.timezone = payload["timezone"]
    if "googleCalendarEventId" in payload:
        task.google_calendar_event_id = payload["googleCalendarEventId"]
    if "monthNumber" in payload:
        task.month_number = payload["monthNumber"]
    if "weekNumber" in payload:
        task.week_number = payload["weekNumber"]
    if "dayNumber" in payload:
        task.day_number = payload["dayNumber"]
    if "taskType" in payload:
        task.task_type = str(payload["taskType"])
    if "dayLabel" in payload:
        task.day_label = payload["dayLabel"]
    if "weekLabel" in payload:
        task.week_label = payload["weekLabel"]
    if "monthLabel" in payload:
        task.month_label = payload["monthLabel"]
    if "milestoneGroup" in payload:
        task.milestone_group = payload["milestoneGroup"]

    db.commit()
    db.refresh(task)
    return format_task(task)

@router.delete("/{plan_id}/tasks/{task_id}")
def delete_task_from_plan(
    plan_id: str,
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deletes an individual task from a plan.
    """
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    task = db.query(PlanTask).filter(PlanTask.id == task_id, PlanTask.plan_id == plan.id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    db.delete(task)
    db.commit()
    return {"success": True, "deletedTaskId": task_id}

@router.post("/{plan_id}/propose-slots")
async def propose_smart_study_slots(
    plan_id: str,
    payload: dict = None,
    month: Optional[int] = Query(None),
    week: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generates a realistic proposed study schedule from saved plan tasks across the full
    plan duration (from 1 day up to 6 months).
    Uses actual ISO dates starting from task scheduled dates or tomorrow.
    Checks Google Calendar for conflicts over the full duration when Calendar is connected.
    Never creates Calendar events — proposal only.
    Supports optional month or week filtering for paginated inspection.
    """
    from app.db.models import OAuthAccount
    from app.services.google_services.calendar_service import google_calendar_service
    from datetime import datetime, timezone, timedelta, date as date_type
    import zoneinfo

    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    if payload is None:
        payload = {}
    preferred_start_hour = int(payload.get("preferredStartHour", 9))   # default 9 AM
    preferred_end_hour   = int(payload.get("preferredEndHour", 20))     # default 8 PM
    skip_weekends        = bool(payload.get("skipWeekends", False))
    filter_month = payload.get("month", month)
    filter_week = payload.get("week", week)

    user_tz_str = getattr(user, "timezone", None) or "UTC"
    try:
        user_tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        user_tz = zoneinfo.ZoneInfo("UTC")

    # Query pending tasks; fall back to all tasks if all complete
    query = db.query(PlanTask).filter(PlanTask.plan_id == plan.id, PlanTask.completed == False)
    if filter_month:
        query = query.filter(PlanTask.month_number == int(filter_month))
    if filter_week:
        query = query.filter(PlanTask.week_number == int(filter_week))

    tasks = query.order_by(PlanTask.task_order, PlanTask.scheduled_date, PlanTask.created_at).all()
    if not tasks:
        # Fallback to all tasks matching filters
        fallback_q = db.query(PlanTask).filter(PlanTask.plan_id == plan.id)
        if filter_month:
            fallback_q = fallback_q.filter(PlanTask.month_number == int(filter_month))
        if filter_week:
            fallback_q = fallback_q.filter(PlanTask.week_number == int(filter_week))
        tasks = fallback_q.order_by(PlanTask.task_order, PlanTask.scheduled_date, PlanTask.created_at).all()

    if not tasks:
        return {
            "planId": plan.id,
            "calendarConnected": False,
            "calendarNote": "No tasks found in this plan to schedule.",
            "proposedStudyBlocks": [],
            "reasoning": "Add tasks to your plan first, then generate a schedule."
        }

    # Fetch existing Calendar events for conflict checking across the full plan duration
    existing_events = []
    calendar_connected = False
    calendar_note = "Calendar not connected — schedule generated without live conflict checking."

    oauth = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider.in_(["calendar", "google_all", "google"])
    ).first()

    now_utc = datetime.now(timezone.utc)
    lookahead_days = min(max(plan.duration_days or 30, 30), 183)

    if oauth:
        try:
            cal_res = await google_calendar_service.list_events(
                user_id=user.id,
                db=db,
                time_min=now_utc.isoformat(),
                time_max=(now_utc + timedelta(days=lookahead_days)).isoformat()
            )
            existing_events = cal_res.get("events", [])
            calendar_connected = True
            calendar_note = (
                f"Conflict-checked against {len(existing_events)} existing Google Calendar events "
                f"over the next {lookahead_days} days."
            )
        except Exception:
            calendar_note = (
                "Calendar is connected but could not be reached — "
                "schedule generated without live conflict checking."
            )

    busy_intervals: List[tuple] = []
    for ev in existing_events:
        try:
            s_str = ev.get("startTime") or ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
            e_str = ev.get("endTime") or ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date")
            if s_str and e_str and "T" in s_str:
                s_dt = datetime.fromisoformat(s_str.replace("Z", "+00:00"))
                e_dt = datetime.fromisoformat(e_str.replace("Z", "+00:00"))
                busy_intervals.append((s_dt, e_dt))
        except Exception:
            pass

    def _has_conflict(start_dt: datetime, end_dt: datetime) -> bool:
        for b_start, b_end in busy_intervals:
            if start_dt < b_end and end_dt > b_start:
                return True
        return False

    proposed_blocks = []
    now_local = now_utc.astimezone(user_tz)
    default_candidate_date = now_local.date() + timedelta(days=1)
    day_last_end_time: Dict[str, datetime] = {}

    for task in tasks:
        duration_mins = task.duration_minutes or 60

        # Determine target date
        if task.scheduled_date:
            try:
                candidate_date = date_type.fromisoformat(task.scheduled_date)
            except Exception:
                candidate_date = default_candidate_date
        else:
            candidate_date = default_candidate_date

        slots_checked = 0
        while slots_checked < 365:
            if skip_weekends and candidate_date.weekday() >= 5:
                candidate_date += timedelta(days=1)
                slots_checked += 1
                continue

            # Start time on this day: either after previous task or at preferred_start_hour
            date_str = candidate_date.isoformat()
            if date_str in day_last_end_time:
                prev_end = day_last_end_time[date_str]
                slot_start = prev_end + timedelta(minutes=15) # 15 min break
            else:
                slot_start = datetime(
                    candidate_date.year, candidate_date.month, candidate_date.day,
                    preferred_start_hour, 0, 0,
                    tzinfo=user_tz
                )

            slot_end = slot_start + timedelta(minutes=duration_mins)

            # Check if this day's time exceeds preferred_end_hour
            if slot_end.hour > preferred_end_hour or (slot_end.hour == preferred_end_hour and slot_end.minute > 0):
                candidate_date += timedelta(days=1)
                slots_checked += 1
                continue

            conflict = _has_conflict(
                slot_start.astimezone(timezone.utc),
                slot_end.astimezone(timezone.utc)
            ) if calendar_connected else False

            date_iso = candidate_date.isoformat()
            date_label = candidate_date.strftime("%A, %d %b %Y")
            start_label = slot_start.strftime("%I:%M %p").lstrip("0")
            end_label = slot_end.strftime("%I:%M %p").lstrip("0")

            day_last_end_time[date_str] = slot_end

            proposed_blocks.append({
                "id": f"block_{len(proposed_blocks) + 1}",
                "taskId": task.id,
                "taskTitle": task.title,
                "focus": task.title,
                "day": date_label,
                "date": date_iso,
                "startTime": start_label,
                "endTime": end_label,
                "startIso": slot_start.isoformat(),
                "endIso": slot_end.isoformat(),
                "timezone": user_tz_str,
                "durationMinutes": duration_mins,
                "priority": task.priority or "high",
                "monthNumber": task.month_number,
                "weekNumber": task.week_number,
                "dayNumber": task.day_number,
                "taskType": task.task_type or "daily",
                "milestoneGroup": task.milestone_group,
                "dayLabel": task.day_label,
                "weekLabel": task.week_label,
                "monthLabel": task.month_label,
                "conflictFree": not conflict,
                "hasConflict": conflict,
                "calendarSyncStatus": "synced" if task.google_calendar_event_id else "not_synced",
                "calendarEventId": task.google_calendar_event_id,
                "reasoning": (
                    f"Scheduled '{task.title}' ({duration_mins} min) on {date_label} "
                    f"at {start_label}."
                    + (" ⚠️ Conflict detected with an existing Calendar event." if conflict else "")
                )
            })

            # Advance default candidate date if task did not have explicit scheduled date
            if not task.scheduled_date:
                default_candidate_date = candidate_date + timedelta(days=1)
            break

    conflict_count = sum(1 for b in proposed_blocks if b["hasConflict"])
    return {
        "planId": plan.id,
        "planTitle": plan.title,
        "durationDays": plan.duration_days,
        "startDate": plan.start_date,
        "endDate": plan.end_date,
        "calendarConnected": calendar_connected,
        "calendarNote": calendar_note,
        "proposedStudyBlocks": proposed_blocks,
        "totalSessions": len(proposed_blocks),
        "conflictCount": conflict_count,
        "timezone": user_tz_str,
        "reasoning": (
            f"Generated {len(proposed_blocks)} study session(s) spanning your {plan.period or 'study plan'}. "
            + (f"{conflict_count} conflict(s) detected — review before confirming." if conflict_count else "No conflicts detected.")
        )
    }

@router.post("/{plan_id}/apply-slots")
def apply_study_slots(
    plan_id: str,
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Persistently saves approved study blocks onto the plan AND updates each
    associated PlanTask's scheduled_date, start_time, end_time, and timezone.
    Does NOT create Google Calendar events — that requires /sync-calendar.
    """
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    new_blocks = payload.get("studyBlocks", [])
    current = plan.suggested_study_blocks or []
    plan.suggested_study_blocks = new_blocks if payload.get("replace", False) else (current + new_blocks)

    # Update individual PlanTask scheduling fields for blocks that have a taskId
    updated_task_ids = []
    for block in new_blocks:
        task_id = block.get("taskId")
        if not task_id:
            continue
        task = db.query(PlanTask).filter(
            PlanTask.id == task_id,
            PlanTask.plan_id == plan.id
        ).first()
        if task:
            if block.get("date"):
                task.scheduled_date = block["date"]
            if block.get("startTime"):
                task.start_time = block["startTime"]
            if block.get("endTime"):
                task.end_time = block["endTime"]
            if block.get("timezone"):
                task.timezone = block["timezone"]
            updated_task_ids.append(task_id)

    db.commit()
    db.refresh(plan)
    return {
        "success": True,
        "planId": plan.id,
        "studyBlocks": plan.suggested_study_blocks,
        "suggestedStudyBlocks": plan.suggested_study_blocks,
        "updatedTaskIds": updated_task_ids
    }


@router.post("/{plan_id}/sync-calendar")
async def sync_plan_sessions_to_calendar(
    plan_id: str,
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Batch-creates Google Calendar events for selected study sessions.
    Requires explicit user confirmation (selectedBlockIds in payload).
    Skips any block whose associated task already has a google_calendar_event_id
    (prevents duplicates on retry).
    Returns per-block success/failure results.
    """
    from app.services.google_services.calendar_service import google_calendar_service
    from app.services.capabilities import is_capability_enabled

    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    if not is_capability_enabled(user.id, "calendar", "create_events", db):
        raise HTTPException(
            status_code=403,
            detail="The 'Create Events' capability is disabled. Enable it in Settings > Integrations."
        )

    selected_ids = payload.get("selectedBlockIds") or []
    blocks_to_sync = payload.get("studyBlocks") or payload.get("blocks") or []

    # Filter to only selected blocks
    if selected_ids:
        blocks_to_sync = [b for b in blocks_to_sync if b.get("id") in selected_ids]

    if not blocks_to_sync:
        raise HTTPException(status_code=400, detail="No study sessions selected for Calendar synchronization.")

    results = []
    for block in blocks_to_sync:
        task_id = block.get("taskId")
        block_id = block.get("id", "?")

        # Look up task to check for existing calendar link
        task = None
        if task_id:
            task = db.query(PlanTask).filter(
                PlanTask.id == task_id,
                PlanTask.plan_id == plan.id
            ).first()

        # Skip if already synced (idempotency guard)
        if task and task.google_calendar_event_id:
            results.append({
                "blockId": block_id,
                "taskId": task_id,
                "status": "already_synced",
                "calendarEventId": task.google_calendar_event_id,
                "message": "Already linked to a Google Calendar event."
            })
            continue

        # Determine ISO start/end
        start_iso = block.get("startIso")
        end_iso = block.get("endIso")
        if not start_iso or not end_iso:
            results.append({
                "blockId": block_id,
                "taskId": task_id,
                "status": "error",
                "calendarEventId": None,
                "message": "Missing startIso/endIso — block cannot be scheduled without precise datetime."
            })
            continue

        title = block.get("taskTitle") or block.get("focus") or plan.title

        try:
            # Use the calendar service to create the event directly
            # (no proposal / confirmation token needed — user already confirmed via sync-calendar call)
            cal_res = await google_calendar_service.create_event_direct(
                user_id=user.id,
                db=db,
                title=title,
                start_time=start_iso,
                end_time=end_iso,
                description=f"Study session from AURELIA plan: {plan.title}",
                location=None
            )

            event_id = cal_res.get("eventId") or cal_res.get("id")
            if event_id:
                # Persist the Calendar event ID on the task
                if task:
                    task.google_calendar_event_id = event_id
                    db.commit()

                results.append({
                    "blockId": block_id,
                    "taskId": task_id,
                    "taskTitle": block.get("taskTitle") or block.get("focus") or "",
                    "status": "success",
                    "calendarEventId": event_id,
                    "message": f"Created Calendar event '{title}'."
                })
            else:
                results.append({
                    "blockId": block_id,
                    "taskId": task_id,
                    "taskTitle": block.get("taskTitle") or block.get("focus") or "",
                    "status": "error",
                    "calendarEventId": None,
                    "message": cal_res.get("message", "Calendar API returned no event ID.")
                })

        except Exception as exc:
            results.append({
                "blockId": block_id,
                "taskId": task_id,
                "taskTitle": block.get("taskTitle") or block.get("focus") or "",
                "status": "error",
                "calendarEventId": None,
                "message": str(exc)
            })

    success_count = sum(1 for r in results if r["status"] == "success")
    already_synced = sum(1 for r in results if r["status"] == "already_synced")
    failed_count   = sum(1 for r in results if r["status"] == "error")
    failures_list  = [r for r in results if r["status"] == "error"]

    return {
        "planId": plan.id,
        "totalRequested": len(blocks_to_sync),
        "successCount": success_count,
        "alreadySyncedCount": already_synced,
        "failedCount": failed_count,
        "results": results,
        "failures": failures_list,
        "message": (
            f"{success_count} session(s) added to Google Calendar."
            + (f" {failed_count} failed." if failed_count else "")
            + (f" {already_synced} already linked." if already_synced else "")
        )
    }
