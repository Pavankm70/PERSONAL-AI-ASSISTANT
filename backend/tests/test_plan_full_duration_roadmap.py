"""
AURELIA AI — Full Duration (1 Day to 6 Months) Study Planner & Roadmap Regression Tests

Covers:
1. Duration parsing and calendar date arithmetic (1d, 7d, 30d, 60d, 90d, 180d, leap years, month-end dates).
2. Complete roadmap hierarchy (Month -> Week -> Day -> Task) and proportional task generation (not fixed at 4).
3. Preferred study days & rest days handling.
4. Full-duration schedule proposal with Google Calendar conflict checking without writing events.
5. Explicit Google Calendar confirmation & synchronization with idempotency and partial success reporting.
6. Chatbot conversational intent routing (durations, week queries, tomorrow study queries, batch rescheduling).
7. Strict user isolation and authorization.
"""

import pytest
import uuid
import zoneinfo
from datetime import datetime, date, timezone, timedelta
from unittest.mock import patch, AsyncMock
import httpx

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import User, Plan, PlanTask, OAuthAccount, Conversation
from app.services.google_oauth.crypto import token_cipher
from app.agent.graph import agent_orchestrator, heuristic_classify_intent
from app.services.study_plan_generator import (
    parse_plan_duration,
    add_calendar_months,
    calculate_plan_dates,
    generate_study_plan_roadmap,
)


# ---------------------------------------------------------------------------
# 1. Duration Parsing & Calendar Date Arithmetic
# ---------------------------------------------------------------------------

def test_parse_plan_duration_various_durations():
    assert parse_plan_duration("1 day") == 1
    assert parse_plan_duration("7 days") == 7
    assert parse_plan_duration("1 week") == 7
    assert parse_plan_duration("2 weeks") == 14
    assert parse_plan_duration("30 days") == 30
    assert parse_plan_duration("1 month") == 30
    assert parse_plan_duration("2 months") == 60
    assert parse_plan_duration("two-month") == 60
    assert parse_plan_duration("3 months") == 90
    assert parse_plan_duration("three-month") == 90
    assert parse_plan_duration("quarter") == 90
    assert parse_plan_duration("6 months") == 180
    assert parse_plan_duration("six-month") == 180
    assert parse_plan_duration("half year") == 180
    # Clamping
    assert parse_plan_duration("10 months") == 183
    assert parse_plan_duration(None, duration_days=45) == 45
    assert parse_plan_duration(None, duration_days=250) == 183


def test_month_end_date_calculation_jan31_to_feb28():
    # Jan 31 in a non-leap year + 1 month -> Feb 28
    d_jan31 = date(2025, 1, 31)
    d_feb = add_calendar_months(d_jan31, 1)
    assert d_feb == date(2025, 2, 28)

    # March 31 + 1 month -> April 30
    d_mar31 = date(2025, 3, 31)
    d_apr = add_calendar_months(d_mar31, 1)
    assert d_apr == date(2025, 4, 30)


def test_month_end_date_calculation_leap_year():
    # Jan 31 in a leap year (2024) + 1 month -> Feb 29
    d_jan31_leap = date(2024, 1, 31)
    d_feb_leap = add_calendar_months(d_jan31_leap, 1)
    assert d_feb_leap == date(2024, 2, 29)


def test_calculate_plan_dates_calendar_months():
    # 2 months starting from Jan 1
    start_d, end_d, total_days = calculate_plan_dates(
        start_date_str="2025-01-01",
        duration_text="2 months"
    )
    assert start_d == date(2025, 1, 1)
    assert end_d == date(2025, 2, 28)  # Jan 1 + 2 months is Mar 1, minus 1 day = Feb 28
    assert total_days == 59


# ---------------------------------------------------------------------------
# 2. Roadmap Generation Across Different Durations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_roadmap_generation_1_day():
    roadmap = await generate_study_plan_roadmap(
        subject="Python Fundamentals",
        duration_text="1 day",
        daily_hours=2.0
    )
    assert roadmap["totalDays"] == 1
    assert len(roadmap["months"]) == 1
    assert len(roadmap["months"][0]["weeks"]) == 1
    assert len(roadmap["months"][0]["weeks"][0]["days"]) == 1
    assert len(roadmap["tasks"]) >= 1


@pytest.mark.asyncio
async def test_roadmap_generation_7_days():
    roadmap = await generate_study_plan_roadmap(
        subject="DSA",
        duration_text="7 days",
        daily_hours=1.5
    )
    assert roadmap["totalDays"] == 7
    assert len(roadmap["months"]) == 1
    assert len(roadmap["months"][0]["weeks"]) == 1
    assert len(roadmap["months"][0]["weeks"][0]["days"]) == 7
    assert len(roadmap["tasks"]) == 7


@pytest.mark.asyncio
async def test_roadmap_generation_30_days():
    roadmap = await generate_study_plan_roadmap(
        subject="DSA",
        duration_text="30 days",
        daily_hours=2.0
    )
    assert roadmap["totalDays"] == 30
    assert len(roadmap["months"]) == 1
    # 30 days = 4 full weeks + 1 partial week
    assert len(roadmap["months"][0]["weeks"]) == 5
    assert len(roadmap["tasks"]) == 30


@pytest.mark.asyncio
async def test_roadmap_generation_60_days():
    roadmap = await generate_study_plan_roadmap(
        subject="Java Spring Boot",
        duration_text="60 days",
        daily_hours=2.0
    )
    assert roadmap["totalDays"] == 60
    assert len(roadmap["months"]) == 2
    assert len(roadmap["tasks"]) == 60


@pytest.mark.asyncio
async def test_roadmap_generation_90_days():
    roadmap = await generate_study_plan_roadmap(
        subject="Machine Learning",
        duration_text="90 days",
        daily_hours=2.5
    )
    assert roadmap["totalDays"] == 90
    assert len(roadmap["months"]) == 3
    assert len(roadmap["tasks"]) == 90


@pytest.mark.asyncio
async def test_roadmap_generation_180_days():
    roadmap = await generate_study_plan_roadmap(
        subject="Full Stack Web Development",
        duration_text="180 days",
        daily_hours=2.0
    )
    assert roadmap["totalDays"] == 180
    assert len(roadmap["months"]) == 6
    assert len(roadmap["tasks"]) == 180


@pytest.mark.asyncio
async def test_proportional_task_counts_not_fixed_at_4():
    """Verify that generated task count scales with duration, not fixed at 4 milestones."""
    r_7 = await generate_study_plan_roadmap(subject="DSA", duration_text="7 days")
    r_30 = await generate_study_plan_roadmap(subject="DSA", duration_text="30 days")
    r_60 = await generate_study_plan_roadmap(subject="DSA", duration_text="60 days")

    assert len(r_7["tasks"]) == 7
    assert len(r_30["tasks"]) == 30
    assert len(r_60["tasks"]) == 60
    assert len(r_30["tasks"]) > 4


@pytest.mark.asyncio
async def test_preferred_study_days_and_rest_days():
    """Verify preferred study days are honored and non-study days are rest days."""
    roadmap = await generate_study_plan_roadmap(
        subject="DSA",
        duration_text="7 days",
        preferred_days=["Monday", "Wednesday", "Friday"]
    )
    all_days = roadmap["months"][0]["weeks"][0]["days"]
    assert len(all_days) == 7

    study_days = [d for d in all_days if not d["isRestDay"]]
    rest_days = [d for d in all_days if d["isRestDay"]]

    assert len(study_days) > 0
    assert len(rest_days) > 0
    for rd in rest_days:
        assert rd["totalPlannedMinutes"] == 0
        assert rd["tasks"] == []


# ---------------------------------------------------------------------------
# 3. Plan API Endpoints & Roadmap Retrieval
# ---------------------------------------------------------------------------

def test_api_create_plan_with_roadmap(client: TestClient, auth_headers: dict):
    res = client.post("/api/plans", json={
        "title": "Two-Month DSA Journey",
        "subject": "DSA",
        "durationDays": 60,
        "dailyHoursTarget": 2.0,
        "preferredStudyDays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    }, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["durationDays"] == 60
    assert data["subject"] == "DSA"
    assert len(data["tasks"]) > 30

    plan_id = data["id"]

    # Test GET /api/plans/{id}/roadmap
    r_res = client.get(f"/api/plans/{plan_id}/roadmap", headers=auth_headers)
    assert r_res.status_code == 200
    r_data = r_res.json()
    assert r_data["planId"] == plan_id
    assert r_data["totalDays"] == 60
    assert len(r_data["months"]) == 2
    assert r_data["totalTasks"] == len(data["tasks"])
    assert r_data["completedTasks"] == 0

    # Cleanup
    client.delete(f"/api/plans/{plan_id}", headers=auth_headers)


def test_api_generate_roadmap_for_existing_bare_plan(client: TestClient, auth_headers: dict, test_user: User, db_session: Session):
    plan = Plan(user_id=test_user.id, title="Empty Plan", period="30 Days", duration_days=30, subject="Machine Learning")
    db_session.add(plan)
    db_session.commit()

    # Trigger generation
    gen_res = client.post(f"/api/plans/{plan.id}/generate-roadmap", json={
        "subject": "Machine Learning",
        "dailyHoursTarget": 2.5
    }, headers=auth_headers)
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert len(gen_data["tasks"]) == 30

    # Verify roadmap endpoint now returns hierarchy
    r_res = client.get(f"/api/plans/{plan.id}/roadmap", headers=auth_headers)
    assert r_res.status_code == 200
    assert len(r_res.json()["months"]) == 1

    # Verify tasks are persisted in DB
    db_session.refresh(plan)
    assert len(plan.tasks) == 30

    client.delete(f"/api/plans/{plan.id}", headers=auth_headers)


# ---------------------------------------------------------------------------
# 4. Full Duration Schedule Proposal & Conflict Check (No Calendar Writes)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_propose_slots_full_duration_with_conflict_check(client: TestClient, auth_headers: dict, test_user: User, db_session: Session):
    plan = Plan(
        user_id=test_user.id,
        title="Full Stack 60-Day Plan",
        subject="Full Stack Web Development",
        duration_days=60
    )
    db_session.add(plan)
    db_session.commit()

    # Generate 60 tasks
    roadmap = await generate_study_plan_roadmap("Full Stack", duration_text="60 days")
    tasks = []
    for item in roadmap["tasks"]:
        tasks.append(PlanTask(
            plan_id=plan.id,
            title=item["title"],
            duration_minutes=item["durationMinutes"],
            month_number=item.get("monthNumber"),
            week_number=item.get("weekNumber"),
            day_number=item.get("dayNumber"),
            milestone_group=item.get("milestoneGroup"),
            scheduled_date=item.get("scheduledDate")
        ))
    db_session.add_all(tasks)
    db_session.commit()

    # Call propose-slots
    res = client.post(f"/api/plans/{plan.id}/propose-slots", json={
        "preferredStartHour": 18,
        "preferredEndHour": 21
    }, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    blocks = data["proposedStudyBlocks"]

    assert len(blocks) == 60
    assert blocks[0]["monthNumber"] == 1
    assert blocks[-1]["monthNumber"] == 2
    assert "startIso" in blocks[0]
    assert "endIso" in blocks[0]
    assert "hasConflict" in blocks[0]

    # Verify proposal does NOT write any calendar events to DB or Google
    db_session.refresh(plan)
    for t in plan.tasks:
        assert t.google_calendar_event_id is None

    client.delete(f"/api/plans/{plan.id}", headers=auth_headers)


# ---------------------------------------------------------------------------
# 5. Explicit Calendar Sync, Idempotency & Partial Failure Handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_calendar_explicit_confirmation_and_idempotency(client: TestClient, auth_headers: dict, test_user: User, db_session: Session):
    plan = Plan(user_id=test_user.id, title="Algorithm Sprint", period="7 Days", duration_days=7)
    db_session.add(plan)
    db_session.commit()

    t1 = PlanTask(plan_id=plan.id, title="Two Pointers", duration_minutes=60, scheduled_date="2026-11-01")
    t2 = PlanTask(plan_id=plan.id, title="Sliding Window", duration_minutes=60, scheduled_date="2026-11-02")
    db_session.add_all([t1, t2])
    db_session.commit()

    fake_oa = OAuthAccount(
        user_id=test_user.id,
        provider="google",
        encrypted_access_token=token_cipher.encrypt("valid_token"),
        encrypted_refresh_token=token_cipher.encrypt("valid_refresh"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    db_session.add(fake_oa)
    db_session.commit()

    blocks = [
        {
            "id": "b1",
            "taskId": t1.id,
            "taskTitle": t1.title,
            "date": "2026-11-01",
            "startIso": "2026-11-01T10:00:00+00:00",
            "endIso": "2026-11-01T11:00:00+00:00",
            "durationMinutes": 60
        },
        {
            "id": "b2",
            "taskId": t2.id,
            "taskTitle": t2.title,
            "date": "2026-11-02",
            "startIso": "2026-11-02T10:00:00+00:00",
            "endIso": "2026-11-02T11:00:00+00:00",
            "durationMinutes": 60
        }
    ]

    mock_resp = httpx.Response(200, json={"id": "gcal_evt_101", "summary": "Two Pointers"}, request=httpx.Request("POST", "https://mock"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res1 = client.post(f"/api/plans/{plan.id}/sync-calendar", json={"blocks": blocks}, headers=auth_headers)
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1["successCount"] == 2
        assert d1["alreadySyncedCount"] == 0

        # Run again to test idempotency (no duplicate events created)
        res2 = client.post(f"/api/plans/{plan.id}/sync-calendar", json={"blocks": blocks}, headers=auth_headers)
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["successCount"] == 0
        assert d2["alreadySyncedCount"] == 2


@pytest.mark.asyncio
async def test_sync_calendar_partial_success_reporting(client: TestClient, auth_headers: dict, test_user: User, db_session: Session):
    plan = Plan(user_id=test_user.id, title="Partial Test Plan", period="7 Days")
    db_session.add(plan)
    db_session.commit()

    t1 = PlanTask(plan_id=plan.id, title="Task Success", duration_minutes=60)
    t2 = PlanTask(plan_id=plan.id, title="Task Fail", duration_minutes=60)
    db_session.add_all([t1, t2])
    db_session.commit()

    fake_oa = OAuthAccount(
        user_id=test_user.id,
        provider="google",
        encrypted_access_token=token_cipher.encrypt("valid_token"),
        encrypted_refresh_token=token_cipher.encrypt("valid_refresh"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    db_session.add(fake_oa)
    db_session.commit()

    blocks = [
        {"id": "b1", "taskId": t1.id, "taskTitle": t1.title, "date": "2026-11-01", "startIso": "2026-11-01T10:00:00Z", "endIso": "2026-11-01T11:00:00Z", "durationMinutes": 60},
        {"id": "b2", "taskId": t2.id, "taskTitle": t2.title, "date": "2026-11-02", "startIso": "2026-11-02T10:00:00Z", "endIso": "2026-11-02T11:00:00Z", "durationMinutes": 60}
    ]

    # First succeeds, second raises error
    call_count = 0
    async def mock_post_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, json={"id": "gcal_1"}, request=httpx.Request("POST", "https://mock"))
        raise httpx.RequestError("Network error on Google API")

    with patch("httpx.AsyncClient.post", side_effect=mock_post_side_effect):
        res = client.post(f"/api/plans/{plan.id}/sync-calendar", json={"blocks": blocks}, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["successCount"] == 1
        assert data["failedCount"] == 1
        assert len(data["failures"]) == 1
        assert data["failures"][0]["taskTitle"] == "Task Fail"


# ---------------------------------------------------------------------------
# 6. Chatbot Intent Routing & Conversational Grounding
# ---------------------------------------------------------------------------

class TestChatbotFullDurationIntentRouting:
    def test_route_two_month_dsa_plan(self):
        r = heuristic_classify_intent("Create a two-month DSA study plan")
        assert r["tool"] == "plan_create"
        assert r["args"]["duration_days"] == 60
        assert "dsa" in r["args"]["subject"].lower()

    def test_route_week_specific_query(self):
        r = heuristic_classify_intent("Show me week three of my Java plan")
        assert r["tool"] == "plan_get"
        assert r["args"]["week_number"] == 3

    def test_route_tomorrow_study_query(self):
        r = heuristic_classify_intent("What should I study tomorrow?")
        assert r["tool"] == "plan_get"
        assert r["args"]["daily_study_query"] is True
        assert r["args"]["target_date"] == "tomorrow"

    def test_route_reschedule_unfinished_tasks(self):
        r = heuristic_classify_intent("Reschedule my unfinished tasks")
        assert r["tool"] == "plan_reschedule_task"
        assert r["args"]["reschedule_all_pending"] is True


@pytest.mark.asyncio
async def test_chatbot_week_specific_response(db_session: Session, test_user: User):
    plan = Plan(user_id=test_user.id, title="Java Backend Roadmap", subject="Java")
    db_session.add(plan)
    db_session.commit()

    t_w2 = PlanTask(plan_id=plan.id, title="Java Collections Framework", week_number=2, completed=True)
    t_w3_a = PlanTask(plan_id=plan.id, title="Spring Boot REST Controllers", week_number=3, completed=False)
    t_w3_b = PlanTask(plan_id=plan.id, title="Spring Data JPA Entities", week_number=3, completed=False)
    db_session.add_all([t_w2, t_w3_a, t_w3_b])
    db_session.commit()

    conv = Conversation(user_id=test_user.id, title="Week Query Session")
    db_session.add(conv)
    db_session.commit()

    with patch("app.core.config.settings.GEMINI_API_KEY", ""):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Show me week three of my Java plan",
            conversation_id=conv.id,
            db=db_session
        )

    assert "Spring Boot REST Controllers" in res["content"]
    assert "Spring Data JPA Entities" in res["content"]
    assert "Collections" not in res["content"]  # week 2 task should not be shown


@pytest.mark.asyncio
async def test_chatbot_what_should_i_study_tomorrow(db_session: Session, test_user: User):
    plan = Plan(user_id=test_user.id, title="Active Daily Plan")
    db_session.add(plan)
    db_session.commit()

    user_tz = zoneinfo.ZoneInfo(test_user.timezone or "UTC")
    now_local = datetime.now(timezone.utc).astimezone(user_tz)
    tomorrow_str = (now_local.date() + timedelta(days=1)).isoformat()

    t_tom = PlanTask(plan_id=plan.id, title="Binary Search Trees Practice", scheduled_date=tomorrow_str, completed=False)
    db_session.add(t_tom)
    db_session.commit()

    conv = Conversation(user_id=test_user.id, title="Daily Study Session")
    db_session.add(conv)
    db_session.commit()

    with patch("app.core.config.settings.GEMINI_API_KEY", ""):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="What should I study tomorrow?",
            conversation_id=conv.id,
            db=db_session
        )

    assert "Binary Search Trees Practice" in res["content"]


@pytest.mark.asyncio
async def test_chatbot_reschedule_unfinished_tasks(db_session: Session, test_user: User):
    plan = Plan(user_id=test_user.id, title="Sprint Plan")
    db_session.add(plan)
    db_session.commit()

    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    t_missed = PlanTask(plan_id=plan.id, title="Missed Graph Traversal", scheduled_date=yesterday_str, completed=False)
    db_session.add(t_missed)
    db_session.commit()

    conv = Conversation(user_id=test_user.id, title="Reschedule Session")
    db_session.add(conv)
    db_session.commit()

    with patch("app.core.config.settings.GEMINI_API_KEY", ""):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Reschedule my unfinished tasks",
            conversation_id=conv.id,
            db=db_session
        )

    assert "rescheduled" in res["content"].lower()
    db_session.refresh(t_missed)
    assert t_missed.scheduled_date > yesterday_str


# ---------------------------------------------------------------------------
# 7. User Isolation & Security
# ---------------------------------------------------------------------------

def test_user_isolation_roadmap_and_slots(client: TestClient, db_session: Session, test_user: User):
    # Create User B
    user_b = User(
        id="usr_test_b_isolate",
        email="user_b@example.com",
        full_name="User B",
        timezone="America/Los_Angeles",
        onboarding_complete=True
    )
    db_session.add(user_b)
    db_session.commit()

    # Create plan belonging to User A
    plan_a = Plan(user_id=test_user.id, title="User A Secret Plan", period="30 Days")
    db_session.add(plan_a)
    db_session.commit()

    # User B auth headers
    from app.core.security import create_access_token
    token_b = create_access_token({"sub": str(user_b.id), "email": user_b.email})
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B attempts to access User A's roadmap -> 404
    res_roadmap = client.get(f"/api/plans/{plan_a.id}/roadmap", headers=headers_b)
    assert res_roadmap.status_code == 404

    # User B attempts to propose slots on User A's plan -> 404
    res_slots = client.post(f"/api/plans/{plan_a.id}/propose-slots", json={}, headers=headers_b)
    assert res_slots.status_code == 404

    # User B attempts to sync calendar on User A's plan -> 404
    res_sync = client.post(f"/api/plans/{plan_a.id}/sync-calendar", json={"blocks": []}, headers=headers_b)
    assert res_sync.status_code == 404
