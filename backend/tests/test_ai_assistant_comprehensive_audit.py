import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
import httpx

from app.db.models import User, OAuthAccount, Conversation, Message, Plan, PlanTask
from app.services.google_oauth.crypto import token_cipher
from app.services.google_services.gmail_service import google_gmail_service
from app.services.google_services.calendar_service import google_calendar_service
from app.agent.graph import agent_orchestrator, heuristic_classify_intent
from app.agent.tool_registry import tool_registry

_RealAsyncClient = httpx.AsyncClient

# =====================================================================
# 1. GREETINGS & GENERAL QA: NEVER FAILS TO RAG
# =====================================================================

def test_greeting_and_bot_identity_heuristic_routing():
    for phrase in ["Hello", "Hi", "Hey", "Good morning", "Who are you?", "What can you do?", "Help me"]:
        result = heuristic_classify_intent(phrase)
        assert result["tool"] == "general_qa", f"Expected '{phrase}' to route to 'general_qa', got '{result['tool']}'"

@pytest.mark.asyncio
async def test_general_qa_execution_returns_helpful_response(db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Intro Chat")
    db_session.add(conv)
    db_session.commit()

    # Query without mock Gemini API key: deterministic response
    with patch("app.core.config.settings.GEMINI_API_KEY", ""):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Hello! What can you do?",
            conversation_id=conv.id,
            db=db_session
        )
        assert res["role"] == "assistant"
        assert "Aurelia AI" in res["content"]
        # Must NOT claim insufficient evidence or cite empty uploaded documents!
        assert "uploaded documents do not provide enough information" not in res["content"]
        assert res["diagnostics"]["selectedTool"] == "general_qa"

# =====================================================================
# 2. CALENDAR EVENT DELETION & RESCHEDULING
# =====================================================================

def test_calendar_delete_event_heuristic_routing():
    queries = [
        ("Cancel my 3 PM meeting tomorrow", "meeting"),
        ("Delete the doctor appointment tomorrow", "doctor appointment"),
        ("Cancel my study session tomorrow", "study session"),
    ]
    for q, expected_term in queries:
        routed = heuristic_classify_intent(q)
        assert routed["tool"] == "calendar_delete_event", f"Expected 'calendar_delete_event' for '{q}', got '{routed['tool']}'"

@pytest.mark.asyncio
async def test_calendar_delete_event_requires_confirmation(db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Calendar Delete Test")
    db_session.add(conv)

    # Attach mock calendar OAuth
    acc_cal = OAuthAccount(
        user_id=test_user.id,
        provider="calendar",
        encrypted_access_token=token_cipher.encrypt("valid_token"),
        encrypted_refresh_token=token_cipher.encrypt("refresh_token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    db_session.add(acc_cal)
    db_session.commit()

    mock_events = {
        "items": [
            {
                "id": "cal_ev_team_sync",
                "summary": "Team Sync Meeting",
                "start": {"dateTime": "2026-10-28T15:00:00Z"},
                "end": {"dateTime": "2026-10-28T16:00:00Z"}
            }
        ]
    }

    async def mock_handler(request: httpx.Request):
        if request.method == "GET" and "events" in str(request.url):
            return httpx.Response(200, json=mock_events)
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _RealAsyncClient(transport=transport)):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Cancel my Team Sync Meeting tomorrow",
            conversation_id=conv.id,
            db=db_session
        )

        assert res["suggestedAction"] is not None
        sa = res["suggestedAction"]
        assert sa["actionType"] == "delete_event"
        assert sa["status"] == "pending"
        assert sa["details"]["eventId"] == "cal_ev_team_sync"
        assert "Team Sync Meeting" in sa["details"]["title"]
        assert "Confirmation Required" in res["content"]

@pytest.mark.asyncio
async def test_calendar_delete_event_execution(db_session, test_user):
    # Setup linked plan task
    plan = Plan(user_id=test_user.id, title="Test Plan", period="Sprint")
    db_session.add(plan)
    db_session.commit()

    task = PlanTask(
        plan_id=plan.id,
        title="Sync Session",
        duration_minutes=60,
        google_calendar_event_id="cal_ev_to_delete"
    )
    db_session.add(task)
    db_session.commit()

    # Execute deletion via tool registry
    async def mock_handler(request: httpx.Request):
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404)

    # Attach mock calendar OAuth
    acc_cal = OAuthAccount(
        user_id=test_user.id,
        provider="calendar",
        encrypted_access_token=token_cipher.encrypt("valid_token"),
        encrypted_refresh_token=token_cipher.encrypt("refresh_token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    db_session.add(acc_cal)
    db_session.commit()

    transport = httpx.MockTransport(mock_handler)
    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _RealAsyncClient(transport=transport)):
        del_res = await tool_registry.execute(
            "calendar_delete_event",
            user_id=test_user.id,
            db=db_session,
            event_id="cal_ev_to_delete"
        )
        assert del_res["deleted"] is True
        assert del_res["eventId"] == "cal_ev_to_delete"

# =====================================================================
# 3. GMAIL CONFIRMATION TOKEN PROTECTION & EXPIRATION
# =====================================================================

@pytest.mark.asyncio
async def test_gmail_send_message_token_protection(db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Gmail Send Test")
    db_session.add(conv)
    db_session.commit()

    with patch("app.core.config.settings.GEMINI_API_KEY", ""):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Send an email to advisor@university.edu about thesis feedback",
            conversation_id=conv.id,
            db=db_session
        )

        sa = res.get("suggestedAction")
        assert sa is not None
        assert sa["actionType"] == "send_email"
        assert sa["status"] == "pending"

        # INVARIANT: confirmationToken MUST be top-level on suggestedAction, NOT in details!
        assert "confirmationToken" in sa
        token = sa["confirmationToken"]
        assert token.startswith("tok_mail_")
        assert "confirmationToken" not in sa["details"]

        # INVARIANT: confirmationToken MUST NOT be leaked in the user-visible message text!
        assert token not in res["content"]

        # Details must be clean and user-facing
        assert sa["details"]["to"] == "advisor@university.edu"
        assert "thesis feedback" in sa["details"]["subject"].lower()

@pytest.mark.asyncio
async def test_gmail_send_token_expiry_enforced(db_session, test_user):
    proposal = google_gmail_service.prepare_send_confirmation(
        user_id=test_user.id,
        to="prof@university.edu",
        subject="Important",
        body="Body"
    )
    token = proposal["confirmationToken"]

    # Artificially age the token past 15 minutes (900 seconds)
    google_gmail_service._send_confirmations[token]["created_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=901)
    )

    with pytest.raises(Exception) as excinfo:
        await google_gmail_service.send_email_confirmed(
            user_id=test_user.id,
            db=db_session,
            confirmation_token=token
        )
    assert "expired" in str(excinfo.value).lower()

# =====================================================================
# 4. PLAN ADD TASK & DELETE TASK VIA AI ASSISTANT
# =====================================================================

@pytest.mark.asyncio
async def test_plan_add_task_via_agent(db_session, test_user):
    plan = Plan(user_id=test_user.id, title="30-Day Java Plan", period="30 Days")
    db_session.add(plan)
    db_session.commit()

    conv = Conversation(user_id=test_user.id, title="Plan Add Task")
    db_session.add(conv)
    db_session.commit()

    res = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Add a new task 'Dynamic Programming Practice' for 90 minutes to my study plan",
        conversation_id=conv.id,
        db=db_session
    )

    assert "Dynamic Programming Practice" in res["content"]
    assert "90 mins" in res["content"] or "90 minutes" in res["content"]

    # Verify persistent database insertion
    task = db_session.query(PlanTask).filter(PlanTask.plan_id == plan.id, PlanTask.title == "Dynamic Programming Practice").first()
    assert task is not None
    assert task.duration_minutes == 90
    assert task.completed is False

@pytest.mark.asyncio
async def test_plan_delete_task_via_agent(db_session, test_user):
    plan = Plan(user_id=test_user.id, title="30-Day Java Plan", period="30 Days")
    db_session.add(plan)
    db_session.commit()

    task = PlanTask(
        plan_id=plan.id,
        title="Dynamic Programming Practice",
        duration_minutes=90
    )
    db_session.add(task)
    db_session.commit()

    conv = Conversation(user_id=test_user.id, title="Plan Delete Task")
    db_session.add(conv)
    db_session.commit()

    res = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Delete the task 'Dynamic Programming Practice' from my study plan",
        conversation_id=conv.id,
        db=db_session
    )

    assert "removed from your study plan" in res["content"]
    remaining = db_session.query(PlanTask).filter(PlanTask.id == task.id).first()
    assert remaining is None

# =====================================================================
# 5. DISCONNECTED GMAIL & DRIVE RETURN 400 (NO DUMMY DATA)
# =====================================================================

def test_disconnected_gmail_endpoint_returns_400_no_dummy_data(client, auth_headers):
    # No OAuth record attached
    res = client.get("/api/gmail/messages", headers=auth_headers)
    assert res.status_code == 400
    assert "not connected" in res.json()["detail"].lower()
    # Ensure fake Vance / registrar data is never returned
    assert "gm_01" not in res.text
    assert "Prof. Vance" not in res.text

def test_disconnected_drive_endpoint_returns_400_no_dummy_data(client, auth_headers):
    # No OAuth record attached
    res = client.get("/api/drive/files", headers=auth_headers)
    assert res.status_code == 400
    assert "not connected" in res.json()["detail"].lower()
    # Ensure fake drv_01 / drv_02 data is never returned
    assert "drv_01" not in res.text
    assert "MSc_Thesis_Proposal" not in res.text

# =====================================================================
# 6. ROBUST LLM STRUCTURED OUTPUT HANDLING FOR PLANS & CALENDAR
# =====================================================================

@pytest.mark.asyncio
async def test_plan_create_with_string_hours_and_subject_in_title(db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Robust Plan Create")
    db_session.add(conv)
    db_session.commit()

    # Mock Gemini intent classification returning title containing Java and DSA and string hours
    mock_classified = {
        "tool": "plan_create",
        "args": {
            "title": "30-Day Java and DSA Intensive",
            "period": "30 Days",
            "daily_hours": "3.5 hours"
        }
    }
    with patch("app.agent.graph.classify_intent_with_gemini", AsyncMock(return_value=mock_classified)):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Create a 30-day Java and DSA study plan with 3.5 hours daily",
            conversation_id=conv.id,
            db=db_session
        )

    assert "30-Day Java and DSA Intensive" in res["content"]
    assert "3.5 hours daily" in res["content"]
    # Check that Java & DSA tasks were generated
    plan = db_session.query(Plan).filter(Plan.user_id == test_user.id, Plan.title == "30-Day Java and DSA Intensive").first()
    assert plan is not None
    tasks = db_session.query(PlanTask).filter(PlanTask.plan_id == plan.id).all()
    assert len(tasks) >= 6
    assert any("OOP" in t.title for t in tasks)
    assert tasks[0].duration_minutes == int(3.5 * 60)

@pytest.mark.asyncio
async def test_plan_update_with_string_hours(db_session, test_user):
    plan = Plan(user_id=test_user.id, title="Active Plan", period="Sprint")
    db_session.add(plan)
    db_session.commit()
    t1 = PlanTask(plan_id=plan.id, title="Task 1", duration_minutes=180, completed=False)
    db_session.add(t1)
    db_session.commit()

    conv = Conversation(user_id=test_user.id, title="Robust Plan Update")
    db_session.add(conv)
    db_session.commit()

    mock_classified = {
        "tool": "plan_update",
        "args": {
            "daily_hours": "2 hours"
        }
    }
    with patch("app.agent.graph.classify_intent_with_gemini", AsyncMock(return_value=mock_classified)):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="I can only study two hours daily now. Update my plan.",
            conversation_id=conv.id,
            db=db_session
        )

    assert "2 hours daily" in res["content"]
    db_session.refresh(t1)
    assert t1.duration_minutes == 120

@pytest.mark.asyncio
async def test_plan_delete_by_title_match(db_session, test_user):
    p1 = Plan(user_id=test_user.id, title="Python Basics", period="10 Days")
    p2 = Plan(user_id=test_user.id, title="Java & DSA Mastery", period="30 Days")
    db_session.add_all([p1, p2])
    db_session.commit()

    conv = Conversation(user_id=test_user.id, title="Plan Delete Specific")
    db_session.add(conv)
    db_session.commit()

    mock_classified = {
        "tool": "plan_delete",
        "args": {
            "title": "Python Basics",
            "confirmed": False
        }
    }
    with patch("app.agent.graph.classify_intent_with_gemini", AsyncMock(return_value=mock_classified)):
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Delete my Python Basics plan",
            conversation_id=conv.id,
            db=db_session
        )

    assert res["suggestedAction"] is not None
    assert res["suggestedAction"]["details"]["planTitle"] == "Python Basics"
    assert res["suggestedAction"]["details"]["planId"] == p1.id

