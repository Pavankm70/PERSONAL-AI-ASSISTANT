import pytest
from datetime import datetime, timezone
from app.db.models import User, Document, DocumentChunk, TimetableEntry, AcademicEvent

def test_document_model_with_new_fields(db_session, test_user):
    doc = Document(
        user_id=test_user.id,
        filename="btech_cs_timetable_sem5.pdf",
        file_size=10240,
        mime_type="application/pdf",
        category="timetable",
        document_type="TIMETABLE",
        processing_status="REVIEW_REQUIRED",
        extracted_data={"entries": [{"day_of_week": "MONDAY", "subject_name": "Operating Systems"}]},
        document_version=1,
        is_active=True
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    assert doc.id is not None
    assert doc.document_type == "TIMETABLE"
    assert doc.processing_status == "REVIEW_REQUIRED"
    assert doc.is_active is True
    assert doc.document_version == 1
    assert "entries" in doc.extracted_data

def test_timetable_entry_model_and_aliases(db_session, test_user):
    doc = Document(
        user_id=test_user.id,
        filename="timetable.pdf",
        file_size=5000,
        mime_type="application/pdf",
        document_type="TIMETABLE"
    )
    db_session.add(doc)
    db_session.commit()

    entry = TimetableEntry(
        user_id=test_user.id,
        document_id=doc.id,
        course_name="Java Programming",
        course_code="CS501",
        day_of_week="Monday",
        start_time="09:00 AM",
        end_time="10:00 AM",
        room="LH-2",
        instructor="Dr. Ramesh",
        class_type="Theory",
        academic_year="2026-2027",
        semester="5"
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    # Test property aliases
    assert entry.subject_name == "Java Programming"
    assert entry.subject_code == "CS501"
    assert entry.room_number == "LH-2"
    assert entry.faculty_name == "Dr. Ramesh"
    assert entry.class_type == "Theory"
    assert entry.document_id == doc.id

    # Test alias setters
    entry.subject_name = "Advanced Java"
    entry.room_number = "Lab 4"
    assert entry.course_name == "Advanced Java"
    assert entry.room == "Lab 4"

def test_academic_event_model(db_session, test_user):
    doc = Document(
        user_id=test_user.id,
        filename="academic_calendar_2026.pdf",
        file_size=8000,
        mime_type="application/pdf",
        document_type="ACADEMIC_CALENDAR"
    )
    db_session.add(doc)
    db_session.commit()

    event = AcademicEvent(
        user_id=test_user.id,
        document_id=doc.id,
        event_name="First Internal Assessment (IA-1)",
        category="INTERNAL_ASSESSMENT",
        start_date="2026-09-10",
        end_date="2026-09-15",
        description="First internal assessment test for all branches",
        academic_year="2026-2027",
        semester="Odd",
        source_page=1,
        source_row=5
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert event.id is not None
    assert event.user_id == test_user.id
    assert event.document_id == doc.id
    assert event.category == "INTERNAL_ASSESSMENT"
    assert event.start_date == "2026-09-10"
    assert event.end_date == "2026-09-15"
    assert event.source_row == 5

def test_cascade_delete_document_records_isolation(db_session, test_user):
    # Create two documents with entries
    doc1 = Document(
        user_id=test_user.id,
        filename="doc1_timetable.pdf",
        file_size=1000,
        mime_type="application/pdf",
        document_type="TIMETABLE"
    )
    doc2 = Document(
        user_id=test_user.id,
        filename="doc2_calendar.pdf",
        file_size=2000,
        mime_type="application/pdf",
        document_type="ACADEMIC_CALENDAR"
    )
    db_session.add_all([doc1, doc2])
    db_session.commit()

    tt1 = TimetableEntry(
        user_id=test_user.id,
        document_id=doc1.id,
        course_name="Compiler Design",
        course_code="CS502",
        day_of_week="Tuesday",
        start_time="10:00 AM",
        end_time="11:00 AM"
    )
    ev2 = AcademicEvent(
        user_id=test_user.id,
        document_id=doc2.id,
        event_name="Diwali Holidays",
        category="HOLIDAY",
        start_date="2026-11-01",
        end_date="2026-11-05"
    )
    db_session.add_all([tt1, ev2])
    db_session.commit()

    # Deleting doc1 must delete tt1, but must NOT delete doc2 or ev2
    db_session.query(TimetableEntry).filter(TimetableEntry.document_id == doc1.id).delete()
    db_session.delete(doc1)
    db_session.commit()

    assert db_session.query(Document).filter(Document.id == doc1.id).first() is None
    assert db_session.query(TimetableEntry).filter(TimetableEntry.document_id == doc1.id).first() is None
    # doc2 and ev2 remain completely untouched
    assert db_session.query(Document).filter(Document.id == doc2.id).first() is not None
    assert db_session.query(AcademicEvent).filter(AcademicEvent.document_id == doc2.id).first() is not None

