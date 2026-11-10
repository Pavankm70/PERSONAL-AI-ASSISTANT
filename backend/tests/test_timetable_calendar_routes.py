import pytest
import io
from app.db.models import Document, TimetableEntry, AcademicEvent

def test_upload_timetable_and_confirm(client, auth_headers, test_user, db_session):
    # Upload text-based timetable
    timetable_content = b"""Day,Time,Course,Room
Monday,09:00 AM - 10:00 AM,Java Programming,Room 101
Monday,10:00 AM - 11:00 AM,Algorithms,Room 101
Wednesday,02:00 PM - 04:00 PM,Machine Learning Lab,Lab 3"""

    files = {"file": ("timetable_sem5.csv", io.BytesIO(timetable_content), "text/csv")}
    data = {"category": "timetable", "document_type": "TIMETABLE"}

    res = client.post("/api/knowledge/upload", headers=auth_headers, files=files, data=data)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["documentType"] == "TIMETABLE"
    assert body["processingStatus"] == "REVIEW_REQUIRED"
    doc_id = body["id"]

    # Preview endpoint check
    prev_res = client.get(f"/api/knowledge/documents/{doc_id}/preview", headers=auth_headers)
    assert prev_res.status_code == 200
    prev_body = prev_res.json()
    assert prev_body["documentType"] == "TIMETABLE"

    # Confirm extracted records
    confirm_payload = {
        "document_type": "TIMETABLE",
        "entries": [
            {
                "day_of_week": "MONDAY",
                "subject_name": "Java Programming",
                "subject_code": "CS401",
                "start_time": "09:00 AM",
                "end_time": "10:00 AM",
                "room_number": "Room 101",
                "faculty_name": "Prof. Rao",
                "class_type": "Theory"
            },
            {
                "day_of_week": "WEDNESDAY",
                "subject_name": "Machine Learning Lab",
                "subject_code": "CS402",
                "start_time": "02:00 PM",
                "end_time": "04:00 PM",
                "room_number": "Lab 3",
                "faculty_name": "Dr. Kumar",
                "class_type": "Lab"
            }
        ]
    }
    conf_res = client.post(f"/api/knowledge/documents/{doc_id}/confirm", headers=auth_headers, json=confirm_payload)
    assert conf_res.status_code == 200
    conf_body = conf_res.json()
    assert conf_body["success"] is True
    assert conf_body["insertedCount"] == 2

    # Query timetables list endpoint
    tt_res = client.get("/api/knowledge/timetables", headers=auth_headers)
    assert tt_res.status_code == 200
    entries = tt_res.json()
    assert len(entries) >= 2
    assert any(e["courseName"] == "Java Programming" and e["dayOfWeek"] == "Monday" for e in entries)
    assert any(e["courseName"] == "Machine Learning Lab" and e["classType"] == "Lab" for e in entries)

def test_upload_academic_calendar_and_confirm(client, auth_headers, test_user, db_session):
    calendar_content = b"""ACADEMIC CALENDAR 2026-2027
1. College Reopens: 2026-08-01
2. First Internal Assessment: 2026-09-10 to 2026-09-15
3. Semester End Exams: 2026-12-15"""

    files = {"file": ("calendar_2026.txt", io.BytesIO(calendar_content), "text/plain")}
    data = {"category": "academic_calendar", "document_type": "ACADEMIC_CALENDAR"}

    res = client.post("/api/knowledge/upload", headers=auth_headers, files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["documentType"] == "ACADEMIC_CALENDAR"
    doc_id = body["id"]

    # Confirm extracted events
    confirm_payload = {
        "document_type": "ACADEMIC_CALENDAR",
        "events": [
            {
                "event_name": "First Internal Assessment (IA 1)",
                "category": "INTERNAL_ASSESSMENT",
                "start_date": "2026-09-10",
                "end_date": "2026-09-15",
                "description": "First internal assessment test"
            },
            {
                "event_name": "Semester End Examinations",
                "category": "EXAM",
                "start_date": "2026-12-15",
                "end_date": "2026-12-30",
                "description": "SEE 2026 exams"
            },
            {
                "event_name": "Gandhi Jayanti",
                "category": "HOLIDAY",
                "start_date": "2026-10-02",
                "end_date": None,
                "description": "National Holiday"
            }
        ]
    }
    conf_res = client.post(f"/api/knowledge/documents/{doc_id}/confirm", headers=auth_headers, json=confirm_payload)
    assert conf_res.status_code == 200
    assert conf_res.json()["insertedCount"] == 3

    # Query academic events list endpoint
    ev_res = client.get("/api/knowledge/academic-events", headers=auth_headers)
    assert ev_res.status_code == 200
    ev_list = ev_res.json()
    assert len(ev_list) == 3

    # Query category filter
    exam_res = client.get("/api/knowledge/academic-events?category=EXAM", headers=auth_headers)
    assert exam_res.status_code == 200
    assert len(exam_res.json()) == 1
    assert exam_res.json()[0]["eventName"] == "Semester End Examinations"

def test_delete_document_removes_structured_entries_cleanly(client, auth_headers, test_user, db_session):
    doc = Document(
        user_id=test_user.id,
        filename="old_timetable.pdf",
        file_size=2000,
        mime_type="application/pdf",
        document_type="TIMETABLE",
        processing_status="COMPLETED"
    )
    db_session.add(doc)
    db_session.commit()

    entry = TimetableEntry(
        user_id=test_user.id,
        document_id=doc.id,
        course_name="Database Systems",
        course_code="CS402",
        day_of_week="Thursday",
        start_time="11:00 AM",
        end_time="12:00 PM"
    )
    db_session.add(entry)
    db_session.commit()

    del_res = client.delete(f"/api/knowledge/documents/{doc.id}", headers=auth_headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Timetable entry must be removed
    assert db_session.query(TimetableEntry).filter(TimetableEntry.document_id == doc.id).first() is None
    assert db_session.query(Document).filter(Document.id == doc.id).first() is None

