"""
Regression tests for Calendar Intent Routing — Issue #9
Tests the five target queries from the Calendar Intent Routing Bug report.

Rules verified:
  Q1: "Today I have quiz at 10 PM deep learning so mark in Google Calendar as event"
      → calendar_propose_event  (title contains "Deep Learning Quiz")
  Q2: "Add DL quiz to my calendar today at 10 PM"
      → calendar_propose_event  (title contains "DL Quiz")
  Q3: "Show my calendar events today"
      → calendar_events_retrieval
  Q4: "Move my Deep Learning Quiz to tomorrow at 7 PM"
      → calendar_update_event
  Q5: "Cancel my Deep Learning Quiz"
      → calendar_delete_event
"""

import pytest
import httpx
from unittest.mock import patch, AsyncMock

from app.agent.graph import (
    heuristic_classify_intent,
    is_calendar_create_intent,
    is_calendar_view_intent,
    extract_calendar_event_title,
    agent_orchestrator,
)
from app.db.models import Conversation, OAuthAccount
from app.services.google_oauth.crypto import token_cipher
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Unit tests — heuristic_classify_intent (synchronous, no DB needed)
# ---------------------------------------------------------------------------

class TestCalendarCreateIntentDetection:
    """is_calendar_create_intent must return True for creation phrases."""

    def test_mark_in_google_calendar_as_event(self):
        q = "Today I have quiz at 10 PM deep learning so mark in Google Calendar as event"
        assert is_calendar_create_intent(q), "Should detect 'mark in Google Calendar as event' as CREATE"

    def test_add_to_calendar(self):
        q = "Add DL quiz to my calendar today at 10 PM"
        assert is_calendar_create_intent(q), "Should detect 'add ... to my calendar' as CREATE"

    def test_add_to_google_calendar(self):
        q = "Add my meeting to Google Calendar"
        assert is_calendar_create_intent(q), "Should detect 'add ... to Google Calendar' as CREATE"

    def test_schedule_phrase(self):
        assert is_calendar_create_intent("Schedule a meeting tomorrow at 3 PM")

    def test_put_on_calendar(self):
        assert is_calendar_create_intent("Put my dentist appointment on the calendar")

    def test_create_event(self):
        assert is_calendar_create_intent("Create an event for my project demo on Friday")


class TestCalendarViewIntentDetection:
    """is_calendar_view_intent must return True for read-only phrases and
       False when the phrase is actually a creation request."""

    def test_show_calendar_events(self):
        q = "Show my calendar events today"
        assert is_calendar_view_intent(q), "Should detect 'show my calendar events' as VIEW"

    def test_what_is_on_calendar(self):
        assert is_calendar_view_intent("What is on my calendar tomorrow?")

    def test_list_events(self):
        assert is_calendar_view_intent("List my events for this week")

    def test_create_does_not_match_view(self):
        """Creation phrase must NOT be classified as view."""
        q = "Add DL quiz to my calendar today at 10 PM"
        assert not is_calendar_view_intent(q), "CREATE phrase must return False from is_calendar_view_intent"

    def test_mark_in_google_calendar_does_not_match_view(self):
        q = "Today I have quiz at 10 PM deep learning so mark in Google Calendar as event"
        assert not is_calendar_view_intent(q)


class TestExtractCalendarEventTitle:
    """Title extractor must return sensible titles for all five target queries."""

    def test_q1_deep_learning_quiz(self):
        q = "Today I have quiz at 10 PM deep learning so mark in Google Calendar as event"
        title = extract_calendar_event_title(q)
        assert "deep learning" in title.lower() or "quiz" in title.lower(), \
            f"Expected 'deep learning' or 'quiz' in title, got: '{title}'"

    def test_q2_dl_quiz(self):
        q = "Add DL quiz to my calendar today at 10 PM"
        title = extract_calendar_event_title(q)
        assert "dl" in title.lower() or "quiz" in title.lower(), \
            f"Expected 'DL' or 'Quiz' in title, got: '{title}'"

    def test_acronym_preserved(self):
        """DL, ML, AI should NOT be lowercased by title-casing."""
        q = "Add ML exam to my calendar tomorrow"
        title = extract_calendar_event_title(q)
        assert "ML" in title, f"Acronym 'ML' should be preserved, got: '{title}'"


class TestHeuristicClassifyIntent:
    """Full heuristic routing — verifies all five target queries."""

    def test_q1_routes_to_propose(self):
        result = heuristic_classify_intent(
            "Today I have quiz at 10 PM deep learning so mark in Google Calendar as event"
        )
        assert result["tool"] == "calendar_propose_event", \
            f"Q1 should route to calendar_propose_event, got: {result['tool']}"
        title = result["args"].get("title", "")
        assert "deep learning" in title.lower() or "quiz" in title.lower(), \
            f"Q1 title should reference 'deep learning' or 'quiz', got: '{title}'"

    def test_q2_routes_to_propose(self):
        result = heuristic_classify_intent("Add DL quiz to my calendar today at 10 PM")
        assert result["tool"] == "calendar_propose_event", \
            f"Q2 should route to calendar_propose_event, got: {result['tool']}"

    def test_q3_routes_to_retrieval(self):
        result = heuristic_classify_intent("Show my calendar events today")
        assert result["tool"] == "calendar_events_retrieval", \
            f"Q3 should route to calendar_events_retrieval, got: {result['tool']}"

    def test_q4_routes_to_update(self):
        result = heuristic_classify_intent("Move my Deep Learning Quiz to tomorrow at 7 PM")
        assert result["tool"] == "calendar_update_event", \
            f"Q4 should route to calendar_update_event, got: {result['tool']}"

    def test_q5_routes_to_delete(self):
        result = heuristic_classify_intent("Cancel my Deep Learning Quiz")
        assert result["tool"] == "calendar_delete_event", \
            f"Q5 should route to calendar_delete_event, got: {result['tool']}"

    def test_q1_does_not_route_to_retrieval(self):
        """The primary regression guard: creation phrase must NOT fall through to retrieval."""
        result = heuristic_classify_intent(
            "Today I have quiz at 10 PM deep learning so mark in Google Calendar as event"
        )
        assert result["tool"] != "calendar_events_retrieval", \
            "REGRESSION: Q1 fell through to calendar_events_retrieval (the original bug)"

    def test_q2_does_not_route_to_retrieval(self):
        result = heuristic_classify_intent("Add DL quiz to my calendar today at 10 PM")
        assert result["tool"] != "calendar_events_retrieval", \
            "REGRESSION: Q2 fell through to calendar_events_retrieval"


# ---------------------------------------------------------------------------
# Integration tests — agent orchestrator (force heuristic routing via mock)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calendar_create_returns_confirm_card_not_list(db_session, test_user):
    """Creation request must return suggestedAction with actionType='create_event',
    NOT a plain list of calendar events."""
    conv = Conversation(user_id=test_user.id, title="Calendar Create Regression")
    db_session.add(conv)
    db_session.commit()

    # Attach a dummy OAuth account so Calendar capability is enabled
    acc = OAuthAccount(
        user_id=test_user.id,
        provider="calendar",
        encrypted_access_token=token_cipher.encrypt("fake_access_token"),
        encrypted_refresh_token=token_cipher.encrypt("fake_refresh_token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(acc)
    db_session.commit()

    with patch("app.core.config.settings.GEMINI_API_KEY", ""):
        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_instance.get = AsyncMock(
                return_value=httpx.Response(200, json={"items": []})
            )
            mock_client_instance.post = AsyncMock(
                return_value=httpx.Response(200, json={"id": "evt123", "summary": "Deep Learning Quiz"})
            )
            MockClient.return_value = mock_client_instance

            res = await agent_orchestrator.run(
                user_id=test_user.id,
                query="Today I have quiz at 10 PM deep learning so mark in Google Calendar as event",
                conversation_id=conv.id,
                db=db_session,
            )

    sa = res.get("suggestedAction")
    assert sa is not None, "Response must include suggestedAction (confirmation card) for creation request"
    assert sa.get("actionType") == "create_event", \
        f"Expected actionType='create_event', got: {sa.get('actionType')}"
    assert sa.get("status") == "pending", \
        "Event must be pending (not yet written to calendar)"
    assert sa.get("confirmationToken") is not None, \
        "confirmationToken must be present at top level"

    # confirmationToken must NOT leak into user-facing details
    details = sa.get("details", {})
    assert "confirmationToken" not in details, \
        "confirmationToken must NOT be inside details (would expose internal token)"

    # Must NOT have returned a calendar event list as the final answer
    diagnostics = res.get("diagnostics", {})
    assert diagnostics.get("selectedTool") != "calendar_events_retrieval", \
        "REGRESSION: selected tool was calendar_events_retrieval (original bug)"


@pytest.mark.asyncio
async def test_calendar_create_does_not_write_before_approval(db_session, test_user):
    """No POST to Google Calendar must happen until the user clicks Confirm."""
    conv = Conversation(user_id=test_user.id, title="No Pre-Write Test")
    db_session.add(conv)
    db_session.commit()

    acc = OAuthAccount(
        user_id=test_user.id,
        provider="calendar",
        encrypted_access_token=token_cipher.encrypt("fake_access_token"),
        encrypted_refresh_token=token_cipher.encrypt("fake_refresh_token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(acc)
    db_session.commit()

    post_calls = []

    with patch("app.core.config.settings.GEMINI_API_KEY", ""):
        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_instance.get = AsyncMock(
                return_value=httpx.Response(200, json={"items": []})
            )

            async def track_post(*args, **kwargs):
                post_calls.append((args, kwargs))
                return httpx.Response(200, json={"id": "x"})

            mock_client_instance.post = AsyncMock(side_effect=track_post)
            MockClient.return_value = mock_client_instance

            res = await agent_orchestrator.run(
                user_id=test_user.id,
                query="Add DL quiz to my calendar today at 10 PM",
                conversation_id=conv.id,
                db=db_session,
            )

    sa = res.get("suggestedAction")
    assert sa is not None
    assert sa.get("status") == "pending"
    assert len(post_calls) == 0, \
        f"Calendar write (POST) must NOT occur before user confirms. Got {len(post_calls)} POST call(s)."

