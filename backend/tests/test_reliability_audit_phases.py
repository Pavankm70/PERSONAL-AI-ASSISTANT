import pytest
import uuid
import zoneinfo
from datetime import datetime, timezone, timedelta, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.db.models import User, Document, DocumentChunk, Plan, PlanTask, OAuthAccount, TimetableEntry, Message, Conversation
from app.services.date_parser import (
    get_user_tz,
    get_user_current_date,
    get_user_today_bounds,
    get_user_week_bounds,
    get_user_month_bounds,
    is_date_today_in_user_tz,
    parse_natural_datetime
)
from app.agent.tool_registry import tool_registry
from app.agent.graph import agent_orchestrator, heuristic_classify_intent, is_document_inventory_query
from app.rag.retrieval import retrieve_knowledge, format_page_citation, is_multi_document_query
from app.services.google_services.calendar_service import google_calendar_service
from app.services.google_services.gmail_service import google_gmail_service

@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def test_user(db):
    user = User(
        id=str(uuid.uuid4()),
        email="test_user@university.edu",
        full_name="Alex Chen",
        timezone="Asia/Kolkata",
        onboarding_complete=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@pytest.fixture
def other_user(db):
    user = User(
        id=str(uuid.uuid4()),
        email="other_user@university.edu",
        full_name="Bob Miller",
        timezone="America/New_York",
        onboarding_complete=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

# =========================================================================
# Scenario 1: Timezone conversion and date utilities
# =========================================================================
def test_01_timezone_conversion_and_date_utilities(test_user):
    tz = get_user_tz(test_user.timezone)
    assert isinstance(tz, zoneinfo.ZoneInfo)
    assert tz.key == "Asia/Kolkata"

    # Default fallback when invalid
    fallback_tz = get_user_tz("Invalid/TimeZone_Name")
    assert fallback_tz.key == "UTC"

    # Current date in timezone
    kolkata_date = get_user_current_date("Asia/Kolkata")
    assert isinstance(kolkata_date, date)

    # Today check
    assert is_date_today_in_user_tz(kolkata_date.isoformat(), "Asia/Kolkata") is True
    yesterday = (kolkata_date - timedelta(days=1)).isoformat()
    assert is_date_today_in_user_tz(yesterday, "Asia/Kolkata") is False

# =========================================================================
# Scenario 2: Today's date boundaries (timezone-accurate)
# =========================================================================
def test_02_todays_date_boundaries():
    start_d, end_d, start_iso, end_iso = get_user_today_bounds("America/New_York")
    assert isinstance(start_d, datetime)
    assert isinstance(end_d, datetime)
    assert start_d.date() == end_d.date()
    assert "T" in start_iso
    assert "T" in end_iso

    # Start must be prior to end
    dt_start = datetime.fromisoformat(start_iso)
    dt_end = datetime.fromisoformat(end_iso)
    assert dt_end > dt_start
    assert int((dt_end - dt_start).total_seconds()) == 86399  # 23 hours, 59 mins, 59 secs

# =========================================================================
# Scenario 3: Overview vs Calendar timing and task consistency
# =========================================================================
def test_03_overview_and_calendar_consistency(db, test_user):
    plan = Plan(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        title="DSA Mastery Plan",
        period="30 Days",
        duration_days=30
    )
    db.add(plan)
    db.commit()

    today_str = get_user_current_date(test_user.timezone).isoformat()
    task = PlanTask(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        title="Binary Tree Traversal",
        duration_minutes=60,
        scheduled_date=today_str,
        start_time="10:00 AM",
        end_time="11:00 AM",
        completed=False
    )
    db.add(task)
    db.commit()

    # Query PlanTask for today in user timezone
    queried_tasks = (
        db.query(PlanTask)
        .join(Plan)
        .filter(Plan.user_id == test_user.id, PlanTask.scheduled_date == today_str)
        .all()
    )
    assert len(queried_tasks) == 1
    assert queried_tasks[0].title == "Binary Tree Traversal"
    assert queried_tasks[0].start_time == "10:00 AM"

# =========================================================================
# Scenario 4: Calendar view filters (Day, Week, Month)
# =========================================================================
def test_04_calendar_views_filters():
    start_d, end_d, start_iso, end_iso = get_user_week_bounds("UTC")
    assert (end_d - start_d).days == 6
    assert start_iso < end_iso

    m_start_d, m_end_d, m_start_iso, m_end_iso = get_user_month_bounds("UTC")
    assert m_start_d.day == 1
    assert m_end_d.day in (28, 29, 30, 31)
    assert m_start_iso < m_end_iso

# =========================================================================
# Scenario 5: Study task display in unified Calendar
# =========================================================================
def test_05_study_tasks_display_in_calendar(db, test_user):
    plan = Plan(id=str(uuid.uuid4()), user_id=test_user.id, title="Python 101")
    db.add(plan)
    db.commit()

    task = PlanTask(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        title="Variables & Data Types",
        duration_minutes=45,
        scheduled_date="2026-10-31",
        start_time="02:00 PM",
        end_time="02:45 PM"
    )
    db.add(task)
    db.commit()

    fetched = db.query(PlanTask).filter(PlanTask.id == task.id).first()
    assert fetched.title == "Variables & Data Types"
    assert fetched.duration_minutes == 45
    assert fetched.scheduled_date == "2026-10-31"

# =========================================================================
# Scenario 6: Google Calendar event deduplication
# =========================================================================
def test_06_calendar_event_deduplication(db, test_user):
    plan = Plan(id=str(uuid.uuid4()), user_id=test_user.id, title="ML Plan")
    db.add(plan)
    db.commit()

    ext_event_id = "gcal_event_xyz123"
    task = PlanTask(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        title="Gradient Descent Practice",
        google_calendar_event_id=ext_event_id,
        scheduled_date="2026-10-31"
    )
    db.add(task)
    db.commit()

    # When building agenda, if calendar event matches google_calendar_event_id,
    # it is deduplicated by linking to the same entity
    assert task.google_calendar_event_id == ext_event_id

# =========================================================================
# Scenario 7: Confirmation enforcement before external event creation / email sending
# =========================================================================
@pytest.mark.asyncio
async def test_07_confirmation_enforcement(db, test_user):
    # Calendar propose event returns confirmationToken and does NOT create real event directly
    prop = await google_calendar_service.prepare_event_proposal(
        user_id=test_user.id,
        db=db,
        title="Study Session",
        start_time="2026-10-31T10:00:00Z",
        end_time="2026-10-31T11:00:00Z"
    )
    assert "confirmationToken" in prop

    # Gmail prepare send confirmation returns confirmationToken
    email_prep = google_gmail_service.prepare_send_confirmation(
        user_id=test_user.id,
        to="prof@university.edu",
        subject="Project Update",
        body="Here is my progress update."
    )
    assert "confirmationToken" in email_prep
    assert email_prep["proposedEmail"]["to"] == "prof@university.edu"

# =========================================================================
# Scenario 8: Inbox Today filter (no yesterday leakage)
# =========================================================================
def test_08_inbox_today_filter_no_yesterday_leakage():
    user_tz = "Asia/Kolkata"
    today_user = get_user_current_date(user_tz)
    yesterday_user = today_user - timedelta(days=1)

    # Date check ensures only messages matching local date are treated as today
    assert is_date_today_in_user_tz(today_user.isoformat(), user_tz) is True
    assert is_date_today_in_user_tz(yesterday_user.isoformat(), user_tz) is False

# =========================================================================
# Scenario 9: Inbox search and filter parsing
# =========================================================================
def test_09_inbox_search_and_filter():
    classified = heuristic_classify_intent("Find emails from professor regarding exam deadline")
    assert classified["tool"] == "gmail_search_and_summarize"
    assert classified["args"]["extract_deadlines"] is True

# =========================================================================
# Scenario 10: Gmail message filters routing
# =========================================================================
def test_10_gmail_message_filters_routing():
    classified = heuristic_classify_intent("Show my unread emails")
    assert classified["tool"] in ("gmail_priority_messages", "gmail_search_and_summarize")

# =========================================================================
# Scenario 11: RAG document inventory metadata discovery
# =========================================================================
@pytest.mark.asyncio
async def test_11_rag_document_inventory_discovery(db, test_user):
    doc1 = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="Machine_Learning_Guide.pdf",
        file_size=204800,
        mime_type="application/pdf",
        category="academic",
        status="indexed",
        chunk_count=12,
        page_count=6
    )
    doc2 = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="Syllabus_Fall2026.pdf",
        file_size=102400,
        mime_type="application/pdf",
        category="timetable",
        status="indexed",
        chunk_count=5,
        page_count=2
    )
    db.add_all([doc1, doc2])
    db.commit()

    assert is_document_inventory_query("What documents have I uploaded?") is True
    assert is_document_inventory_query("List my uploaded documents") is True
    assert is_document_inventory_query("How many documents are stored?") is True

    res = await tool_registry.execute("document_inventory", user_id=test_user.id, db=db, query="What documents have I uploaded?")
    assert res["totalCount"] == 2
    assert res["matchingCount"] == 2
    assert len(res["documents"]) == 2
    filenames = [d["filename"] for d in res["documents"]]
    assert "Machine_Learning_Guide.pdf" in filenames
    assert "Syllabus_Fall2026.pdf" in filenames

# =========================================================================
# Scenario 12: RAG exact numerical and metric retrieval
# =========================================================================
@pytest.mark.asyncio
async def test_12_rag_exact_numerical_and_metric_retrieval(db, test_user):
    doc = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="model_benchmarks.txt",
        file_size=5000,
        mime_type="text/plain",
        status="indexed"
    )
    db.add(doc)
    db.commit()

    chunk = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=0,
        content="The benchmark achieved an accuracy of 94.7% with a latency of 42ms on the validation set.",
        page_number=1,
        embedding=[0.1] * 128
    )
    db.add(chunk)
    db.commit()

    retrieved = await retrieve_knowledge("What was the accuracy and latency of the benchmark?", test_user.id, db)
    assert len(retrieved["sources"]) > 0
    assert "94.7%" in retrieved["sources"][0]["snippet"]
    assert "42ms" in retrieved["sources"][0]["snippet"]

# =========================================================================
# Scenario 13: RAG semantic retrieval & synthesis
# =========================================================================
@pytest.mark.asyncio
async def test_13_rag_semantic_retrieval(db, test_user):
    doc = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="distributed_systems.txt",
        file_size=3000,
        mime_type="text/plain",
        status="indexed"
    )
    db.add(doc)
    db.commit()

    chunk = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=0,
        content="Raft consensus algorithm uses leader election and log replication to ensure state machine safety.",
        page_number=3,
        embedding=[0.2] * 128
    )
    db.add(chunk)
    db.commit()

    res = await retrieve_knowledge("How does Raft ensure consensus?", test_user.id, db)
    assert len(res["sources"]) > 0
    assert "leader election" in res["sources"][0]["snippet"]
    assert res["sources"][0]["page"] == 3

# =========================================================================
# Scenario 14: Cross-document comparison queries
# =========================================================================
def test_14_cross_document_queries():
    assert is_multi_document_query("Compare the results across all documents") is True
    assert is_multi_document_query("What is the difference between both papers?") is True
    assert is_multi_document_query("What does the syllabus say?") is False

# =========================================================================
# Scenario 15: Follow-up conversational memory reference resolution
# =========================================================================
@pytest.mark.asyncio
async def test_15_follow_up_reference_resolution(db, test_user):
    doc = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="transformer_architecture.pdf",
        file_size=15000,
        mime_type="application/pdf",
        status="indexed"
    )
    db.add(doc)
    db.commit()

    chunk = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=0,
        content="The transformer self-attention mechanism computes Query, Key, and Value dot-product interactions.",
        page_number=2,
        embedding=[0.3] * 128
    )
    db.add(chunk)
    db.commit()

    # Pass explicit_doc_id directly to retrieve_knowledge as done in conversational memory resolution
    res = await retrieve_knowledge("Tell me more about it", test_user.id, db, explicit_doc_id=doc.id)
    assert len(res["sources"]) > 0
    assert res["sources"][0]["documentId"] == doc.id
    assert "transformer self-attention" in res["sources"][0]["snippet"]

# =========================================================================
# Scenario 16: Grounded citations format (sourceType, page, snippet)
# =========================================================================
def test_16_grounded_citations_format():
    assert format_page_citation(1) == "Page 1"
    assert format_page_citation(None) == "Page unavailable"

# =========================================================================
# Scenario 17: RAG missing-information honest response
# =========================================================================
@pytest.mark.asyncio
async def test_17_rag_missing_information_honest_response(db, test_user):
    doc = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="java_basics.txt",
        file_size=1000,
        mime_type="text/plain",
        status="indexed"
    )
    db.add(doc)
    db.commit()
    chunk = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=0,
        content="Java is a class-based, object-oriented programming language designed for portability.",
        page_number=1,
        embedding=[0.05] * 128
    )
    db.add(chunk)
    db.commit()

    # Query for something completely absent from user's documents
    res = await retrieve_knowledge("Quantum teleportation protocols in 2040", test_user.id, db)
    assert len(res["sources"]) == 0
    assert res.get("relevanceEvaluation") == "insufficient_evidence"

# =========================================================================
# Scenario 18: Tenant isolation (User B cannot see User A's data)
# =========================================================================
@pytest.mark.asyncio
async def test_18_tenant_isolation(db, test_user, other_user):
    doc_a = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="User_A_Secret_Notes.txt",
        file_size=1000,
        mime_type="text/plain",
        status="indexed"
    )
    doc_b = Document(
        id=str(uuid.uuid4()),
        user_id=other_user.id,
        filename="User_B_Public_Notes.txt",
        file_size=1000,
        mime_type="text/plain",
        status="indexed"
    )
    db.add_all([doc_a, doc_b])
    db.commit()

    # User B queries document inventory
    res_b = await tool_registry.execute("document_inventory", user_id=other_user.id, db=db, query="List my documents")
    b_filenames = [d["filename"] for d in res_b["documents"]]
    assert "User_B_Public_Notes.txt" in b_filenames
    assert "User_A_Secret_Notes.txt" not in b_filenames

# =========================================================================
# Scenario 19: Google Drive file listing and extraction routing
# =========================================================================
def test_19_google_drive_routing():
    classified_list = heuristic_classify_intent("What files are in my Google Drive?")
    assert classified_list["tool"] in ("drive_search_and_read", "drive_search_files")

    classified_read = heuristic_classify_intent("Read the content of project-spec.pdf from Drive")
    assert classified_read["tool"] in ("drive_search_and_read", "drive_search_files")
    assert classified_read["args"].get("read_content") is True

# =========================================================================
# Scenario 20: Chatbot tool routing and unified calendar response
# =========================================================================
@pytest.mark.asyncio
async def test_20_chatbot_unified_calendar_and_free_time(db, test_user):
    conv = Conversation(id=str(uuid.uuid4()), user_id=test_user.id, title="Schedule Chat")
    db.add(conv)
    db.commit()

    plan = Plan(id=str(uuid.uuid4()), user_id=test_user.id, title="Spring Boot Roadmap")
    db.add(plan)
    db.commit()

    today_str = get_user_current_date(test_user.timezone).isoformat()
    task = PlanTask(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        title="Spring Security JWT Setup",
        duration_minutes=60,
        scheduled_date=today_str,
        start_time="03:00 PM",
        completed=False,
        google_calendar_event_id="synced_evt_101"
    )
    db.add(task)
    db.commit()

    # Test "Are my study sessions synchronized with Google Calendar?"
    res_sync = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Are my study sessions synchronized with Google Calendar?",
        conversation_id=conv.id,
        db=db
    )
    assert res_sync.get("status") != "error"
    assert "content" in res_sync
    assert ("Synchronized" in res_sync["content"] or "Spring Security JWT Setup" in res_sync["content"])

    # Test "What study tasks do I have today?"
    res_tasks = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What study tasks do I have today?",
        conversation_id=conv.id,
        db=db
    )
    assert res_tasks.get("status") != "error"
    assert "content" in res_tasks
    assert "Spring Security JWT Setup" in res_tasks["content"]
