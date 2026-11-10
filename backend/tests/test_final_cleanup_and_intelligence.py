import pytest
import uuid
from datetime import datetime, date, time, timedelta, timezone
from unittest.mock import AsyncMock, patch
from sqlalchemy.orm import Session

from app.db.models import User, Plan, PlanTask, TimetableEntry, OAuthAccount
from app.services.date_parser import (
    get_user_greeting,
    parse_explicit_calendar_date,
    get_user_week_bounds,
    get_user_month_bounds
)
from app.agent.graph import heuristic_classify_intent, is_calendar_view_intent, AureliaAgent
from app.services.google_services.calendar_service import google_calendar_service


# ==============================================================================
# PHASE 1: LOCALIZED GREETING TESTS
# ==============================================================================

def test_01_localized_greeting_hour_ranges():
    """
    Validates that get_user_greeting returns correct greeting based on user's timezone:
    Morning:   5:00 AM – 11:59 AM
    Afternoon: 12:00 PM – 4:59 PM
    Evening:   5:00 PM – 8:59 PM
    Night:     9:00 PM – 4:59 AM
    """
    import zoneinfo
    # Test specific hours
    hours_cases = [
        (4, 59, "Good night"),
        (5, 0, "Good morning"),
        (11, 59, "Good morning"),
        (12, 0, "Good afternoon"),
        (16, 59, "Good afternoon"),
        (17, 0, "Good evening"),
        (20, 59, "Good evening"),
        (21, 0, "Good night"),
        (23, 30, "Good night"),
        (2, 0, "Good night")
    ]

    for h, m, expected in hours_cases:
        fixed_dt = datetime(2026, 10, 31, h, m, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))
        with patch("app.services.date_parser.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            mock_dt.combine = datetime.combine
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.strptime = datetime.strptime
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            greeting = get_user_greeting("UTC")
            assert greeting == expected, f"Hour {h}:{m} expected {expected}, got {greeting}"


# ==============================================================================
# PHASE 2 & 3: CALENDAR WINDOW & CONNECTIVITY
# ==============================================================================

def test_02_calendar_default_window_and_limit():
    """
    Validates calendar_service.list_events default parameters:
    Broad window (-60 days to +120 days) and capacity for up to 250 events.
    """
    import inspect
    source = inspect.getsource(google_calendar_service.list_events)
    assert "days=60" in source
    assert "days=120" in source
    assert "250" in source


# ==============================================================================
# PHASE 4: CHATBOT CALENDAR INTELLIGENCE & INTENT ROUTING
# ==============================================================================

def test_03_calendar_intent_routing_coverage():
    """
    Verifies that all specified calendar questions route correctly to calendar_events_retrieval.
    """
    queries = [
        "What is on my schedule today?",
        "What do I have planned tomorrow?",
        "What is on my calendar this week?",
        "What do I have planned for this month?",
        "Do I have any events on November 5?",
        "What is my next event?",
        "What are my next three events?",
        "When is my next quiz?",
        "When is my next exam?",
        "When is my next meeting?",
        "Do I have any free time tomorrow afternoon?",
        "Am I free at 6 PM today?",
        "How many study sessions do I have this week?",
        "Show me my Google Calendar events for today.",
        "Show me my study tasks for today."
    ]

    for q in queries:
        routed = heuristic_classify_intent(q, user_tz="UTC")
        assert routed["tool"] == "calendar_events_retrieval", f"Query '{q}' routed to '{routed['tool']}' instead of calendar_events_retrieval"


def test_04_explicit_date_parsing():
    """
    Validates parse_explicit_calendar_date correctly extracts target dates from natural language.
    """
    ref = date(2026, 10, 31)
    d1 = parse_explicit_calendar_date("Do I have any events on November 5?", ref_date=ref)
    assert d1 == date(2026, 11, 5)

    d2 = parse_explicit_calendar_date("What is scheduled on 2026-11-12?", ref_date=ref)
    assert d2 == date(2026, 11, 12)

    d3 = parse_explicit_calendar_date("Check my calendar for Oct 25, 2026", ref_date=ref)
    assert d3 == date(2026, 10, 25)


@pytest.mark.asyncio
async def test_05_chatbot_honest_reporting_with_zero_study_plans(db_session, test_user):
    """
    Crucial Requirement:
    When a user has ZERO study plans, the chatbot must NOT claim their schedule is clear
    if they have real Google Calendar events. It must report the real events honestly.
    """
    agent = AureliaAgent()
    conv_id = str(uuid.uuid4())

    # Ensure zero study plans
    assert db_session.query(Plan).filter_by(user_id=test_user.id).count() == 0

    mock_cal_events = [
        {
            "id": "g_evt_101",
            "title": "Faculty Research Colloquium",
            "startTime": "2026-10-31T14:00:00Z",
            "endTime": "2026-10-31T15:30:00Z",
            "location": "Auditorium A"
        }
    ]

    with patch("app.agent.tool_registry.tool_registry.execute") as mock_exec:
        mock_exec.return_value = {
            "status": "success",
            "isLive": True,
            "events": mock_cal_events
        }

        # Fix today to 2026-10-31 in agent execution
        res = await agent.run(
            user_id=test_user.id,
            query="What is on my schedule for 2026-10-31?",
            conversation_id=conv_id,
            db=db_session
        )

        assert "Faculty Research Colloquium" in res["content"]
        assert "Google Calendar Events" in res["content"]
        assert "schedule is clear" not in res["content"].lower()


@pytest.mark.asyncio
async def test_06_chatbot_next_three_events(db_session, test_user):
    """
    Validates Sub-case D: 'What are my next three events?' returns multiple chronological events.
    """
    agent = AureliaAgent()
    conv_id = str(uuid.uuid4())

    now_utc = datetime.now(timezone.utc)
    t1 = (now_utc + timedelta(hours=2)).isoformat()
    t2 = (now_utc + timedelta(hours=5)).isoformat()
    t3 = (now_utc + timedelta(hours=8)).isoformat()

    mock_events = [
        {"id": "e1", "title": "Team Standup", "startTime": t1, "endTime": t1, "location": "Room 101"},
        {"id": "e2", "title": "Deep Learning Lecture", "startTime": t2, "endTime": t2, "location": "Hall B"},
        {"id": "e3", "title": "Project Review Meeting", "startTime": t3, "endTime": t3, "location": "Zoom"}
    ]

    with patch("app.agent.tool_registry.tool_registry.execute") as mock_exec:
        mock_exec.return_value = {"status": "success", "isLive": True, "events": mock_events}

        res = await agent.run(
            user_id=test_user.id,
            query="What are my next three events?",
            conversation_id=conv_id,
            db=db_session
        )

        assert "Team Standup" in res["content"]
        assert "Deep Learning Lecture" in res["content"]
        assert "Project Review Meeting" in res["content"]
        assert "Your Next 3 Scheduled Events" in res["content"]


@pytest.mark.asyncio
async def test_07_chatbot_quiz_intelligence(db_session, test_user):
    """
    Validates Sub-case B: 'When is my next quiz?' filters events for quizzes/exams.
    """
    agent = AureliaAgent()
    conv_id = str(uuid.uuid4())

    now_utc = datetime.now(timezone.utc)
    quiz_time = (now_utc + timedelta(days=1, hours=3)).isoformat()

    mock_events = [
        {"id": "e_reg", "title": "General Lab", "startTime": (now_utc + timedelta(hours=2)).isoformat(), "endTime": (now_utc + timedelta(hours=3)).isoformat()},
        {"id": "e_quiz", "title": "Algorithms Midterm Exam", "startTime": quiz_time, "endTime": quiz_time, "location": "Room 404"}
    ]

    with patch("app.agent.tool_registry.tool_registry.execute") as mock_exec:
        mock_exec.return_value = {"status": "success", "isLive": True, "events": mock_events}

        res = await agent.run(
            user_id=test_user.id,
            query="When is my next exam?",
            conversation_id=conv_id,
            db=db_session
        )

        assert "Algorithms Midterm Exam" in res["content"]
        assert "Room 404" in res["content"]


# ==============================================================================
# PHASE 5: STUDY PLAN DELETION & CALENDAR CLEANUP
# ==============================================================================

def test_08_delete_plan_with_calendar_cleanup(client, test_user, auth_headers, db_session):
    """
    Validates that DELETE /plans/{id}?delete_google_events=true removes both internal
    tasks and linked external Google Calendar events.
    """
    # Create plan with 2 tasks, 1 synced to Google Calendar
    plan = Plan(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        title="Temporary Delete Plan",
        period="14 days"
    )
    db_session.add(plan)
    db_session.commit()

    task1 = PlanTask(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        title="Synced Study Task",
        duration_minutes=60,
        google_calendar_event_id="g_cal_evt_999"
    )
    task2 = PlanTask(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        title="Local Study Task",
        duration_minutes=45
    )
    db_session.add_all([task1, task2])
    db_session.commit()

    with patch("app.services.google_services.calendar_service.google_calendar_service.delete_event", new_callable=AsyncMock) as mock_del:
        mock_del.return_value = {"deleted": True, "eventId": "g_cal_evt_999"}

        res = client.delete(f"/api/plans/{plan.id}?delete_google_events=true", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["deletedCalendarEvents"] == 1
        mock_del.assert_called_once()

    # Verify plan and tasks are deleted from database
    assert db_session.query(Plan).filter_by(id=plan.id).first() is None
    assert db_session.query(PlanTask).filter_by(plan_id=plan.id).count() == 0


def test_09_reconcile_orphans_endpoint(client, test_user, auth_headers, db_session):
    """
    Validates POST /plans/reconcile-orphans clears broken references when Google Calendar
    events have been removed externally.
    """
    plan = Plan(id=str(uuid.uuid4()), user_id=test_user.id, title="Orphan Plan", period="7 days")
    db_session.add(plan)
    db_session.commit()

    t_orphaned = PlanTask(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        title="Orphaned Task",
        duration_minutes=45,
        google_calendar_event_id="external_dead_id"
    )
    db_session.add(t_orphaned)
    db_session.commit()

    with patch("app.services.google_services.calendar_service.google_calendar_service.list_events", new_callable=AsyncMock) as mock_list:
        # Live calendar does NOT contain external_dead_id
        mock_list.return_value = {"events": [{"id": "unrelated_meeting"}]}

        res = client.post("/api/plans/reconcile-orphans", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["reconciledCount"] == 1

    db_session.refresh(t_orphaned)
    assert t_orphaned.google_calendar_event_id is None


# ==============================================================================
# PHASE 6: PLAN PROPOSAL PREVIEW WITHOUT PERSISTENCE
# ==============================================================================

def test_10_plan_proposal_preview_without_persistence(client, test_user, auth_headers, db_session):
    """
    Validates POST /plans/generate-proposal returns roadmap preview data without saving to DB.
    """
    initial_plans_count = db_session.query(Plan).filter_by(user_id=test_user.id).count()
    initial_tasks_count = db_session.query(PlanTask).count()

    payload = {
        "subject": "Deep Reinforcement Learning",
        "period": "14 days",
        "daily_hours_target": 2.5,
        "start_date": "2026-11-01"
    }

    res = client.post("/api/plans/generate-proposal", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()

    assert "tasks" in data
    assert len(data["tasks"]) > 0
    assert data["durationDays"] == 14

    # DB records must NOT have increased (preview only!)
    after_plans_count = db_session.query(Plan).filter_by(user_id=test_user.id).count()
    after_tasks_count = db_session.query(PlanTask).count()
    assert after_plans_count == initial_plans_count
    assert after_tasks_count == initial_tasks_count


# ==============================================================================
# PHASE 7: KNOWLEDGE BASE TIMETABLES CLEANUP
# ==============================================================================

def test_11_timetables_endpoint_returns_real_user_data_only(client, test_user, auth_headers, db_session):
    """
    Validates GET /knowledge/timetables returns only genuine user records and zero dummy items.
    """
    # Initially empty
    res_empty = client.get("/api/knowledge/timetables", headers=auth_headers)
    assert res_empty.status_code == 200
    assert res_empty.json() == []

    # Insert one genuine timetable entry
    tt = TimetableEntry(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        course_name="Compiler Construction",
        course_code="CS-501",
        day_of_week="Tuesday",
        start_time="09:00 AM",
        end_time="11:00 AM",
        room="LH-2",
        instructor="Dr. Turing"
    )
    db_session.add(tt)
    db_session.commit()

    res_real = client.get("/api/knowledge/timetables", headers=auth_headers)
    assert res_real.status_code == 200
    items = res_real.json()
    assert len(items) == 1
    assert items[0]["courseCode"] == "CS-501"
    assert items[0]["courseName"] == "Compiler Construction"
    assert "CS-702" not in [i["courseCode"] for i in items]
