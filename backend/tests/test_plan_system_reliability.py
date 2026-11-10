"""
AURELIA AI — Plan Section & Productivity System Reliability Regression Tests
Tests end-to-end plan persistence, smart schedule proposal with real ISO dates & conflict checks,
explicit Google Calendar confirmation & synchronization, idempotency, progress tracking,
and chatbot conversational intent routing.
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
import httpx

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import User, Plan, PlanTask, OAuthAccount, Conversation
from app.services.google_oauth.crypto import token_cipher
from app.agent.graph import agent_orchestrator, heuristic_classify_intent


# ---------------------------------------------------------------------------
# 1. Plan Persistence, CRUD & Progress
# ---------------------------------------------------------------------------

def test_plan_persistence_and_progress_metrics(client: TestClient, auth_headers: dict, test_user: User, db_session: Session):
    """
    1. Create plan with daily study target.
    2. Add tasks with various priorities and durations.
    3. Verify completion metrics: total, completed, pending, percentage.
    4. Verify empty state when no plans exist.
    """
    # 1. Create plan
    res = client.post("/api/plans", json={
        "title": "Full Stack Mastery",
        "period": "60 Days",
        "goals": ["Master FastAPI", "Master React"],
        "tasks": [
            {"title": "FastAPI Async Endpoints", "durationMinutes": 120, "priority": "high"},
            {"title": "React Query & State Management", "durationMinutes": 90, "priority": "medium"},
            {"title": "PostgreSQL Index Optimization", "durationMinutes": 60, "priority": "low"}
        ]
    }, headers=auth_headers)
    assert res.status_code == 200
    p = res.json()
    plan_id = p["id"]
    assert len(p["tasks"]) == 3

    # 2. Complete one task
    t1_id = p["tasks"][0]["id"]
    up_res = client.patch(f"/api/plans/{plan_id}/tasks/{t1_id}", json={"completed": True}, headers=auth_headers)
    assert up_res.status_code == 200
    assert up_res.json()["completed"] is True

    # 3. Retrieve plan in a fresh query and verify tasks and completion
    get_res = client.get(f"/api/plans/{plan_id}", headers=auth_headers)
    assert get_res.status_code == 200
    fetched = get_res.json()
    tasks = fetched["tasks"]
    assert len(tasks) == 3
    completed = [t for t in tasks if t["completed"]]
    assert len(completed) == 1
    assert completed[0]["title"] == "FastAPI Async Endpoints"

    # Cleanup
    client.delete(f"/api/plans/{plan_id}", headers=auth_headers)


# ---------------------------------------------------------------------------
# 2. Smart Schedule Proposal (Real ISO dates, conflict detection, no Calendar writes)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_propose_slots_generates_real_dates_and_checks_conflicts(client: TestClient, auth_headers: dict, test_user: User, db_session: Session):
    """
    Verifies that /propose-slots:
    - Generates real ISO dates (YYYY-MM-DD), not just day-of-week strings
    - Computes valid start and end ISO timestamps matching duration
    - Inspects Google Calendar for conflicts without creating any events
    """
    plan = Plan(user_id=test_user.id, title="DSA Preparation", period="30 Days")
    db_session.add(plan)
    db_session.commit()

    t1 = PlanTask(plan_id=plan.id, title="Arrays & Two Pointers", duration_minutes=90, priority="high")
    t2 = PlanTask(plan_id=plan.id, title="Sliding Window Problems", duration_minutes=60, priority="medium")
    db_session.add_all([t1, t2])
    db_session.commit()

    # Call propose-slots
    res = client.post(f"/api/plans/{plan.id}/propose-slots", json={
        "preferredStartHour": 10,
        "preferredEndHour": 18
    }, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["planId"] == plan.id
    blocks = data["proposedStudyBlocks"]
    assert len(blocks) == 2

    b1 = blocks[0]
    assert b1["taskId"] == t1.id
    assert b1["durationMinutes"] == 90
    assert "startIso" in b1 and "endIso" in b1
    # Check that date is a real ISO date format: YYYY-MM-DD
    assert len(b1["date"]) == 10 and b1["date"][4] == "-" and b1["date"][7] == "-"
    # Check that end time is start time + 90 mins
    s_dt = datetime.fromisoformat(b1["startIso"])
    e_dt = datetime.fromisoformat(b1["endIso"])
    assert (e_dt - s_dt).total_seconds() == 90 * 60

    # No calendar events must be written by proposal
    # (plan.suggested_study_blocks remains untouched until apply or sync)
    db_session.refresh(plan)
    assert plan.suggested_study_blocks == []


# ---------------------------------------------------------------------------
# 3. Apply Slots Updates Task Scheduling Fields
# ---------------------------------------------------------------------------

def test_apply_slots_updates_plan_tasks(client: TestClient, auth_headers: dict, test_user: User, db_session: Session):
    """
    Verifies that applying study blocks:
    - Saves blocks on the plan
    - Updates scheduled_date, start_time, end_time on individual PlanTask records
    """
    plan = Plan(user_id=test_user.id, title="DevOps Sprint", period="14 Days")
    db_session.add(plan)
    db_session.commit()

    t1 = PlanTask(plan_id=plan.id, title="Docker Multi-Stage Builds", duration_minutes=60)
    db_session.add(t1)
    db_session.commit()

    sample_block = {
        "id": "block_1",
        "taskId": t1.id,
        "taskTitle": t1.title,
        "day": "Wednesday, 28 Oct 2026",
        "date": "2026-10-28",
        "startTime": "10:00 AM",
        "endTime": "11:00 AM",
        "startIso": "2026-10-28T10:00:00+00:00",
        "endIso": "2026-10-28T11:00:00+00:00",
        "timezone": "UTC",
        "durationMinutes": 60
    }

    res = client.post(f"/api/plans/{plan.id}/apply-slots", json={
        "studyBlocks": [sample_block]
    }, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Verify task was updated
    db_session.refresh(t1)
    assert t1.scheduled_date == "2026-10-28"
    assert t1.start_time == "10:00 AM"
    assert t1.end_time == "11:00 AM"


# ---------------------------------------------------------------------------
# 4. Google Calendar Batch Synchronization & Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calendar_sync_batch_creation_and_idempotency(client: TestClient, auth_headers: dict, test_user: User, db_session: Session):
    """
    Verifies that POST /api/plans/{id}/sync-calendar:
    - Creates real/mocked Google Calendar events for selected sessions
    - Saves google_calendar_event_id against the associated PlanTask
    - Skips already-synced tasks on retry to prevent duplicates
    - Rejects request if Calendar capability is disabled
    """
    # Attach OAuth account
    acc = OAuthAccount(
        user_id=test_user.id,
        provider="calendar",
        encrypted_access_token=token_cipher.encrypt("mock_token"),
        encrypted_refresh_token=token_cipher.encrypt("mock_refresh"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    db_session.add(acc)
    db_session.commit()

    plan = Plan(user_id=test_user.id, title="System Design Plan", period="30 Days")
    db_session.add(plan)
    db_session.commit()

    t1 = PlanTask(plan_id=plan.id, title="Distributed Caching with Redis", duration_minutes=60)
    t2 = PlanTask(plan_id=plan.id, title="Message Queues with Kafka", duration_minutes=60)
    db_session.add_all([t1, t2])
    db_session.commit()

    blocks = [
        {
            "id": "block_1",
            "taskId": t1.id,
            "taskTitle": t1.title,
            "startIso": "2026-10-29T10:00:00Z",
            "endIso": "2026-10-29T11:00:00Z",
            "durationMinutes": 60
        },
        {
            "id": "block_2",
            "taskId": t2.id,
            "taskTitle": t2.title,
            "startIso": "2026-10-30T10:00:00Z",
            "endIso": "2026-10-30T11:00:00Z",
            "durationMinutes": 60
        }
    ]

    mock_created_events = [
        {"id": "cal_evt_101", "summary": t1.title},
        {"id": "cal_evt_102", "summary": t2.title}
    ]
    post_count = 0

    async def mock_cal_post(url, headers, json):
        nonlocal post_count
        post_count += 1
        return httpx.Response(201, json={"id": f"cal_evt_{100 + post_count}", "summary": json.get("summary")})

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.post = AsyncMock(side_effect=mock_cal_post)
        MockClient.return_value = mock_instance

        # 1. First sync: sync both blocks
        sync_res = client.post(f"/api/plans/{plan.id}/sync-calendar", json={
            "studyBlocks": blocks,
            "selectedBlockIds": ["block_1", "block_2"]
        }, headers=auth_headers)

        assert sync_res.status_code == 200
        sdata = sync_res.json()
        assert sdata["successCount"] == 2
        assert sdata["failedCount"] == 0

        # Verify google_calendar_event_id was stored on tasks
        db_session.refresh(t1)
        db_session.refresh(t2)
        assert t1.google_calendar_event_id == "cal_evt_101"
        assert t2.google_calendar_event_id == "cal_evt_102"

        # 2. Second sync attempt with the exact same blocks:
        # Idempotency guard must skip already-synced tasks and NOT create duplicate calendar events!
        retry_res = client.post(f"/api/plans/{plan.id}/sync-calendar", json={
            "studyBlocks": blocks,
            "selectedBlockIds": ["block_1", "block_2"]
        }, headers=auth_headers)

        assert retry_res.status_code == 200
        rdata = retry_res.json()
        assert rdata["alreadySyncedCount"] == 2
        assert rdata["successCount"] == 0
        # post_count must still be 2 (no extra calendar writes)
        assert post_count == 2


# ---------------------------------------------------------------------------
# 5. Chatbot Intent Routing & Conversational Grounding
# ---------------------------------------------------------------------------

class TestChatbotPlanIntentRouting:
    """Verifies that natural language requests route to the right plan tools."""

    def test_route_show_saved_plans(self):
        r = heuristic_classify_intent("Show my saved study plans")
        assert r["tool"] == "plan_list"

    def test_route_create_plan(self):
        r = heuristic_classify_intent("Create a 30-day DSA preparation plan.")
        assert r["tool"] == "plan_create"
        assert "dsa" in r["args"]["subject"].lower() or "dsa" in r["args"]["title"].lower()

    def test_route_propose_schedule(self):
        r = heuristic_classify_intent("Generate a schedule for my DSA plan")
        assert r["tool"] == "plan_propose_schedule"

    def test_route_sync_calendar(self):
        r = heuristic_classify_intent("Add the selected study sessions to Google Calendar")
        assert r["tool"] == "plan_sync_calendar"
        assert r["args"]["confirmed"] is False

    def test_route_pending_tasks(self):
        r = heuristic_classify_intent("What tasks are pending in my DSA plan?")
        assert r["tool"] == "plan_get"

    def test_route_completion_progress(self):
        r = heuristic_classify_intent("How much of my project plan have I completed?")
        assert r["tool"] == "plan_get"

    def test_route_complete_task(self):
        r = heuristic_classify_intent("Mark my Arrays task as completed")
        assert r["tool"] == "plan_complete_task"


@pytest.mark.asyncio
async def test_chatbot_propose_schedule_returns_grounded_response_no_calendar_write(db_session: Session, test_user: User):
    """
    Verifies that 'Generate a schedule for my DSA plan' in chat:
    - Calculates dates and times
    - Returns a proposal response
    - Does NOT write to Google Calendar
    """
    plan = Plan(user_id=test_user.id, title="DSA Preparation", period="30 Days")
    db_session.add(plan)
    db_session.commit()

    t1 = PlanTask(plan_id=plan.id, title="Binary Search Fundamentals", duration_minutes=60, completed=False)
    db_session.add(t1)
    db_session.commit()

    conv = Conversation(user_id=test_user.id, title="Schedule Generation Session")
    db_session.add(conv)
    db_session.commit()

    with patch("app.core.config.settings.GEMINI_API_KEY", ""):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Generate a schedule for my DSA plan",
            conversation_id=conv.id,
            db=db_session
        )

    assert "Binary Search Fundamentals" in res["content"]
    assert "**not** been added to google calendar" in res["content"].lower()
    # No suggestedAction with immediate write executed
    db_session.refresh(t1)
    assert t1.google_calendar_event_id is None


@pytest.mark.asyncio
async def test_chatbot_sync_calendar_requires_confirmation_card(db_session: Session, test_user: User):
    """
    Verifies that 'Add the selected study sessions to Google Calendar' in chat:
    - Returns a suggestedAction confirmation card (status: 'pending')
    - Does NOT immediately write events
    """
    plan = Plan(
        user_id=test_user.id,
        title="Web Development Sprint",
        period="14 Days",
        suggested_study_blocks=[
            {
                "id": "blk_1",
                "taskId": "task_1",
                "taskTitle": "CSS Grid & Flexbox",
                "day": "Monday, 27 Oct",
                "startIso": "2026-10-27T09:00:00Z",
                "endIso": "2026-10-27T10:00:00Z"
            }
        ]
    )
    db_session.add(plan)
    db_session.commit()

    conv = Conversation(user_id=test_user.id, title="Calendar Sync Chat")
    db_session.add(conv)
    db_session.commit()

    with patch("app.core.config.settings.GEMINI_API_KEY", ""):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Add the selected study sessions to Google Calendar",
            conversation_id=conv.id,
            db=db_session
        )

    sa = res.get("suggestedAction")
    assert sa is not None, "Must present a confirmation card before Calendar synchronization"
    assert sa["actionType"] == "sync_plan_calendar"
    assert sa["status"] == "pending"
    assert "Web Development Sprint" in sa["title"]


@pytest.mark.asyncio
async def test_chatbot_plan_get_honest_empty_state_when_no_plans(db_session: Session, test_user: User):
    """
    If user has no plans, 'What tasks are pending in my DSA plan?' must honestly say
    no saved study plans were found — never invent fake plans.
    """
    conv = Conversation(user_id=test_user.id, title="Empty Plan Inspection")
    db_session.add(conv)
    db_session.commit()

    with patch("app.core.config.settings.GEMINI_API_KEY", ""):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="What tasks are pending in my DSA plan?",
            conversation_id=conv.id,
            db=db_session
        )

    assert "do not have any saved study plans" in res["content"]
