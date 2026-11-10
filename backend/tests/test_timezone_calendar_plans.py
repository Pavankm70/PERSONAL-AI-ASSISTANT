import pytest
from datetime import datetime, date, timezone as py_timezone
import zoneinfo
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.db.models import User, Plan, PlanTask
from app.services.date_parser import parse_natural_datetime, parse_explicit_calendar_date

def test_relative_tomorrow_at_4pm_preserves_local_wall_clock():
    """
    User requests 'tomorrow at 4 PM'.
    In any given timezone (e.g. Asia/Kolkata, America/Los_Angeles, Europe/London),
    the returned datetime hour MUST be strictly 16:00 local wall-clock time.
    It must not shift to 7 PM or midnight.
    """
    timezones_to_test = [
        "Asia/Kolkata",
        "America/Los_Angeles",
        "America/New_York",
        "Europe/London",
        "Asia/Tokyo",
        "UTC"
    ]

    for tz_str in timezones_to_test:
        start_dt, end_dt, meta = parse_natural_datetime(
            query="Schedule a meeting tomorrow at 4 PM for one hour",
            user_tz_str=tz_str
        )
        # Wall clock hour must be 16 (4 PM)
        assert start_dt.hour == 16, f"Failed for {tz_str}: expected hour 16, got {start_dt.hour}"
        assert start_dt.minute == 0
        assert end_dt.hour == 17, f"Failed for {tz_str}: expected hour 17, got {end_dt.hour}"
        assert end_dt.minute == 0
        assert meta["durationMinutes"] == 60
        assert meta["timezone"] == tz_str

def test_all_day_dates_strictly_format_without_utc_hour_shift():
    """
    All-day event dates must resolve to exact YYYY-MM-DD date representation
    without timezone shifting changing the day.
    """
    ref = date(2026, 10, 27)
    parsed = parse_explicit_calendar_date("October 28, 2026", ref_date=ref)
    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.month == 10
    assert parsed.day == 28
    assert parsed.isoformat() == "2026-10-28"

def test_calendar_endpoint_returns_no_mock_data_when_disconnected(client: TestClient, auth_headers: dict):
    """
    When Google Calendar is not connected, the endpoint must raise 400
    and never return fake events (ev_01, ev_02).
    """
    res = client.get("/api/calendar/events", headers=auth_headers)
    assert res.status_code == 400
    assert "Google Calendar is not connected" in res.json()["detail"]

def test_deleting_calendar_event_clears_task_reference_without_deleting_task(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    test_user: User
):
    """
    Deleting a calendar event unlinks the google_calendar_event_id on a PlanTask,
    preserving the study task itself.
    """
    plan = Plan(user_id=test_user.id, title="Linked Task Plan", period="Sprint")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    task = PlanTask(
        plan_id=plan.id,
        title="Linked Study Session",
        duration_minutes=60,
        google_calendar_event_id="ev_linked_999"
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    # Delete calendar event
    del_res = client.delete("/api/calendar/events/ev_linked_999", headers=auth_headers)
    assert del_res.status_code == 200

    # Task still exists in database, but google_calendar_event_id is cleared
    db_session.refresh(task)
    assert task.title == "Linked Study Session"
    assert task.google_calendar_event_id is None
