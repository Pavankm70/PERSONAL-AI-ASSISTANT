import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import httpx
from fastapi import status

from app.db.models import User, OAuthAccount, IntegrationConnection
from app.services.google_oauth.crypto import token_cipher
from app.services.google_services.gmail_service import google_gmail_service
from app.services.google_services.calendar_service import google_calendar_service
from app.services.google_services.drive_service import google_drive_service
from app.agent.graph import agent_orchestrator

_RealAsyncClient = httpx.AsyncClient

@pytest.fixture
def user_a(db_session):
    u = User(
        id="usr_alice_101",
        email="alice@university.edu",
        full_name="Alice User",
        onboarding_complete=True
    )
    db_session.add(u)
    db_session.commit()
    return u

@pytest.fixture
def user_b(db_session):
    u = User(
        id="usr_bob_202",
        email="bob@university.edu",
        full_name="Bob User",
        onboarding_complete=True
    )
    db_session.add(u)
    db_session.commit()
    return u

@pytest.fixture
def user_a_creds(db_session, user_a):
    acc_gmail = OAuthAccount(
        user_id=user_a.id,
        provider="gmail",
        encrypted_access_token=token_cipher.encrypt("alice_gmail_valid_token"),
        encrypted_refresh_token=token_cipher.encrypt("alice_refresh_token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    acc_cal = OAuthAccount(
        user_id=user_a.id,
        provider="calendar",
        encrypted_access_token=token_cipher.encrypt("alice_cal_valid_token"),
        encrypted_refresh_token=token_cipher.encrypt("alice_cal_refresh_token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    acc_drive = OAuthAccount(
        user_id=user_a.id,
        provider="drive",
        encrypted_access_token=token_cipher.encrypt("alice_drive_valid_token"),
        encrypted_refresh_token=token_cipher.encrypt("alice_drive_refresh_token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    db_session.add_all([acc_gmail, acc_cal, acc_drive])
    db_session.commit()

# ==========================================
# 1. GMAIL SERVICE TESTS (Mocked Google API)
# ==========================================

@pytest.mark.asyncio
async def test_gmail_list_and_get_messages(db_session, user_a, user_a_creds):
    mock_list_response = {
        "messages": [
            {"id": "msg_001", "threadId": "th_001"},
            {"id": "msg_002", "threadId": "th_002"}
        ],
        "nextPageToken": "next_token_123"
    }
    mock_detail_response = {
        "id": "msg_001",
        "threadId": "th_001",
        "snippet": "Meeting with research advisors tomorrow.",
        "payload": {
            "headers": [
                {"name": "From", "value": "Prof. Vance <vance@university.edu>"},
                {"name": "Subject", "value": "Thesis Methodology Notes"},
                {"name": "Date", "value": "Sun, 25 Oct 2026 10:00:00 GMT"}
            ]
        },
        "labelIds": ["INBOX", "IMPORTANT"]
    }

    async def mock_handler(request: httpx.Request):
        url = str(request.url)
        if "messages/msg_001" in url:
            return httpx.Response(200, json=mock_detail_response)
        elif "messages" in url:
            return httpx.Response(200, json=mock_list_response)
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _RealAsyncClient(transport=transport)):
        res = await google_gmail_service.list_messages(user_id=user_a.id, db=db_session)
        assert len(res["messages"]) >= 1
        msg = res["messages"][0]
        assert msg["fromEmail"] == "vance@university.edu"
        assert msg["subject"] == "Thesis Methodology Notes"
        assert msg["isImportant"] is True

@pytest.mark.asyncio
async def test_gmail_create_draft(db_session, user_a, user_a_creds):
    mock_draft_res = {
        "id": "draft_789",
        "message": {"id": "msg_draft_789"}
    }

    async def mock_handler(request: httpx.Request):
        assert request.method == "POST"
        assert "drafts" in str(request.url)
        return httpx.Response(200, json=mock_draft_res)

    transport = httpx.MockTransport(mock_handler)
    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _RealAsyncClient(transport=transport)):
        res = await google_gmail_service.create_draft(
            user_id=user_a.id,
            db=db_session,
            to="advisor@university.edu",
            subject="Proposal Review",
            body="Attached is the benchmark evaluation."
        )
        assert res["draftId"] == "draft_789"
        assert res["status"] == "draft_created"

@pytest.mark.asyncio
async def test_gmail_send_requires_confirmation(db_session, user_a, user_a_creds):
    proposal = google_gmail_service.prepare_send_confirmation(
        user_id=user_a.id,
        to="dean@university.edu",
        subject="Scholarship Application",
        body="Submitting my application materials."
    )
    token = proposal["confirmationToken"]
    assert token.startswith("tok_mail_")
    assert proposal["requiresConfirmation"] is True

    # Sending with bad token fails
    with pytest.raises(Exception):
        await google_gmail_service.send_email_confirmed(
            user_id=user_a.id,
            db=db_session,
            confirmation_token="invalid_token_xyz"
        )

    # Sending with valid confirmation token succeeds
    async def mock_handler(request: httpx.Request):
        assert "messages/send" in str(request.url)
        return httpx.Response(200, json={"id": "sent_001", "threadId": "th_sent"})

    transport = httpx.MockTransport(mock_handler)
    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _RealAsyncClient(transport=transport)):
        sent_res = await google_gmail_service.send_email_confirmed(
            user_id=user_a.id,
            db=db_session,
            confirmation_token=token
        )
        assert sent_res["sent"] is True
        assert sent_res["messageId"] == "sent_001"

# ============================================
# 2. CALENDAR SERVICE TESTS (Mocked Google API)
# ============================================

@pytest.mark.asyncio
async def test_calendar_list_and_conflict_check(db_session, user_a, user_a_creds):
    mock_events = {
        "items": [
            {
                "id": "cal_ev_1",
                "summary": "MSc Distributed Systems",
                "start": {"dateTime": "2026-10-26T14:00:00Z"},
                "end": {"dateTime": "2026-10-26T16:00:00Z"},
                "location": "Lab 4"
            }
        ]
    }

    async def mock_handler(request: httpx.Request):
        return httpx.Response(200, json=mock_events)

    transport = httpx.MockTransport(mock_handler)
    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _RealAsyncClient(transport=transport)):
        res = await google_calendar_service.list_events(user_id=user_a.id, db=db_session)
        assert len(res["events"]) == 1
        assert res["events"][0]["title"] == "MSc Distributed Systems"

        # Check availability with overlapping slot (14:30 - 15:30)
        target_start = datetime.fromisoformat("2026-10-26T14:30:00+00:00")
        target_end = datetime.fromisoformat("2026-10-26T15:30:00+00:00")
        avail = await google_calendar_service.check_availability(user_a.id, db_session, target_start, target_end)
        assert avail["hasConflict"] is True
        assert len(avail["conflicts"]) == 1

@pytest.mark.asyncio
async def test_calendar_event_confirmed_creation(db_session, user_a, user_a_creds):
    async def mock_handler(request: httpx.Request):
        url = str(request.url)
        if request.method == "POST" and "events" in url:
            return httpx.Response(200, json={
                "id": "new_ev_555",
                "summary": "Deep Learning Study Block",
                "start": {"dateTime": "2026-10-26T16:30:00Z"},
                "end": {"dateTime": "2026-10-26T18:00:00Z"},
                "htmlLink": "https://calendar.google.com/event"
            })
        elif "events" in url:
            return httpx.Response(200, json={"items": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _RealAsyncClient(transport=transport)):
        proposal = await google_calendar_service.prepare_event_proposal(
            user_id=user_a.id,
            db=db_session,
            title="Deep Learning Study Block",
            start_time="2026-10-26T16:30:00Z",
            end_time="2026-10-26T18:00:00Z",
            location="Quiet Area"
        )
        token = proposal["confirmationToken"]
        assert token.startswith("tok_cal_")

        created = await google_calendar_service.create_event_confirmed(
            user_id=user_a.id,
            db=db_session,
            confirmation_token=token
        )
        assert created["created"] is True
        assert created["id"] == "new_ev_555"

# =========================================
# 3. DRIVE SERVICE TESTS (Mocked Google API)
# =========================================

@pytest.mark.asyncio
async def test_drive_search_and_export(db_session, user_a, user_a_creds):
    mock_files = {
        "files": [
            {
                "id": "file_doc_1",
                "name": "Thesis_Draft.gdoc",
                "mimeType": "application/vnd.google-apps.document",
                "modifiedTime": "2026-10-25T08:00:00Z",
                "webViewLink": "https://docs.google.com/doc_1"
            }
        ]
    }

    async def mock_handler(request: httpx.Request):
        url = str(request.url)
        if "export" in url:
            return httpx.Response(200, text="Exported plain text content of Thesis Draft.")
        elif "files/file_doc_1" in url:
            return httpx.Response(200, json=mock_files["files"][0])
        elif "files" in url:
            return httpx.Response(200, json=mock_files)
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _RealAsyncClient(transport=transport)):
        search_res = await google_drive_service.search_files(user_id=user_a.id, db=db_session, query="Thesis")
        assert len(search_res["files"]) == 1
        assert search_res["files"][0]["name"] == "Thesis_Draft.gdoc"

        content_res = await google_drive_service.read_file_content(user_id=user_a.id, db=db_session, file_id="file_doc_1")
        assert "Exported plain text content" in content_res["content"]

# =========================================
# 4. MULTI-USER TENANT ISOLATION TESTS
# =========================================

@pytest.mark.asyncio
async def test_cross_user_isolation(db_session, user_a, user_b, user_a_creds):
    # User B has no connected credentials
    with pytest.raises(Exception) as excinfo:
        await google_gmail_service.list_messages(user_id=user_b.id, db=db_session)
    assert "not connected" in str(excinfo.value).lower()

    with pytest.raises(Exception) as excinfo:
        await google_calendar_service.list_events(user_id=user_b.id, db=db_session)
    assert "not connected" in str(excinfo.value).lower()

    with pytest.raises(Exception) as excinfo:
        await google_drive_service.search_files(user_id=user_b.id, db=db_session)
    assert "not connected" in str(excinfo.value).lower()

@pytest.mark.asyncio
async def test_user_cannot_use_another_users_confirmation_token(db_session, user_a, user_b):
    proposal = google_gmail_service.prepare_send_confirmation(
        user_id=user_a.id,
        to="prof@university.edu",
        subject="Important",
        body="Secret content"
    )
    token = proposal["confirmationToken"]

    # Bob attempts to execute Alice's confirmation token
    with pytest.raises(Exception) as excinfo:
        await google_gmail_service.send_email_confirmed(
            user_id=user_b.id,
            db=db_session,
            confirmation_token=token
        )
    assert "Security violation" in str(excinfo.value) or "Forbidden" in str(excinfo.value)

# ==============================================
# 5. AGENT INTENT DISPATCH & GROUNDING TESTS
# ==============================================

@pytest.mark.asyncio
async def test_agent_drive_search_intent(db_session, user_a, user_a_creds):
    mock_files = {
        "files": [
            {
                "id": "file_prop_1",
                "name": "Project_Proposal_Final.docx",
                "mimeType": "application/vnd.google-apps.document",
                "modifiedTime": "2026-10-24T12:00:00Z",
                "webViewLink": "https://drive.google.com/file_prop_1"
            }
        ]
    }
    async def mock_handler(request: httpx.Request):
        return httpx.Response(200, json=mock_files)

    transport = httpx.MockTransport(mock_handler)
    with patch("httpx.AsyncClient", side_effect=lambda *a, **kw: _RealAsyncClient(transport=transport)):
        res = await agent_orchestrator.run(
            user_id=user_a.id,
            query="Find my project proposal in Drive",
            conversation_id="conv_101",
            db=db_session
        )
        assert len(res["citations"]) >= 1
        assert "Project_Proposal_Final.docx" in res["content"]
        assert any(t["toolName"] == "GoogleDriveSearch" for t in res["toolExecutions"])
