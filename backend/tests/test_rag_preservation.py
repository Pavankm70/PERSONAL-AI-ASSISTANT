import io
import pytest
from app.db.models import Document, DocumentChunk, Timetable, TimetablePeriod

def test_rag_upload_syllabus(client, auth_headers, db_session, test_user):
    csv_content = b"Unit,Topic,Hours,Description\nUnit 1,Introduction to Algorithms,4,Time and space complexity asymptotic notation\nUnit 2,Divide and Conquer,6,Merge sort quick sort master theorem"
    res = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("algorithms_syllabus.csv", io.BytesIO(csv_content), "text/csv")},
        data={"document_type": "SYLLABUS"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "syllabus"
    assert data["documentType"] == "SYLLABUS"
    assert data["chunkCount"] >= 1

    # Verify Document and DocumentChunk in DB
    doc = db_session.query(Document).filter(Document.id == data["id"]).first()
    assert doc is not None
    assert doc.category == "syllabus"
    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).all()
    assert len(chunks) >= 1
    assert any("Algorithms" in c.content for c in chunks)

def test_rag_upload_approved_syllabus(client, auth_headers, db_session, test_user):
    csv_content = b"Course,Faculty,Module,Content\nCS401,Dr. Alan,Module 1,Distributed Systems RPC and consensus"
    res = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("approved_cs401.csv", io.BytesIO(csv_content), "text/csv")},
        data={"document_type": "APPROVED_SYLLABUS"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "syllabus"
    assert data["documentType"] == "SYLLABUS"

def test_rag_upload_lecture_notes(client, auth_headers, db_session, test_user):
    notes_content = b"Lecture 1 Notes\nToday we covered relational algebra: selection, projection, cartesian product, and natural joins."
    res = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("dbms_lecture1.txt", io.BytesIO(notes_content), "text/plain")},
        data={"document_type": "NOTES"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "notes"
    assert data["documentType"] == "NOTES"

def test_rag_upload_textbook(client, auth_headers, db_session, test_user):
    textbook_content = b"Chapter 1: Foundations of Computer Networks\nPacket switching vs circuit switching, OSI 7-layer model, and TCP/IP stack."
    res = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("tanenbaum_networks_ch1.txt", io.BytesIO(textbook_content), "text/plain")},
        data={"document_type": "TEXTBOOK"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "textbook"
    assert data["documentType"] == "TEXTBOOK"

def test_rag_delete_document_preserves_timetable(client, auth_headers, db_session, test_user):
    # 1. User has a manual timetable
    tt = Timetable(
        user_id=test_user.id,
        name="Untouchable Timetable",
        academic_year="2026-2027"
    )
    db_session.add(tt)
    db_session.commit()
    period = TimetablePeriod(
        timetable_id=tt.id,
        user_id=test_user.id,
        day_of_week="Monday",
        subject_name="Compiler Design",
        start_time="09:00",
        end_time="10:00"
    )
    db_session.add(period)
    db_session.commit()

    # 2. Upload a knowledge document
    doc_res = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("temporary_notes.txt", io.BytesIO(b"Notes to delete"), "text/plain")},
        data={"document_type": "NOTES"}
    )
    doc_id = doc_res.json()["id"]

    # Verify document and chunks created
    assert db_session.query(Document).filter(Document.id == doc_id).first() is not None
    assert db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count() >= 1

    # 3. Delete knowledge document
    del_res = client.delete(f"/api/knowledge/documents/{doc_id}", headers=auth_headers)
    assert del_res.status_code == 200

    # Verify document and its chunks deleted
    assert db_session.query(Document).filter(Document.id == doc_id).first() is None
    assert db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count() == 0

    # 4. CRITICAL: Timetable and TimetablePeriod must remain intact!
    preserved_tt = db_session.query(Timetable).filter(Timetable.id == tt.id).first()
    assert preserved_tt is not None
    preserved_periods = db_session.query(TimetablePeriod).filter(TimetablePeriod.timetable_id == tt.id).all()
    assert len(preserved_periods) == 1
    assert preserved_periods[0].subject_name == "Compiler Design"

