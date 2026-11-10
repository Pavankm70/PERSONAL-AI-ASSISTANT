import pytest
from datetime import datetime, timezone, timedelta
from app.services.date_parser import parse_natural_datetime, parse_natural_time, parse_natural_duration_minutes

def test_parse_tomorrow_at_3pm():
    ref = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    start_dt, end_dt, meta = parse_natural_datetime("Schedule meeting tomorrow at 3 PM", reference_dt=ref)
    
    assert start_dt.year == 2026
    assert start_dt.month == 10
    assert start_dt.day == 27 # Tomorrow
    assert start_dt.hour == 15 # 3 PM
    assert start_dt.minute == 0
    assert end_dt == start_dt + timedelta(hours=1)
    assert meta["durationMinutes"] == 60

def test_parse_today_at_10_30am():
    ref = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    start_dt, end_dt, meta = parse_natural_datetime("Focus block today at 10:30 am for 45 mins", reference_dt=ref)

    assert start_dt.day == 26
    assert start_dt.hour == 10
    assert start_dt.minute == 30
    assert meta["durationMinutes"] == 45
    assert end_dt == start_dt + timedelta(minutes=45)

def test_parse_weekday_next_friday():
    ref = datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc) # Monday
    start_dt, end_dt, meta = parse_natural_datetime("Lab sync on Friday at 2 PM", reference_dt=ref)

    assert start_dt.weekday() == 4 # Friday
    assert start_dt.hour == 14
    assert meta["dateType"] == "weekday_friday"

def test_parse_iso_string_safely():
    iso_query = "2026-11-15T14:30:00Z"
    start_dt, end_dt, meta = parse_natural_datetime(iso_query)

    assert start_dt.year == 2026
    assert start_dt.month == 11
    assert start_dt.day == 15
    assert start_dt.hour == 14
    assert start_dt.minute == 30

def test_parse_natural_duration_patterns():
    assert parse_natural_duration_minutes("for 90 mins") == 90
    assert parse_natural_duration_minutes("for 2 hours") == 120
    assert parse_natural_duration_minutes("for half an hour") == 30
    assert parse_natural_duration_minutes("for an hour") == 60
    assert parse_natural_duration_minutes("regular study session") == 60 # default
