import pytest
from app.db.models import User, Document, TimetableEntry, AcademicEvent
from app.core.security import create_access_token

def test_tenant_isolation_timetable_and_academic_events(client, db_session):
    # Create User A
    user_a = User(
        id="usr_alice",
        email="alice@college.edu",
        full_name="Alice Smith",
        timezone="UTC"
    )
    # Create User B
    user_b = User(
        id="usr_bob",
        email="bob@othercollege.edu",
        full_name="Bob Jones",
        timezone="UTC"
    )
    db_session.add_all([user_a, user_b])
    db_session.commit()

    token_a = create_access_token({"sub": user_a.id, "email": user_a.email})
    token_b = create_access_token({"sub": user_b.id, "email": user_b.email})
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A has Timetable A & Event A
    doc_a = Document(user_id=user_a.id, filename="alice_timetable.pdf", file_size=1000, mime_type="application/pdf", document_type="TIMETABLE")
    db_session.add(doc_a)
    db_session.commit()

    tt_a = TimetableEntry(
        user_id=user_a.id,
        document_id=doc_a.id,
        course_name="Alice Physics",
        course_code="PHY101",
        day_of_week="Monday",
        start_time="09:00 AM",
        end_time="10:00 AM"
    )
    ev_a = AcademicEvent(
        user_id=user_a.id,
        document_id=doc_a.id,
        event_name="Alice Sports Day",
        category="COLLEGE_EVENT",
        start_date="2026-11-20"
    )

    # User B has Timetable B & Event B
    doc_b = Document(user_id=user_b.id, filename="bob_timetable.pdf", file_size=1000, mime_type="application/pdf", document_type="TIMETABLE")
    db_session.add(doc_b)
    db_session.commit()

    tt_b = TimetableEntry(
        user_id=user_b.id,
        document_id=doc_b.id,
        course_name="Bob Chemistry",
        course_code="CHM101",
        day_of_week="Monday",
        start_time="09:00 AM",
        end_time="10:00 AM"
    )
    ev_b = AcademicEvent(
        user_id=user_b.id,
        document_id=doc_b.id,
        event_name="Bob Tech Fest",
        category="COLLEGE_EVENT",
        start_date="2026-11-25"
    )
    db_session.add_all([tt_a, ev_a, tt_b, ev_b])
    db_session.commit()

    # 1. User A querying timetables should ONLY see Alice Physics
    res_a_tt = client.get("/api/knowledge/timetables", headers=headers_a)
    assert res_a_tt.status_code == 200
    courses_a = [e["courseName"] for e in res_a_tt.json()]
    assert "Alice Physics" in courses_a
    assert "Bob Chemistry" not in courses_a

    # 2. User B querying academic events should ONLY see Bob Tech Fest
    res_b_ev = client.get("/api/knowledge/academic-events", headers=headers_b)
    assert res_b_ev.status_code == 200
    events_b = [e["eventName"] for e in res_b_ev.json()]
    assert "Bob Tech Fest" in events_b
    assert "Alice Sports Day" not in events_b

    # 3. User B cannot preview User A's document (IDOR attempt)
    res_b_preview_a = client.get(f"/api/knowledge/documents/{doc_a.id}/preview", headers=headers_b)
    assert res_b_preview_a.status_code == 404

    # 4. User B cannot delete User A's document (IDOR attempt)
    res_b_delete_a = client.delete(f"/api/knowledge/documents/{doc_a.id}", headers=headers_b)
    assert res_b_delete_a.status_code == 404

    # Verify doc_a is still present
    assert db_session.query(Document).filter(Document.id == doc_a.id).first() is not None

