from app.db.models import User, Document, DocumentChunk, TimetableEntry, Plan
from app.core.security import create_access_token

def test_tenant_isolation_documents(client, db_session, test_user, auth_headers):
    # Create another distinct user B
    user_b = User(
        id="usr_other_999",
        email="other.student@university.edu",
        full_name="Other Student"
    )
    db_session.add(user_b)
    db_session.commit()

    # Add a document belonging to user B
    doc_b = Document(
        user_id=user_b.id,
        filename="Private_Confidential_Thesis_UserB.pdf",
        file_size=12000,
        mime_type="application/pdf",
        status="indexed"
    )
    db_session.add(doc_b)

    # Add a document belonging to test_user
    doc_a = Document(
        user_id=test_user.id,
        filename="UserA_Public_Notes.pdf",
        file_size=4000,
        mime_type="application/pdf",
        status="indexed"
    )
    db_session.add(doc_a)
    db_session.commit()

    # Query documents as User A
    res = client.get("/api/knowledge/documents", headers=auth_headers)
    assert res.status_code == 200
    docs = res.json()

    # Verify User A only sees their own document and NOT User B's document
    doc_names = [d["filename"] for d in docs]
    assert "UserA_Public_Notes.pdf" in doc_names
    assert "Private_Confidential_Thesis_UserB.pdf" not in doc_names
