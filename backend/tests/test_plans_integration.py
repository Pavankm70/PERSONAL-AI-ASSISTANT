import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.db.models import User, Plan, PlanTask
from app.agent.graph import agent_orchestrator, heuristic_classify_intent
from app.agent.tool_registry import tool_registry

def test_empty_plans_returns_empty_list_no_dummy_data(client: TestClient, auth_headers: dict):
    """
    GET /api/plans must return an empty list [] for a user with no saved plans.
    It must never auto-generate or seed fake starter plans.
    """
    res = client.get("/api/plans", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 0

def test_plan_crud_and_tenant_isolation(client: TestClient, auth_headers: dict, test_user: User, db_session: Session):
    """
    Verifies full persistent CRUD for plans with strict tenant isolation.
    """
    from app.core.security import create_access_token
    user_b = User(
        id="usr_test_b",
        email="user.b@university.edu",
        full_name="User B",
        timezone="UTC",
        onboarding_complete=True
    )
    db_session.add(user_b)
    db_session.commit()
    token_b = create_access_token({"sub": user_b.id, "email": user_b.email})
    second_user_auth_headers = {"Authorization": f"Bearer {token_b}"}
    # 1. User A creates a plan
    create_payload = {
        "title": "30-Day Java & DSA Sprint",
        "period": "30 Days",
        "goals": ["Master Java OOP", "Solve 50 Tree & Graph problems"],
        "tasks": [
            {"title": "Day 1: Java Memory Model & Collections", "durationMinutes": 180, "priority": "high"},
            {"title": "Day 2: Binary Search & Two Pointers", "durationMinutes": 180, "priority": "high"}
        ]
    }
    create_res = client.post("/api/plans", json=create_payload, headers=auth_headers)
    assert create_res.status_code == 200
    plan_data = create_res.json()
    plan_id = plan_data["id"]
    assert plan_data["title"] == "30-Day Java & DSA Sprint"
    assert len(plan_data["tasks"]) == 2

    # 2. User B cannot see User A's plan
    user_b_res = client.get("/api/plans", headers=second_user_auth_headers)
    assert user_b_res.status_code == 200
    assert len(user_b_res.json()) == 0

    user_b_get = client.get(f"/api/plans/{plan_id}", headers=second_user_auth_headers)
    assert user_b_get.status_code == 404

    # 3. User A can retrieve plan
    get_res = client.get(f"/api/plans/{plan_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "30-Day Java & DSA Sprint"

    # 4. User A updates plan title and period
    update_res = client.patch(f"/api/plans/{plan_id}", json={"title": "Updated Java Sprint", "period": "45 Days"}, headers=auth_headers)
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Updated Java Sprint"
    assert update_res.json()["period"] == "45 Days"

    # 5. User A adds a task
    add_task_res = client.post(f"/api/plans/{plan_id}/tasks", json={
        "title": "Day 3: Dynamic Programming Patterns",
        "durationMinutes": 120,
        "priority": "medium"
    }, headers=auth_headers)
    assert add_task_res.status_code == 200
    task_id = add_task_res.json()["id"]

    # 6. User A completes the task
    complete_res = client.patch(f"/api/plans/{plan_id}/tasks/{task_id}", json={"completed": True}, headers=auth_headers)
    assert complete_res.status_code == 200
    assert complete_res.json()["completed"] is True

    # 7. User A deletes the task
    del_task_res = client.delete(f"/api/plans/{plan_id}/tasks/{task_id}", headers=auth_headers)
    assert del_task_res.status_code == 200
    assert del_task_res.json()["success"] is True

    # 8. User A deletes the plan (cascades tasks)
    del_plan_res = client.delete(f"/api/plans/{plan_id}", headers=auth_headers)
    assert del_plan_res.status_code == 200
    assert del_plan_res.json()["success"] is True

    # Verify plan and tasks are gone from DB
    assert client.get(f"/api/plans/{plan_id}", headers=auth_headers).status_code == 404
    tasks_remaining = db_session.query(PlanTask).filter(PlanTask.plan_id == plan_id).count()
    assert tasks_remaining == 0

@pytest.mark.asyncio
async def test_ai_assistant_example_a_create_plan(db_session: Session, test_user: User):
    """
    Example A: User asks 'Create a 30-day Java and DSA study plan. I can study three hours daily.'
    AI assistant creates and persists the plan with tasks in the database.
    """
    query = "Create a 30-day Java and DSA study plan. I can study three hours daily."
    conv_id = "conv_test_ex_a"

    # Verify intent routing
    intent = heuristic_classify_intent(query)
    assert intent["tool"] == "plan_create"
    assert "java" in intent["args"]["subject"].lower()

    # Execute through orchestrator
    result = await agent_orchestrator.run(
        user_id=test_user.id,
        query=query,
        conversation_id=conv_id,
        db=db_session
    )

    assert result["role"] == "assistant"
    assert "30-Day Java and DSA Study Plan" in result["content"]
    assert "3 hours daily" in result["content"]

    # Verify plan was persistently stored in DB
    saved_plan = db_session.query(Plan).filter(Plan.user_id == test_user.id).first()
    assert saved_plan is not None
    assert "Java and DSA" in saved_plan.title
    tasks = db_session.query(PlanTask).filter(PlanTask.plan_id == saved_plan.id).all()
    assert len(tasks) >= 4
    for t in tasks:
        assert t.duration_minutes == 180  # 3 hours daily

@pytest.mark.asyncio
async def test_ai_assistant_example_b_update_plan(db_session: Session, test_user: User):
    """
    Example B: User asks 'I can only study two hours daily now. Update my plan.'
    AI assistant updates pending task duration to 2 hours while preserving completed tasks.
    """
    # Seed an existing plan with completed and incomplete tasks
    plan = Plan(user_id=test_user.id, title="Java & DSA Masterclass", period="30 Days")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    t1 = PlanTask(plan_id=plan.id, title="Day 1: Completed Task", duration_minutes=180, completed=True)
    t2 = PlanTask(plan_id=plan.id, title="Day 2: Pending Task", duration_minutes=180, completed=False)
    db_session.add_all([t1, t2])
    db_session.commit()

    query = "I can only study two hours daily now. Update my plan."
    intent = heuristic_classify_intent(query)
    assert intent["tool"] == "plan_update"
    assert intent["args"]["daily_hours"] == 2.0

    result = await agent_orchestrator.run(
        user_id=test_user.id,
        query=query,
        conversation_id="conv_test_ex_b",
        db=db_session
    )

    assert "2 hours daily" in result["content"]

    # Verify in DB: t1 still 180 min and completed; t2 updated to 120 min
    db_session.refresh(t1)
    db_session.refresh(t2)
    assert t1.completed is True
    assert t2.completed is False
    assert t2.duration_minutes == 120  # 2 hours

@pytest.mark.asyncio
async def test_ai_assistant_example_c_complete_task(db_session: Session, test_user: User):
    """
    Example C: User says 'I completed today's Java task.'
    AI assistant finds the Java task in the user's plan and marks it completed.
    """
    plan = Plan(user_id=test_user.id, title="Backend Engineering Sprint", period="Current Sprint")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    java_task = PlanTask(plan_id=plan.id, title="Java Generics & Collections Exercise", duration_minutes=60, completed=False)
    db_session.add(java_task)
    db_session.commit()

    query = "I completed today's Java task."
    intent = heuristic_classify_intent(query)
    assert intent["tool"] == "plan_complete_task"

    result = await agent_orchestrator.run(
        user_id=test_user.id,
        query=query,
        conversation_id="conv_test_ex_c",
        db=db_session
    )

    assert "completed" in result["content"].lower()

    db_session.refresh(java_task)
    assert java_task.completed is True

@pytest.mark.asyncio
async def test_ai_assistant_example_d_delete_plan_requires_confirmation(db_session: Session, test_user: User):
    """
    Example D: User says 'I don't like this plan. Delete it.'
    AI assistant does NOT delete immediately; returns suggestedAction confirmation card.
    After user confirms, plan is deleted.
    """
    plan = Plan(user_id=test_user.id, title="Old Throwaway Plan", period="Spring")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    task = PlanTask(plan_id=plan.id, title="Throwaway Task", duration_minutes=45)
    db_session.add(task)
    db_session.commit()

    query = "I don't like this plan. Delete it."
    intent = heuristic_classify_intent(query)
    assert intent["tool"] == "plan_delete"
    assert intent["args"]["confirmed"] is False

    # First pass: returns confirmation card
    result = await agent_orchestrator.run(
        user_id=test_user.id,
        query=query,
        conversation_id="conv_test_ex_d",
        db=db_session
    )

    assert result["suggestedAction"] is not None
    assert result["suggestedAction"]["actionType"] == "delete_plan"
    assert result["suggestedAction"]["status"] == "pending"
    # Plan must NOT be deleted yet!
    assert db_session.query(Plan).filter(Plan.id == plan.id).first() is not None

    # Second pass: when user confirms permanently
    confirm_query = "Yes, permanently delete my plan."
    confirm_res = await agent_orchestrator.run(
        user_id=test_user.id,
        query=confirm_query,
        conversation_id="conv_test_ex_d",
        db=db_session
    )

    assert "deleted" in confirm_res["content"].lower()
    # Now plan is deleted from DB
    assert db_session.query(Plan).filter(Plan.id == plan.id).first() is None

@pytest.mark.asyncio
async def test_ai_assistant_example_e_reschedule_task(db_session: Session, test_user: User):
    """
    Example E: User says 'Move my Java study session to tomorrow at 4 PM.'
    AI assistant updates the task scheduled_date and start_time.
    """
    test_user.timezone = "America/Los_Angeles"
    db_session.commit()

    plan = Plan(user_id=test_user.id, title="Java Sprint", period="Current Week")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    task = PlanTask(plan_id=plan.id, title="Java Core Study Session", duration_minutes=60, completed=False)
    db_session.add(task)
    db_session.commit()

    query = "Move my Java study session to tomorrow at 4 PM."
    intent = heuristic_classify_intent(query, user_tz=test_user.timezone)
    assert intent["tool"] == "plan_reschedule_task"

    result = await agent_orchestrator.run(
        user_id=test_user.id,
        query=query,
        conversation_id="conv_test_ex_e",
        db=db_session
    )

    assert "04:00 PM" in result["content"] or "4:00 PM" in result["content"]
    db_session.refresh(task)
    assert task.start_time is not None
    assert "04:00 PM" in task.start_time
    assert task.scheduled_date is not None
