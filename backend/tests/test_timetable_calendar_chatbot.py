import pytest
from datetime import datetime, timedelta
from app.agent.graph import AureliaAgent
from app.agent.tool_registry import tool_registry
from app.db.models import Document, TimetableEntry, AcademicEvent, Conversation
from app.services.date_parser import get_user_current_date

@pytest.mark.asyncio
async def test_chatbot_timetable_monday(db_session, test_user):
    agent = AureliaAgent()
    conv = Conversation(user_id=test_user.id, title="Test Chat")
    db_session.add(conv)
    db_session.commit()

    tt = TimetableEntry(
        user_id=test_user.id,
        course_name="Software Engineering",
        course_code="CS503",
        day_of_week="Monday",
        start_time="09:00 AM",
        end_time="10:00 AM",
        room="LH-1",
        instructor="Prof. Davis",
        class_type="Theory"
    )
    db_session.add(tt)
    db_session.commit()

    res = await agent.run(
        user_id=test_user.id,
        query="What classes do I have on Monday?",
        conversation_id=conv.id,
        db=db_session
    )
    content = res.get("content", "")
    assert "Software Engineering" in content
    assert "09:00 AM - 10:00 AM" in content or "09:00 AM" in content

@pytest.mark.asyncio
async def test_chatbot_timetable_subject_and_tomorrow(db_session, test_user):
    agent = AureliaAgent()
    conv = Conversation(user_id=test_user.id, title="Test Chat")
    db_session.add(conv)
    db_session.commit()

    # Determine tomorrow's weekday
    curr_d = get_user_current_date(test_user.timezone)
    tomorrow_day = (curr_d + timedelta(days=1)).strftime("%A")

    tt = TimetableEntry(
        user_id=test_user.id,
        course_name="Java Programming",
        course_code="CS401",
        day_of_week=tomorrow_day,
        start_time="11:00 AM",
        end_time="12:00 PM",
        room="Room 204",
        instructor="Dr. Clark",
        class_type="Theory"
    )
    db_session.add(tt)
    db_session.commit()

    # Query: When is my Java class?
    res_subj = await agent.run(
        user_id=test_user.id,
        query="When is my Java class?",
        conversation_id=conv.id,
        db=db_session
    )
    assert "Java Programming" in res_subj.get("content", "")

    # Query: What classes do I have tomorrow?
    res_tom = await agent.run(
        user_id=test_user.id,
        query="What classes do I have tomorrow?",
        conversation_id=conv.id,
        db=db_session
    )
    assert "Java Programming" in res_tom.get("content", "")

@pytest.mark.asyncio
async def test_chatbot_timetable_free_time_check(db_session, test_user):
    agent = AureliaAgent()
    conv = Conversation(user_id=test_user.id, title="Test Chat")
    db_session.add(conv)
    db_session.commit()

    tt = TimetableEntry(
        user_id=test_user.id,
        course_name="Computer Networks",
        course_code="CS504",
        day_of_week="Wednesday",
        start_time="02:00 PM",
        end_time="03:00 PM",
        room="LH-3"
    )
    db_session.add(tt)
    db_session.commit()

    # Query with conflict: between 2 PM and 4 PM on Wednesday
    res = await agent.run(
        user_id=test_user.id,
        query="Am I free between 2 PM and 4 PM on Wednesday?",
        conversation_id=conv.id,
        db=db_session
    )
    content = res.get("content", "")
    assert "not free" in content.lower() or "Computer Networks" in content

    # Query without conflict: between 9 AM and 11 AM on Wednesday
    res_free = await agent.run(
        user_id=test_user.id,
        query="Am I free between 9 AM and 11 AM on Wednesday?",
        conversation_id=conv.id,
        db=db_session
    )
    content_free = res_free.get("content", "")
    assert "free" in content_free.lower()

@pytest.mark.asyncio
async def test_chatbot_academic_events(db_session, test_user):
    agent = AureliaAgent()
    conv = Conversation(user_id=test_user.id, title="Test Chat")
    db_session.add(conv)
    db_session.commit()

    ev1 = AcademicEvent(
        user_id=test_user.id,
        event_name="First Internal Assessment (IA-1)",
        category="INTERNAL_ASSESSMENT",
        start_date="2026-09-10",
        end_date="2026-09-15",
        description="First CIE test"
    )
    ev2 = AcademicEvent(
        user_id=test_user.id,
        event_name="Christmas Vacation",
        category="HOLIDAY",
        start_date="2026-12-24",
        end_date="2026-12-31",
        description="Winter holiday"
    )
    ev3 = AcademicEvent(
        user_id=test_user.id,
        event_name="Semester End Examinations",
        category="EXAM",
        start_date="2026-12-10",
        end_date="2026-12-22",
        description="SEE Theory Exams"
    )
    db_session.add_all([ev1, ev2, ev3])
    db_session.commit()

    # Query: When is IA 1?
    res_ia = await agent.run(
        user_id=test_user.id,
        query="When is IA 1?",
        conversation_id=conv.id,
        db=db_session
    )
    assert "2026-09-10" in res_ia.get("content", "")

    # Query: What examinations are happening in December?
    res_exam = await agent.run(
        user_id=test_user.id,
        query="What examinations are happening in December?",
        conversation_id=conv.id,
        db=db_session
    )
    assert "Semester End Examinations" in res_exam.get("content", "")

    # Query: List all holidays
    res_holidays = await agent.run(
        user_id=test_user.id,
        query="List all holidays",
        conversation_id=conv.id,
        db=db_session
    )
    assert "Christmas Vacation" in res_holidays.get("content", "")

@pytest.mark.asyncio
async def test_chatbot_combined_academic_and_timetable_query(db_session, test_user):
    agent = AureliaAgent()
    conv = Conversation(user_id=test_user.id, title="Test Chat")
    db_session.add(conv)
    db_session.commit()

    # IA 1 starts on Thursday 2026-09-10
    ev = AcademicEvent(
        user_id=test_user.id,
        event_name="Internal Assessment 1",
        category="INTERNAL_ASSESSMENT",
        start_date="2026-09-10", # Thursday
        end_date="2026-09-15"
    )
    # User has Java on Thursdays
    tt = TimetableEntry(
        user_id=test_user.id,
        course_name="Java Programming",
        course_code="CS401",
        day_of_week="Thursday",
        start_time="09:00 AM",
        end_time="10:00 AM",
        room="LH-2"
    )
    db_session.add_all([ev, tt])
    db_session.commit()

    res = await agent.run(
        user_id=test_user.id,
        query="Do I have a Java class on the day of my internal assessment?",
        conversation_id=conv.id,
        db=db_session
    )
    content = res.get("content", "")
    assert "Internal Assessment 1" in content
    assert "Java Programming" in content
    assert "Thursday" in content

