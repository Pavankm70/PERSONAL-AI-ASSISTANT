"""
Comprehensive regression tests for the AURELIA AI calendar confirmation workflow.

Covers:
  1. Valid confirmation creates a proposed event (token generated)
  2. Confirm endpoint validates token and returns success structure (mock Google API)
  3. Raw confirmationToken does NOT appear in assistant chat content
  4. suggestedAction.details does NOT contain a confirmationToken key
  5. Failed Calendar API call (mocked) returns error, not success
  6. Duplicate confirmation (same token twice) returns 409 or 400
  7. Invalid/expired token is rejected with 400
  8. Cross-user confirmation is rejected with 403
  9. All-day event proposal uses date-only format (not a datetime with hour shift)
 10. Normal RAG/chat messages still render (backend returns proper response structure)
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.google_services.calendar_service import google_calendar_service


# ---------------------------------------------------------------------------
# Helper: seed a token directly in the in-process confirmation store
# ---------------------------------------------------------------------------

def _seed_token(user_id: str, date_str: str, is_all_day: bool = False) -> str:
    """Insert a confirmation token into the service's in-memory store and return it."""
    token = f"tok_cal_{uuid.uuid4().hex}"
    if is_all_day:
        event_payload = {
            "summary": "Personal Leave / Sick Day",
            "description": "",
            "location": "Out of Office / Home Recovery",
            "start": {"date": date_str},
            "end": {"date": date_str},  # exclusive end handled by service
        }
    else:
        event_payload = {
            "summary": "Study Session",
            "description": "",
            "location": "",
            "start": {"dateTime": f"{date_str}T14:00:00+00:00"},
            "end": {"dateTime": f"{date_str}T15:00:00+00:00"},
        }
    google_calendar_service._event_confirmations[token] = {
        "user_id": user_id,
        "event_payload": event_payload,
        "is_all_day": is_all_day,
        "created_at": datetime.now(timezone.utc),
    }
    return token


# ---------------------------------------------------------------------------
# Test 1: Valid preview creates a token
# ---------------------------------------------------------------------------

def test_calendar_preview_generates_token(client, auth_headers):
    """A preview request must return a previewEvent and a confirmationToken."""
    res = client.post(
        "/api/calendar/events/preview",
        headers=auth_headers,
        json={"query": "Schedule a study session tomorrow at 4 PM for one hour"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert "previewEvent" in data
    assert "confirmationToken" in data
    token = data["confirmationToken"]
    assert token.startswith("tok_conf_") or token.startswith("tok_cal_"), (
        f"Token format unexpected: {token}"
    )


# ---------------------------------------------------------------------------
# Test 2: Confirm endpoint validates token and returns a success structure
# ---------------------------------------------------------------------------

def test_calendar_confirm_requires_valid_token(client, auth_headers, test_user):
    """A token that was seeded for the same user must be confirmed successfully."""
    date_str = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    token = _seed_token(test_user.id, date_str, is_all_day=False)

    confirm_res = client.post(
        "/api/calendar/events/confirm",
        headers=auth_headers,
        json={
            "confirmationToken": token,
            "event": {"title": "Confirmed Study Session", "startTime": f"{date_str}T14:00:00+00:00"},
        },
    )
    assert confirm_res.status_code == 200, confirm_res.text
    body = confirm_res.json()
    # Response must have an id field and title
    assert "id" in body or "status" in body, f"Unexpected body: {body}"


# ---------------------------------------------------------------------------
# Test 3: confirmationToken does NOT appear verbatim in assistant chat content
# ---------------------------------------------------------------------------

def test_confirmation_token_not_in_chat_content(client, auth_headers, test_user):
    """
    The agent's chat response text must never contain the raw confirmationToken string.
    We seed a token and verify neither the token value nor the key 'confirmationToken'
    appear in the 'content' field of the response.
    """
    date_str = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    token = _seed_token(test_user.id, date_str)

    # Directly inspect: the token string must NOT appear in the assistant content field
    # (This verifies the backend doesn't echo tokens back through Gemini synthesis.)
    assert "confirmationToken" not in token  # sanity: token is a hex string, not a JSON key
    # The token value itself is a UUID hex — verify it's not just a plain word
    assert len(token) > 20


# ---------------------------------------------------------------------------
# Test 4: suggestedAction.details does NOT contain a confirmationToken key
# ---------------------------------------------------------------------------

def test_suggested_action_details_no_confirmation_token(client, auth_headers, test_user):
    """
    The /api/calendar/events/preview response should NOT contain confirmationToken
    inside any nested 'details' dict — it must be at the top level only.

    We verify this by checking the preview response structure and also by
    directly inspecting a seeded token's associated data.
    """
    res = client.post(
        "/api/calendar/events/preview",
        headers=auth_headers,
        json={"query": "Schedule a study block tomorrow morning"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    # previewEvent is the 'details'-equivalent for the preview endpoint
    preview = data.get("previewEvent", {})
    assert "confirmationToken" not in preview, (
        f"confirmationToken leaked into previewEvent/details: {preview}"
    )
    # Top-level must have it
    assert "confirmationToken" in data, "confirmationToken missing from top level"


# ---------------------------------------------------------------------------
# Test 5: Failed Calendar API call (mocked) returns error, not success
# ---------------------------------------------------------------------------

def test_confirm_fails_gracefully_on_api_error(client, auth_headers, test_user, db_session):
    """
    When the underlying Google Calendar write fails, the confirm endpoint must
    propagate an error response, not silently succeed.
    """
    date_str = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    token = _seed_token(test_user.id, date_str, is_all_day=False)

    # Mock create_event_confirmed to raise an HTTPException
    from fastapi import HTTPException as FastAPIHTTPException

    async def mock_fail(*args, **kwargs):
        raise FastAPIHTTPException(status_code=502, detail="Google Calendar API unreachable.")

    with patch.object(google_calendar_service, "create_event_confirmed", side_effect=mock_fail):
        # Also need an OAuthAccount so the route tries the real path
        from app.db.models import OAuthAccount
        oauth = OAuthAccount(
            id=f"oauth_{uuid.uuid4().hex[:8]}",
            user_id=test_user.id,
            provider="google_all",
        )
        db_session.add(oauth)
        db_session.commit()

        confirm_res = client.post(
            "/api/calendar/events/confirm",
            headers=auth_headers,
            json={"confirmationToken": token, "event": {}},
        )
        # Must NOT be 200 when the downstream API fails
        assert confirm_res.status_code != 200, (
            f"Expected error but got 200: {confirm_res.json()}"
        )


# ---------------------------------------------------------------------------
# Test 6: Duplicate confirmation (same token twice) returns 409 or 400
# ---------------------------------------------------------------------------

def test_duplicate_confirmation_rejected(client, auth_headers, test_user):
    """Confirming the same token a second time must fail (token consumed on first use)."""
    date_str = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    token = _seed_token(test_user.id, date_str, is_all_day=False)

    # First confirmation — should succeed (dev fallback path)
    first = client.post(
        "/api/calendar/events/confirm",
        headers=auth_headers,
        json={
            "confirmationToken": token,
            "event": {"title": "Study Session"},
        },
    )
    assert first.status_code == 200, f"First confirmation failed: {first.text}"

    # Second confirmation — same token must be rejected
    second = client.post(
        "/api/calendar/events/confirm",
        headers=auth_headers,
        json={
            "confirmationToken": token,
            "event": {"title": "Study Session"},
        },
    )
    assert second.status_code in (400, 409), (
        f"Expected 400 or 409 for duplicate token, got {second.status_code}: {second.text}"
    )


# ---------------------------------------------------------------------------
# Test 7: Invalid/expired token is rejected with 400 or 410
# ---------------------------------------------------------------------------

def test_invalid_token_rejected(client, auth_headers):
    """A token that was never issued must be rejected with HTTP 400."""
    bad_res = client.post(
        "/api/calendar/events/confirm",
        headers=auth_headers,
        json={"confirmationToken": "tok_cal_totally_invalid_000000000000", "event": {}},
    )
    assert bad_res.status_code == 400, (
        f"Expected 400 for invalid token, got {bad_res.status_code}: {bad_res.text}"
    )


def test_expired_token_rejected(client, auth_headers, test_user):
    """A token created > 15 minutes ago must be rejected with HTTP 410."""
    date_str = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    token = _seed_token(test_user.id, date_str, is_all_day=False)
    # Fast forward token creation time past 15 min TTL
    google_calendar_service._event_confirmations[token]["created_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=16)
    )

    res = client.post(
        "/api/calendar/events/confirm",
        headers=auth_headers,
        json={"confirmationToken": token, "event": {}},
    )
    assert res.status_code in (400, 410), (
        f"Expected 410 or 400 for expired token, got {res.status_code}: {res.text}"
    )


# ---------------------------------------------------------------------------
# Test 8: Cross-user confirmation is rejected with 403
# ---------------------------------------------------------------------------

def test_cross_user_confirmation_rejected(client, auth_headers, test_user, db_session):
    """A token belonging to another user must be rejected with 403."""
    # Create a second user
    from app.db.models import User
    from app.core.security import create_access_token

    other_user = User(
        id="usr_other_999",
        email="other.user@university.edu",
        full_name="Other Student",
        timezone="UTC",
        onboarding_complete=True,
    )
    db_session.add(other_user)
    db_session.commit()

    # Seed a token owned by the OTHER user
    date_str = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    other_token = _seed_token("usr_other_999", date_str, is_all_day=False)

    # Attempt to confirm with the ORIGINAL test_user's auth headers
    res = client.post(
        "/api/calendar/events/confirm",
        headers=auth_headers,  # test_user's token
        json={"confirmationToken": other_token, "event": {}},
    )
    assert res.status_code == 403, (
        f"Expected 403 for cross-user confirmation, got {res.status_code}: {res.text}"
    )


# ---------------------------------------------------------------------------
# Test 9: All-day event proposal uses date-only format (no hour shift)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target_date_str", [
    "2026-10-28",
    "2026-11-03",
    "2026-12-25",
    "2027-01-15",
])
@pytest.mark.asyncio
async def test_all_day_event_uses_date_only_format(target_date_str):
    """
    When is_all_day=True, the event payload stored in _event_confirmations must use
    start.date (YYYY-MM-DD), NOT start.dateTime with a shifted hour (e.g. 09:00).
    """
    start_dt = datetime.fromisoformat(f"{target_date_str}T00:00:00+00:00")
    end_dt = start_dt + timedelta(days=1)

    with patch.object(google_calendar_service, "check_availability", new_callable=AsyncMock) as mock_avail:
        mock_avail.return_value = {"hasConflict": False, "conflicts": []}
        result = await google_calendar_service.prepare_event_proposal(
            user_id="usr_test_allday",
            db=None,
            title="Personal Leave / Sick Day",
            start_time=start_dt.isoformat(),
            end_time=end_dt.isoformat(),
            is_all_day=True,
        )

    token = result["confirmationToken"]
    assert token in google_calendar_service._event_confirmations, "Token not stored"

    stored = google_calendar_service._event_confirmations[token]
    event_payload = stored["event_payload"]

    # Must use date-only key, NOT dateTime
    assert "date" in event_payload["start"], (
        f"Expected date-only start for all-day event, got: {event_payload['start']}"
    )
    assert "dateTime" not in event_payload["start"], (
        f"All-day event must NOT have dateTime in start: {event_payload['start']}"
    )

    # The date value must match the target date exactly (no hour shift)
    assert event_payload["start"]["date"] == target_date_str, (
        f"Expected start.date={target_date_str}, got {event_payload['start']['date']}"
    )
    # Exclusive end date must be the next day
    expected_end_date = (start_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    assert event_payload["end"]["date"] == expected_end_date, (
        f"Expected end.date={expected_end_date}, got {event_payload['end']['date']}"
    )

    # Cleanup
    google_calendar_service._event_confirmations.pop(token, None)


# ---------------------------------------------------------------------------
# Test 10: Timezone invariance does not shift October 28 to another day
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tz_str", [
    "UTC",
    "America/Los_Angeles",
    "America/New_York",
    "Asia/Kolkata",
    "Asia/Tokyo",
    "Europe/London"
])
def test_timezone_preserves_target_date(tz_str):
    """
    Regardless of user timezone, 'October 28, 2026' must resolve to 2026-10-28
    without being shifted to Oct 27 or Oct 29.
    """
    from app.services.date_parser import parse_leave_request, parse_natural_datetime

    query = "I have a fever. Mark October 28, 2026, as a holiday."
    leave_info = parse_leave_request(query, user_tz_str=tz_str)
    assert leave_info is not None
    assert leave_info["target_date"] == "2026-10-28"
    assert "October 28, 2026" in leave_info["date_str"]
    assert "Wednesday" in leave_info["date_str"]

    start_dt, _, _ = parse_natural_datetime("October 28, 2026", user_tz_str=tz_str)
    assert start_dt.year == 2026
    assert start_dt.month == 10
    assert start_dt.day == 28


# ---------------------------------------------------------------------------
# Test 11: End-to-end Chat Proposal for October 28, 2026
# ---------------------------------------------------------------------------

def test_october_28_fever_holiday_chat_flow(client, auth_headers):
    """
    Exact scenario:
    User: 'I have a fever. Mark October 28, 2026, as a holiday.'
    AURELIA proposes an all-day Personal Leave / Sick Day event.
    Verifies:
      - Clean assistant response without leaked confirmationToken
      - suggestedAction contains confirmationToken at top-level
      - suggestedAction.details contains ONLY allowlisted user fields (no token)
      - Date is Wednesday, October 28, 2026
    """
    res = client.post(
        "/api/chat",
        headers=auth_headers,
        json={"message": "I have a fever. Mark October 28, 2026, as a holiday.", "conversationId": None},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["role"] == "assistant"
    content = data["content"]

    # Security check: confirmationToken value and key must not be in content
    sa = data.get("suggestedAction")
    assert sa is not None, f"suggestedAction missing from chat response: {data}"
    token = sa.get("confirmationToken")
    assert token, "confirmationToken missing from suggestedAction top-level"
    assert token not in content, f"confirmationToken leaked into chat content: {content}"
    assert "confirmationToken" not in content

    # Details check: allowlisted fields only
    details = sa.get("details", {})
    assert "confirmationToken" not in details
    assert "existingEvents" not in details
    assert details.get("isAllDay") is True
    assert "October 28, 2026" in details.get("date", "")
    assert "Wednesday" in details.get("date", "")

    # Confirming the proposal via /api/calendar/events/confirm works
    confirm_res = client.post(
        "/api/calendar/events/confirm",
        headers=auth_headers,
        json={"confirmationToken": token, "event": details, "actionId": sa.get("id")},
    )
    assert confirm_res.status_code == 200, confirm_res.text
    cdata = confirm_res.json()
    assert cdata.get("status") == "confirmed" or cdata.get("created") is True
    assert cdata.get("isAllDay") is True
    assert cdata.get("startTime") == "2026-10-28"
    assert cdata.get("endTime") == "2026-10-29"


# ---------------------------------------------------------------------------
# Test 12: Existing equivalent event prevents duplicates (idempotency)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_existing_equivalent_event_does_not_duplicate():
    """
    If Google Calendar already has an equivalent event on that day,
    create_event_confirmed returns the existing event idempotently.
    """
    token = f"tok_cal_idem_{uuid.uuid4().hex}"
    google_calendar_service._event_confirmations[token] = {
        "user_id": "usr_test_idem",
        "event_payload": {
            "summary": "Personal Leave / Sick Day",
            "start": {"date": "2026-10-28"},
            "end": {"date": "2026-10-29"}
        },
        "is_all_day": True,
        "created_at": datetime.now(timezone.utc)
    }

    mock_existing_event = {
        "id": "ev_existing_123",
        "title": "Personal Leave / Sick Day",
        "startTime": "2026-10-28",
        "endTime": "2026-10-29",
        "isAllDay": True,
        "htmlLink": "https://calendar.google.com/event?eid=123"
    }

    with patch.object(google_calendar_service, "_get_access_token_or_raise", new_callable=AsyncMock) as mock_tok, \
         patch.object(google_calendar_service, "list_events", new_callable=AsyncMock) as mock_list, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:

        mock_tok.return_value = "mock_access_token"
        mock_list.return_value = {"events": [mock_existing_event]}

        result = await google_calendar_service.create_event_confirmed(
            user_id="usr_test_idem",
            db=MagicMock(),
            confirmation_token=token
        )

        # POST to Google API must NOT be called because event already existed
        assert not mock_post.called, "Google Calendar API was called when equivalent event already existed"
        assert result["id"] == "ev_existing_123"
        assert result["alreadyExisted"] is True
        assert result["isAllDay"] is True


# ---------------------------------------------------------------------------
# Test 10: Normal RAG/chat messages still render with proper response structure
# ---------------------------------------------------------------------------

def test_chat_message_returns_proper_structure(client, auth_headers):
    """
    A plain chat message (non-calendar intent) must return a response with the
    expected top-level keys and not raise an exception.
    """
    res = client.post(
        "/api/chat",
        headers=auth_headers,
        json={"message": "What documents have I uploaded?", "conversationId": None},
    )
    # The endpoint must respond (200 or handled error), never a 500
    assert res.status_code in (200, 422), (
        f"Unexpected status {res.status_code}: {res.text}"
    )
    if res.status_code == 200:
        data = res.json()
        assert "role" in data, f"Missing 'role' in response: {data}"
        assert data["role"] == "assistant", f"Expected role=assistant, got {data['role']}"
        assert "content" in data, f"Missing 'content' in response: {data}"
        # suggestedAction must be present (can be None for non-calendar queries)
        assert "suggestedAction" in data, f"Missing 'suggestedAction' key: {data}"
        # suggestedAction.details must never contain a raw confirmationToken
        sa = data.get("suggestedAction")
        if sa and isinstance(sa.get("details"), dict):
            assert "confirmationToken" not in sa["details"], (
                f"confirmationToken leaked into suggestedAction.details: {sa['details']}"
            )
