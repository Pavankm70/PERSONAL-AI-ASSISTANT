import pytest
from app.schemas import (
    TimetableEntryItem,
    TimetableExtractionResult,
    AcademicEventItem,
    AcademicCalendarExtractionResult
)
from app.services.table_extractor import (
    _fallback_parse_timetable,
    _fallback_parse_academic_calendar,
    _clean_json_output,
    DAY_MAP,
    VALID_CATEGORIES
)

def test_clean_json_output_strips_markdown():
    raw_with_fences = "```json\n{\"document_type\": \"TIMETABLE\", \"entries\": []}\n```"
    cleaned = _clean_json_output(raw_with_fences)
    assert cleaned == "{\"document_type\": \"TIMETABLE\", \"entries\": []}"

def test_timetable_pydantic_schema_validation():
    data = {
        "document_type": "TIMETABLE",
        "entries": [
            {
                "day_of_week": "MONDAY",
                "subject_name": "Artificial Intelligence",
                "subject_code": "CS601",
                "start_time": "09:00 AM",
                "end_time": "10:00 AM",
                "room_number": "Room 304",
                "faculty_name": "Dr. Alan Turing",
                "class_type": "Theory"
            }
        ]
    }
    result = TimetableExtractionResult.model_validate(data)
    assert result.document_type == "TIMETABLE"
    assert len(result.entries) == 1
    assert result.entries[0].day_of_week == "MONDAY"
    assert result.entries[0].subject_name == "Artificial Intelligence"
    assert result.entries[0].room_number == "Room 304"

def test_academic_calendar_pydantic_schema_validation():
    data = {
        "document_type": "ACADEMIC_CALENDAR",
        "events": [
            {
                "event_name": "Commencement of Odd Semester",
                "category": "SEMESTER",
                "start_date": "2026-08-01",
                "end_date": None,
                "description": "College reopens for 3rd, 5th, and 7th semester students",
                "source_page": 1,
                "source_row": 1
            },
            {
                "event_name": "First Internal Assessment",
                "category": "INTERNAL_ASSESSMENT",
                "start_date": "2026-09-10",
                "end_date": "2026-09-15",
                "description": "CIE 1 test series",
                "source_page": 1,
                "source_row": 2
            }
        ]
    }
    result = AcademicCalendarExtractionResult.model_validate(data)
    assert result.document_type == "ACADEMIC_CALENDAR"
    assert len(result.events) == 2
    assert result.events[0].category == "SEMESTER"
    assert result.events[1].category == "INTERNAL_ASSESSMENT"
    assert result.events[1].start_date == "2026-09-10"
    assert result.events[1].end_date == "2026-09-15"

def test_fallback_parse_timetable_text():
    sample_text = """
    Department of Computer Science — Weekly Time Table 2026-2027
    MONDAY:
    09:00 AM - 10:00 AM: CS401 Java Programming (LH-1)
    10:00 AM - 11:00 AM: CS402 Database Systems (LH-1)
    WEDNESDAY:
    02:00 PM - 04:00 PM: CS403 Web Tech Lab (Lab 2)
    """
    res = _fallback_parse_timetable(sample_text)
    assert res.document_type == "TIMETABLE"
    assert len(res.entries) >= 2
    assert any(e.day_of_week in ["Monday", "MONDAY"] for e in res.entries)
    assert any(e.day_of_week in ["Wednesday", "WEDNESDAY"] for e in res.entries)

def test_fallback_parse_academic_calendar_text():
    sample_calendar_text = """
    ACADEMIC CALENDAR FOR ACADEMIC YEAR 2026-2027
    1. College Reopens: 2026-08-01
    2. First Internal Assessment (IA 1): 2026-09-10
    3. Dussehra Holiday: 2026-10-20
    4. Semester End Examination: 2026-12-15
    """
    res = _fallback_parse_academic_calendar(sample_calendar_text)
    assert res.document_type == "ACADEMIC_CALENDAR"
    assert len(res.events) >= 3
    categories = [e.category for e in res.events]
    assert "SEMESTER" in categories or "INTERNAL_ASSESSMENT" in categories or "HOLIDAY" in categories or "EXAM" in categories
