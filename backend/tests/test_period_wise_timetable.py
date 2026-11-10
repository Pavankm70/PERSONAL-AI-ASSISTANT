import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from app.db.models import User, Timetable, TimetablePeriod
from app.agent.graph import agent_orchestrator
from app.agent.tool_registry import tool_registry

@pytest.fixture(scope="function")
def period_wise_timetable(db_session, test_user):
    tt = Timetable(
        user_id=test_user.id,
        name="Semester 6 Engineering Timetable",
        academic_year="2026-2027",
        semester="6",
        section="B"
    )
    db_session.add(tt)
    db_session.commit()
    db_session.refresh(tt)

    periods = [
        # Monday: 4 periods
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Monday",
            period_number=1,
            subject_name="Artificial Intelligence",
            subject_code="AI401",
            start_time="09:00",
            end_time="10:00",
            room="Room 204",
            faculty="Dr. Sarah Jenkins",
            class_type="Lecture"
        ),
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Monday",
            period_number=2,
            subject_name="Machine Learning",
            subject_code="ML201",
            start_time="10:00",
            end_time="11:00",
            room="Room 102",
            faculty="Dr. Andrew Ng",
            class_type="Lecture"
        ),
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Monday",
            period_number=3,
            subject_name="Database Systems",
            subject_code="CS302",
            start_time="11:15",
            end_time="12:15",
            room="Lab 2",
            faculty="Prof. Alan Turing",
            class_type="Lab"
        ),
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Monday",
            period_number=4,
            subject_name="Operating Systems",
            subject_code="CS304",
            start_time="14:00",
            end_time="15:00",
            room="Room 301",
            faculty="Dr. Linus",
            class_type="Lecture"
        ),
        # Saturday: 2 periods
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Saturday",
            period_number=1,
            subject_name="Cloud Computing",
            subject_code="CS405",
            start_time="09:00",
            end_time="10:30",
            room="Room 501",
            faculty="Prof. Dean",
            class_type="Lecture"
        ),
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Saturday",
            period_number=2,
            subject_name="Capstone Seminar",
            subject_code="CS499",
            start_time="11:00",
            end_time="12:30",
            room="Auditorium",
            faculty="Dr. Grace",
            class_type="Seminar"
        )
    ]
    for p in periods:
        db_session.add(p)
    db_session.commit()
    return tt

# ---------------------------------------------------------------------------
# Test Chatbot Queries: Strict Period-Wise Retrieval
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_monday_first_period_returns_only_first_period(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What is my Monday first period?",
        conversation_id="conv_p1",
        db=db_session
    )
    content = resp["content"]
    assert "Period 1: Artificial Intelligence (AI401)" in content
    assert "09:00 - 10:00" in content
    assert "Room: Room 204" in content
    assert "Faculty: Dr. Sarah Jenkins" in content
    assert "Type: Lecture" in content
    # STRICT RULE: Must NOT return other periods or the full day
    assert "Machine Learning" not in content
    assert "Database Systems" not in content
    assert "Operating Systems" not in content

@pytest.mark.asyncio
async def test_monday_second_period_returns_only_second_period(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What is my Monday second period?",
        conversation_id="conv_p2",
        db=db_session
    )
    content = resp["content"]
    assert "Period 2: Machine Learning (ML201)" in content
    assert "10:00 - 11:00" in content
    assert "Artificial Intelligence" not in content
    assert "Operating Systems" not in content

@pytest.mark.asyncio
async def test_monday_fifth_period_non_existent_returns_strict_message(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What is my Monday fifth period?",
        conversation_id="conv_p5_none",
        db=db_session
    )
    content = resp["content"]
    # STRICT RULE: Must return exact selection message and NEVER fall back to full day
    assert "You don't have a scheduled period for that selection." in content
    assert "Artificial Intelligence" not in content
    assert "Machine Learning" not in content

@pytest.mark.asyncio
async def test_saturday_first_period(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What is my Saturday first period?",
        conversation_id="conv_sat_p1",
        db=db_session
    )
    content = resp["content"]
    assert "Period 1: Cloud Computing (CS405)" in content
    assert "09:00 - 10:30" in content
    assert "Room: Room 501" in content
    assert "Faculty: Prof. Dean" in content
    assert "Capstone Seminar" not in content
    assert "Artificial Intelligence" not in content

@pytest.mark.asyncio
async def test_monday_multiple_periods(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What are my Monday second and fourth periods?",
        conversation_id="conv_multi_p",
        db=db_session
    )
    content = resp["content"]
    assert "Period 2: Machine Learning (ML201)" in content
    assert "Period 4: Operating Systems (CS304)" in content
    # Periods 1 and 3 should not be in the output
    assert "Artificial Intelligence" not in content
    assert "Database Systems" not in content

@pytest.mark.asyncio
async def test_monday_range_periods(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="second to fourth periods on Monday",
        conversation_id="conv_range_p",
        db=db_session
    )
    content = resp["content"]
    assert "Period 2: Machine Learning (ML201)" in content
    assert "Period 3: Database Systems (CS302)" in content
    assert "Period 4: Operating Systems (CS304)" in content
    # Period 1 must not be in the output
    assert "Artificial Intelligence" not in content

@pytest.mark.asyncio
async def test_monday_period_at_specific_time(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What class do I have at 10 AM on Monday?",
        conversation_id="conv_at_time",
        db=db_session
    )
    content = resp["content"]
    assert "Period 2: Machine Learning (ML201)" in content
    assert "10:00 - 11:00" in content
    assert "Artificial Intelligence" not in content
    assert "Operating Systems" not in content

@pytest.mark.asyncio
async def test_monday_between_times(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What do I have between 10 AM and 12 PM on Monday?",
        conversation_id="conv_between_time",
        db=db_session
    )
    content = resp["content"]
    assert "Period 2: Machine Learning (ML201)" in content
    assert "Period 3: Database Systems (CS302)" in content
    assert "Artificial Intelligence" not in content
    assert "Operating Systems" not in content

@pytest.mark.asyncio
async def test_monday_full_day_schedule(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Show my Monday timetable",
        conversation_id="conv_monday_full",
        db=db_session
    )
    content = resp["content"]
    assert "timetable for **Monday**" in content
    assert "Period 1: Artificial Intelligence (AI401)" in content
    assert "Period 2: Machine Learning (ML201)" in content
    assert "Period 3: Database Systems (CS302)" in content
    assert "Period 4: Operating Systems (CS304)" in content

@pytest.mark.asyncio
async def test_saturday_full_day_schedule(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Show my Saturday timetable",
        conversation_id="conv_saturday_full",
        db=db_session
    )
    content = resp["content"]
    assert "timetable for **Saturday**" in content
    assert "Period 1: Cloud Computing (CS405)" in content
    assert "Period 2: Capstone Seminar (CS499)" in content

@pytest.mark.asyncio
async def test_complete_weekly_timetable(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Show my complete weekly timetable",
        conversation_id="conv_weekly_all",
        db=db_session
    )
    content = resp["content"]
    assert "**Monday:**" in content
    assert "Artificial Intelligence" in content
    assert "**Saturday:**" in content
    assert "Cloud Computing" in content

@pytest.mark.asyncio
async def test_sunday_period_empty_strict_message(db_session, test_user, period_wise_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What is my Sunday first period?",
        conversation_id="conv_sun_none",
        db=db_session
    )
    content = resp["content"]
    assert "You don't have a scheduled period for that selection." in content
    assert "Cloud Computing" not in content

# ---------------------------------------------------------------------------
# Test Direct Tool Registry Methods
# ---------------------------------------------------------------------------

def test_tool_registry_get_timetable_period(db_session, test_user, period_wise_timetable):
    res = tool_registry._tools["get_timetable_period"](
        user_id=test_user.id,
        db=db_session,
        day="Monday",
        period_number=1
    )
    assert res["status"] == "success"
    assert res["count"] == 1
    assert "Period 1: Artificial Intelligence (AI401)" in res["customMessage"]

def test_tool_registry_get_timetable_period_not_found(db_session, test_user, period_wise_timetable):
    res = tool_registry._tools["get_timetable_period"](
        user_id=test_user.id,
        db=db_session,
        day="Monday",
        period_number=99
    )
    assert res["status"] == "not_found"
    assert res["count"] == 0
    assert res["customMessage"] == "You don't have a scheduled period for that selection."

def test_tool_registry_get_timetable_for_day(db_session, test_user, period_wise_timetable):
    res = tool_registry._tools["get_timetable_for_day"](
        user_id=test_user.id,
        db=db_session,
        day="Saturday"
    )
    assert res["status"] == "success"
    assert res["count"] == 2
    assert "Cloud Computing" in res["customMessage"]
    assert "Capstone Seminar" in res["customMessage"]

# ---------------------------------------------------------------------------
# Test Timetable API: Period Number Persistence
# ---------------------------------------------------------------------------

def test_api_create_and_get_timetable_with_periods(client, auth_headers):
    # 1. Create timetable
    payload = {
        "name": "B.Tech Semester 7",
        "academic_year": "2026-2027",
        "semester": "7",
        "section": "A",
        "periods": [
            {
                "day_of_week": "Monday",
                "period_number": 1,
                "subject_name": "Deep Learning",
                "subject_code": "CS501",
                "start_time": "09:00",
                "end_time": "10:00",
                "room": "Room 101",
                "faculty": "Dr. LeCun",
                "class_type": "Lecture"
            },
            {
                "day_of_week": "Monday",
                "period_number": 2,
                "subject_name": "Robotics",
                "subject_code": "CS502",
                "start_time": "10:00",
                "end_time": "11:00",
                "room": "Lab 5",
                "faculty": "Dr. Thrun",
                "class_type": "Lab"
            },
            {
                "day_of_week": "Saturday",
                "period_number": 1,
                "subject_name": "Cybersecurity",
                "subject_code": "CS503",
                "start_time": "09:30",
                "end_time": "11:00",
                "room": "Room 205",
                "faculty": "Prof. Schneier",
                "class_type": "Lecture"
            }
        ]
    }
    create_res = client.post("/api/timetable", json=payload, headers=auth_headers)
    assert create_res.status_code == 201
    created_tt = create_res.json()
    assert len(created_tt["periods"]) == 3
    assert created_tt["periods"][0]["period_number"] == 1
    assert created_tt["periods"][1]["period_number"] == 2
    assert created_tt["periods"][2]["period_number"] == 1

    # 2. Add individual period
    tt_id = created_tt["id"]
    new_period_payload = {
        "day_of_week": "Saturday",
        "period_number": 2,
        "subject_name": "Blockchain",
        "subject_code": "CS504",
        "start_time": "11:15",
        "end_time": "12:45",
        "room": "Room 205",
        "faculty": "Prof. Nakamoto",
        "class_type": "Lecture"
    }
    add_res = client.post(f"/api/timetable/{tt_id}/periods", json=new_period_payload, headers=auth_headers)
    assert add_res.status_code == 201
    assert add_res.json()["period_number"] == 2

    # 3. Fetch current timetable
    get_res = client.get("/api/timetable", headers=auth_headers)
    assert get_res.status_code == 200
    tt_data = get_res.json()
    assert len(tt_data["periods"]) == 4

