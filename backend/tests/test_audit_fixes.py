import pytest
from app.db.models import User, Plan, PlanTask, Conversation, Message, Document, DocumentChunk
from app.services.weather_service import weather_service
from app.services.web_search_service import web_search_service
from app.core.security import create_access_token

def test_delete_calendar_event_endpoint_mock_mode(client, auth_headers):
    # When Google Calendar is unlinked or returns mock/error, DELETE endpoint responds truthfully
    res = client.delete("/api/calendar/events/ev_test_12345", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data.get("deleted") is True or data.get("status") == "deleted"

def test_smart_study_slots_proposal_and_application(client, auth_headers, test_user, db_session):
    # Create test plan
    plan = Plan(
        id="plan_audit_test",
        user_id=test_user.id,
        title="Final Exam Sprint",
        period="Finals Week",
        goals=["Pass ML exam", "Submit Project"],
        suggested_study_blocks=[]
    )
    db_session.add(plan)
    db_session.flush()

    task = PlanTask(
        id="task_audit_t1",
        plan_id=plan.id,
        title="Review Backpropagation Math",
        duration_minutes=60,
        priority="high",
        completed=False
    )
    db_session.add(task)
    db_session.commit()

    # Call propose slots endpoint
    res = client.post(f"/api/plans/{plan.id}/propose-slots", headers=auth_headers)
    assert res.status_code == 200
    pdata = res.json()
    assert "proposedStudyBlocks" in pdata
    assert len(pdata["proposedStudyBlocks"]) >= 1
    assert "Review Backpropagation Math" in pdata["proposedStudyBlocks"][0]["focus"]

    # Call apply slots endpoint
    apply_res = client.post(
        f"/api/plans/{plan.id}/apply-slots",
        headers=auth_headers,
        json={"studyBlocks": pdata["proposedStudyBlocks"]}
    )
    assert apply_res.status_code == 200
    adata = apply_res.json()
    assert adata["success"] is True
    assert len(adata["suggestedStudyBlocks"]) >= 1

def test_purge_chat_history_endpoint(client, auth_headers, test_user, db_session):
    # Add a conversation and messages
    conv = Conversation(id="conv_test_purge", user_id=test_user.id, title="Test Conversation")
    db_session.add(conv)
    db_session.commit()

    msg1 = Message(id="msg_p1", conversation_id=conv.id, role="user", content="Hello Aurelia")
    msg2 = Message(id="msg_p2", conversation_id=conv.id, role="assistant", content="Hello Alex")
    db_session.add_all([msg1, msg2])
    db_session.commit()

    # Call purge history
    res = client.delete("/api/chat/history", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True

    # Verify messages are gone
    remaining_convs = db_session.query(Conversation).filter_by(user_id=test_user.id).all()
    assert len(remaining_convs) == 0

def test_account_deletion_endpoint(client, db_session):
    # Create isolated user to delete
    user_to_delete = User(
        id="usr_audit_to_delete",
        email="delete.me@university.edu",
        full_name="Temporary User"
    )
    db_session.add(user_to_delete)
    db_session.commit()

    target_user_id = user_to_delete.id
    token = create_access_token({"sub": target_user_id, "email": user_to_delete.email})
    headers = {"Authorization": f"Bearer {token}"}

    # Add a doc for this user
    doc = Document(id="doc_temp", user_id=target_user_id, filename="DeleteMe.txt", file_size=100, mime_type="text/plain")
    db_session.add(doc)
    db_session.commit()

    # Call delete account
    del_res = client.delete("/api/settings/account", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Verify user record is gone
    user_check = db_session.query(User).filter_by(id=target_user_id).first()
    assert user_check is None

    # Verify documents are gone
    doc_check = db_session.query(Document).filter_by(user_id=target_user_id).all()
    assert len(doc_check) == 0

@pytest.mark.asyncio
async def test_weather_service_clean_fallback():
    res = await weather_service.get_weather("Bengaluru")
    assert "temperatureC" in res or "error" in res or "location" in res

@pytest.mark.asyncio
async def test_web_search_unconfigured_status():
    res = await web_search_service.search("transformer optimization papers")
    assert res["status"] in ["unconfigured", "no_results", "success", "error"]
    assert "results" in res
