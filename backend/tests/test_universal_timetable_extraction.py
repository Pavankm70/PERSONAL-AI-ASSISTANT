import pytest
import io
import os
import tempfile
from pypdf import PdfWriter

from app.schemas import (
    TimetableEntryItem,
    SubjectReferenceItem,
    TimetableExtractionResult
)
from app.services.table_extractor import (
    detect_pdf_format_and_pages,
    render_pdf_page_to_base64,
    resolve_reference_table_mappings,
    normalize_and_validate_entries,
    _fallback_parse_timetable
)
from app.db.models import Document, TimetableEntry, Conversation, Message
from app.agent.graph import AureliaAgent

def test_detect_pdf_format_image_based_and_render():
    # Create an empty 1-page PDF (0 text chars, 0 tables)
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    format_info = detect_pdf_format_and_pages(pdf_bytes)
    assert format_info["overall_format"] == "IMAGE_BASED"
    page_details = format_info["pages"]
    assert len(page_details) == 1
    assert page_details[0]["page_type"] == "IMAGE_BASED"
    assert page_details[0]["char_count"] == 0

    # Test pypdfium2 high-resolution rendering
    b64_img = render_pdf_page_to_base64(pdf_bytes, 0)
    assert isinstance(b64_img, str)
    assert len(b64_img) > 100

def test_fallback_parse_days_as_rows():
    text = """
Day,09:00 AM - 10:00 AM,10:00 AM - 11:00 AM,11:15 AM - 12:15 PM
Monday,Data Structures (Room 101),Operating Systems (Room 102),Algorithms (Room 103)
Tuesday,Computer Networks (LH-2),Software Eng (LH-2),Web Dev (Lab 1)
"""
    result = _fallback_parse_timetable(text)
    assert len(result.entries) >= 6
    mon_entries = [e for e in result.entries if e.day_of_week == "Monday"]
    assert len(mon_entries) == 3
    assert any("Data Structures" in e.subject_name and e.room_number == "Room 101" for e in mon_entries)
    assert any("Operating Systems" in e.subject_name and e.room_number == "Room 102" for e in mon_entries)
    tue_entries = [e for e in result.entries if e.day_of_week == "Tuesday"]
    assert len(tue_entries) == 3
    assert any("Computer Networks" in e.subject_name and e.room_number == "LH-2" for e in tue_entries)

def test_fallback_parse_days_as_columns():
    text = """
Time,Monday,Tuesday,Wednesday
09:00 AM - 10:00 AM,Artificial Intelligence,Cloud Computing,Cyber Security
10:00 AM - 11:00 AM,Machine Learning,Deep Learning,Computer Vision
"""
    result = _fallback_parse_timetable(text)
    assert len(result.entries) >= 6
    mon_ai = next((e for e in result.entries if e.day_of_week == "Monday" and "Artificial Intelligence" in e.subject_name), None)
    assert mon_ai is not None
    assert mon_ai.start_time == "09:00 AM"
    assert mon_ai.end_time == "10:00 AM"

    tue_cc = next((e for e in result.entries if e.day_of_week == "Tuesday" and "Cloud Computing" in e.subject_name), None)
    assert tue_cc is not None
    assert tue_cc.start_time == "09:00 AM"

def test_fallback_parse_merged_multi_period_and_lab():
    text = """
Day,Time,Subject,Room
Friday,02:00 PM - 04:00 PM,Networks Laboratory,Lab 2
Friday,09:00 AM - 10:00 AM,Compiler Design,Room 205
"""
    result = _fallback_parse_timetable(text)
    assert len(result.entries) == 2
    lab_entry = next((e for e in result.entries if "Networks Laboratory" in e.subject_name), None)
    assert lab_entry is not None
    assert lab_entry.start_time == "02:00 PM"
    assert lab_entry.end_time == "04:00 PM"
    assert lab_entry.room_number == "Lab 2"
    assert lab_entry.class_type == "Lab"

def test_reference_table_legend_resolution():
    entries = [
        TimetableEntryItem(
            day_of_week="Monday",
            subject_name="CS501",
            subject_code="CS501",
            start_time="09:00 AM",
            end_time="10:00 AM",
            room_number=None,
            faculty_name=None,
            class_type="Theory"
        )
    ]
    ref_items = [
        SubjectReferenceItem(
            code="CS501",
            name="Distributed Cloud Systems",
            faculty="Dr. Angela Merkel",
            room="Auditorium 2"
        )
    ]
    enriched = resolve_reference_table_mappings(entries, ref_items)
    assert len(enriched) == 1
    assert enriched[0].subject_name == "Distributed Cloud Systems"
    assert enriched[0].faculty_name == "Dr. Angela Merkel"
    assert enriched[0].room_number == "Auditorium 2"

def test_break_and_lunch_exclusion():
    raw_entries = [
        TimetableEntryItem(
            day_of_week="MONDAY",
            subject_name="Physics",
            subject_code="PHY101",
            start_time="09:00 AM",
            end_time="10:00 AM"
        ),
        TimetableEntryItem(
            day_of_week="MONDAY",
            subject_name="LUNCH BREAK",
            subject_code=None,
            start_time="12:00 PM",
            end_time="01:00 PM"
        ),
        TimetableEntryItem(
            day_of_week="MONDAY",
            subject_name="TEA BREAK",
            subject_code=None,
            start_time="03:00 PM",
            end_time="03:15 PM"
        )
    ]
    cleaned, uncert_count = normalize_and_validate_entries(raw_entries)
    assert len(cleaned) == 1
    assert cleaned[0].subject_name == "Physics"
    assert cleaned[0].day_of_week == "Monday"

def test_retry_extraction_endpoint(client, auth_headers, test_user, db_session):
    # Create a temporary file on disk with timetable content
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, "staged_timetable.csv")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("Day,Time,Course,Room\nMonday,09:00 AM - 10:00 AM,Calculus III,Room 101\n")

    doc = Document(
        user_id=test_user.id,
        filename="staged_timetable.csv",
        file_path=file_path,
        file_size=os.path.getsize(file_path),
        mime_type="text/csv",
        document_type="TIMETABLE",
        category="timetable",
        processing_status="FAILED",
        processing_error="Simulated failure"
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    res = client.post(f"/api/knowledge/documents/{doc.id}/retry", headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["processingStatus"] == "REVIEW_REQUIRED"
    assert "preview" in data
    assert len(data["preview"]["entries"]) >= 1
    assert data["preview"]["entries"][0]["subject_name"] == "Calculus III"

@pytest.mark.asyncio
async def test_chatbot_multi_turn_followup(db_session, test_user):
    agent = AureliaAgent()
    conv = Conversation(user_id=test_user.id, title="Multi Turn Test")
    db_session.add(conv)
    db_session.commit()

    tt = TimetableEntry(
        user_id=test_user.id,
        course_name="Database Systems",
        course_code="CS301",
        day_of_week="Tuesday",
        start_time="10:00 AM",
        end_time="11:00 AM",
        room="Room 402",
        instructor="Prof. Charles Babbage",
        class_type="Theory"
    )
    db_session.add(tt)
    db_session.commit()

    # Turn 1: When is my Database Systems class?
    turn1_res = await agent.run(
        user_id=test_user.id,
        query="When is my Database Systems class?",
        conversation_id=conv.id,
        db=db_session
    )
    content1 = turn1_res.get("content", "")
    assert "Database Systems" in content1
    assert "Tuesday" in content1

    # Record message history
    db_session.add(Message(conversation_id=conv.id, role="user", content="When is my Database Systems class?"))
    db_session.add(Message(conversation_id=conv.id, role="assistant", content=content1))
    db_session.commit()

    # Turn 2: Which room?
    turn2_res = await agent.run(
        user_id=test_user.id,
        query="Which room is it in?",
        conversation_id=conv.id,
        db=db_session
    )
    content2 = turn2_res.get("content", "")
    assert "Room 402" in content2 or "Database Systems" in content2

    # Record message history
    db_session.add(Message(conversation_id=conv.id, role="user", content="Which room is it in?"))
    db_session.add(Message(conversation_id=conv.id, role="assistant", content=content2))
    db_session.commit()

    # Turn 3: Who teaches it?
    turn3_res = await agent.run(
        user_id=test_user.id,
        query="Who teaches it?",
        conversation_id=conv.id,
        db=db_session
    )
    content3 = turn3_res.get("content", "")
    assert "Prof. Charles Babbage" in content3 or "Database Systems" in content3

@pytest.mark.asyncio
async def test_chatbot_advanced_timetable_queries(db_session, test_user):
    agent = AureliaAgent()
    conv = Conversation(user_id=test_user.id, title="Advanced Queries")
    db_session.add(conv)
    db_session.commit()

    # Seed timetable entries:
    # 1. Monday morning class
    # 2. Monday overlapping elective
    # 3. Monday afternoon lab (after lunch)
    entries = [
        TimetableEntry(
            user_id=test_user.id,
            course_name="Compiler Design",
            course_code="CS502",
            day_of_week="Monday",
            start_time="10:00 AM",
            end_time="11:00 AM",
            room="Room 302",
            class_type="Theory"
        ),
        TimetableEntry(
            user_id=test_user.id,
            course_name="Elective A",
            course_code="EL501",
            day_of_week="Monday",
            start_time="10:30 AM",
            end_time="11:30 AM",
            room="Room 105",
            class_type="Theory"
        ),
        TimetableEntry(
            user_id=test_user.id,
            course_name="Operating Systems Lab",
            course_code="CS503",
            day_of_week="Monday",
            start_time="02:00 PM",
            end_time="04:00 PM",
            room="Lab 3",
            class_type="Lab"
        )
    ]
    db_session.add_all(entries)
    db_session.commit()

    # Query 1: Overlapping classes
    overlap_res = await agent.run(
        user_id=test_user.id,
        query="Do I have any overlapping classes or schedule conflicts?",
        conversation_id=conv.id,
        db=db_session
    )
    overlap_content = overlap_res.get("content", "")
    assert "Compiler Design" in overlap_content or "Elective A" in overlap_content

    # Query 2: Classes after lunch
    lunch_res = await agent.run(
        user_id=test_user.id,
        query="Which classes do I have after lunch on Monday?",
        conversation_id=conv.id,
        db=db_session
    )
    lunch_content = lunch_res.get("content", "")
    assert "Operating Systems Lab" in lunch_content or "02:00 PM" in lunch_content

    # Query 3: Laboratory classes
    lab_res = await agent.run(
        user_id=test_user.id,
        query="When is my next laboratory session?",
        conversation_id=conv.id,
        db=db_session
    )
    lab_content = lab_res.get("content", "")
    assert "Operating Systems Lab" in lab_content or "Lab 3" in lab_content

    # Query 4: Full weekly timetable
    week_res = await agent.run(
        user_id=test_user.id,
        query="What is my full timetable for this week?",
        conversation_id=conv.id,
        db=db_session
    )
    week_content = week_res.get("content", "")
    assert "Monday" in week_content
    assert "Compiler Design" in week_content
