import pytest
from datetime import datetime
from app.db.models import User, Timetable, TimetablePeriod
from app.agent.graph import agent_orchestrator

@pytest.fixture(scope="function")
def populated_timetable(db_session, test_user):
    tt = Timetable(
        user_id=test_user.id,
        name="Semester 5 Timetable",
        academic_year="2026-2027",
        semester="5",
        section="A"
    )
    db_session.add(tt)
    db_session.commit()
    db_session.refresh(tt)

    periods = [
        # Monday: Java at 9-10, DBMS at 10-11, Free gap from 11-14, then OS at 14-15
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Monday",
            subject_name="Java Programming",
            subject_code="CS301",
            start_time="09:00",
            end_time="10:00",
            room="LH-101",
            faculty="Dr. Alan",
            class_type="Lecture"
        ),
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Monday",
            subject_name="Database Management Systems",
            subject_code="CS302",
            start_time="10:00",
            end_time="11:00",
            room="LH-102",
            faculty="Dr. Sharma",
            class_type="Lecture"
        ),
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Monday",
            subject_name="Operating Systems",
            subject_code="CS304",
            start_time="14:00",
            end_time="15:00",
            room="LH-103",
            faculty="Prof. Miller",
            class_type="Lecture"
        ),
        # Wednesday: Morning class 9-10, Gap 10-14, Lab 14-16
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Wednesday",
            subject_name="Computer Networks",
            subject_code="CS303",
            start_time="09:00",
            end_time="10:00",
            room="LH-104",
            faculty="Dr. Gupta",
            class_type="Lecture"
        ),
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Wednesday",
            subject_name="DBMS Lab",
            subject_code="CS302L",
            start_time="14:00",
            end_time="16:00",
            room="Lab 2",
            faculty="Dr. Sharma",
            class_type="Lab"
        ),
        # Friday: Class 10-11
        TimetablePeriod(
            timetable_id=tt.id,
            user_id=test_user.id,
            day_of_week="Friday",
            subject_name="Web Technologies",
            subject_code="CS306",
            start_time="10:00",
            end_time="11:00",
            room="LH-105",
            faculty="Prof. Taylor",
            class_type="Lecture"
        )
    ]
    for p in periods:
        db_session.add(p)
    db_session.commit()
    return tt

@pytest.mark.asyncio
async def test_chatbot_empty_timetable_message(db_session, test_user):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Show my complete timetable",
        conversation_id="conv_tt_empty",
        db=db_session
    )
    assert resp["role"] == "assistant"
    assert "You have not created a timetable yet" in resp["content"]
    assert "Knowledge Base under the Timetable section" in resp["content"]

@pytest.mark.asyncio
async def test_chatbot_query_1_complete_timetable(db_session, test_user, populated_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Show my complete timetable",
        conversation_id="conv_tt_1",
        db=db_session
    )
    assert resp["role"] == "assistant"
    content = resp["content"]
    assert "Monday:" in content
    assert "Java Programming" in content
    assert "Wednesday:" in content
    assert "DBMS Lab" in content
    assert "Friday:" in content
    assert "Web Technologies" in content

@pytest.mark.asyncio
async def test_chatbot_query_2_tomorrows_classes(db_session, test_user, populated_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What classes do I have tomorrow?",
        conversation_id="conv_tt_2",
        db=db_session
    )
    assert resp["role"] == "assistant"
    assert ("timetable for tomorrow" in resp["content"].lower()) or ("no classes scheduled for tomorrow" in resp["content"].lower())

@pytest.mark.asyncio
async def test_chatbot_query_3_monday_timetable(db_session, test_user, populated_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What is my Monday timetable?",
        conversation_id="conv_tt_3",
        db=db_session
    )
    assert resp["role"] == "assistant"
    content = resp["content"]
    assert "Monday" in content
    assert "Java Programming" in content
    assert "Database Management Systems" in content
    assert "Operating Systems" in content

@pytest.mark.asyncio
async def test_chatbot_query_4_next_java_class(db_session, test_user, populated_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="When is my next Java class?",
        conversation_id="conv_tt_4",
        db=db_session
    )
    assert resp["role"] == "assistant"
    content = resp["content"]
    assert "Java Programming" in content
    assert "LH-101" in content
    assert "Dr. Alan" in content

@pytest.mark.asyncio
async def test_chatbot_query_5_free_periods_wednesday(db_session, test_user, populated_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Do I have any free periods on Wednesday?",
        conversation_id="conv_tt_5",
        db=db_session
    )
    assert resp["role"] == "assistant"
    content = resp["content"]
    assert "Wednesday" in content
    assert "10:00 to 14:00" in content or "10:00" in content
    assert "free" in content.lower()

@pytest.mark.asyncio
async def test_chatbot_query_6_classes_between_times(db_session, test_user, populated_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What classes do I have between 10 AM and 1 PM?",
        conversation_id="conv_tt_6",
        db=db_session
    )
    assert resp["role"] == "assistant"
    content = resp["content"]
    assert "10 am and 1 pm" in content.lower()
    assert "Database Management Systems" in content or "Web Technologies" in content

@pytest.mark.asyncio
async def test_chatbot_query_7_next_lab(db_session, test_user, populated_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="When is my next lab?",
        conversation_id="conv_tt_7",
        db=db_session
    )
    assert resp["role"] == "assistant"
    content = resp["content"]
    assert "DBMS Lab" in content
    assert "Lab 2" in content
    assert "Wednesday" in content

@pytest.mark.asyncio
async def test_chatbot_query_8_which_faculty_teaches_dbms(db_session, test_user, populated_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Which faculty teaches DBMS?",
        conversation_id="conv_tt_8",
        db=db_session
    )
    assert resp["role"] == "assistant"
    content = resp["content"]
    assert "Dr. Sharma" in content
    assert "Database Management Systems" in content or "DBMS" in content

@pytest.mark.asyncio
async def test_chatbot_query_9_last_class_today(db_session, test_user, populated_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What is my last class today?",
        conversation_id="conv_tt_9",
        db=db_session
    )
    assert resp["role"] == "assistant"
    content = resp["content"]
    assert ("last class" in content.lower()) or ("no classes scheduled for today" in content.lower())

@pytest.mark.asyncio
async def test_chatbot_query_10_friday_timetable(db_session, test_user, populated_timetable):
    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Friday timetable",
        conversation_id="conv_tt_10",
        db=db_session
    )
    assert resp["role"] == "assistant"
    content = resp["content"]
    assert "Friday" in content
    assert "Web Technologies" in content
    assert "LH-105" in content

@pytest.mark.asyncio
async def test_chatbot_reflects_updated_timetable(db_session, test_user, populated_timetable):
    friday_p = db_session.query(TimetablePeriod).filter(
        TimetablePeriod.timetable_id == populated_timetable.id,
        TimetablePeriod.day_of_week == "Friday"
    ).first()
    friday_p.subject_name = "Machine Learning"
    friday_p.subject_code = "CS405"
    friday_p.room = "LH-999"
    friday_p.faculty = "Dr. Hinton"
    db_session.commit()

    resp = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Friday timetable",
        conversation_id="conv_tt_edit",
        db=db_session
    )
    assert resp["role"] == "assistant"
    content = resp["content"]
    assert "Machine Learning" in content
    assert "LH-999" in content
    assert "Dr. Hinton" in content
    assert "Web Technologies" not in content
