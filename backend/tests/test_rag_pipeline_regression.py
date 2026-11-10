"""
AURELIA AI — Comprehensive RAG Pipeline & Error Handling Regression Suite
Tests required by Part 7:
- Test A: PostgreSQL decision (relational constraints, reliable transactions, ADR-017, unique constraint)
- Test B: Load-test metrics (145 ms, 420 ms, 0.8%, 250 virtual users)
- Test C: Incomplete testing activities (disaster-recovery drill, >250 concurrent users, independent penetration test, not a production capacity guarantee)
- Test D: Missing information (grounded statement that cloud provider is not specified)
- Test E: Rate limit (HTTP 429 / RESOURCE_EXHAUSTED handling, no fabricated answer, no fallback, no persistence, no infinite retry)
- Test F: Other Gemini failures (invalid credentials, timeouts, server errors, safety blocks, empty responses, MAX_TOKENS)
- Test G: Successful Gemini generation (generated answer, citations, persistence)
- Test H: Evidence integrity (source citations correspond to selected evidence, excerpts preserve original wording)
"""
import pytest
import uuid
from unittest.mock import AsyncMock, patch
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.db.models import User, Document, DocumentChunk, Conversation, Message
from app.rag.embeddings import compute_local_embedding
from app.rag.retrieval import (
    retrieve_knowledge,
    format_grounded_rag_response,
    format_page_citation
)
from app.agent.graph import agent_orchestrator
from app.services.gemini_client import call_gemini_api, GeminiCallResult


# ---------------------------------------------------------------------------
# Corpus Fixture matching AURELIA_RAG_Test_Document.pdf
# ---------------------------------------------------------------------------
@pytest.fixture
def rag_test_document_corpus(db_session: Session, test_user: User):
    doc = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="AURELIA_RAG_Test_Document.pdf",
        file_size=64000,
        mime_type="application/pdf",
        status="indexed",
        page_count=2
    )
    db_session.add(doc)

    # Chunk 1: Architecture overview
    c1 = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=1,
        page_number=1,
        content=(
            "The frontend uses React 19 and Vite. The backend uses FastAPI with Python 3.12. "
            "The relational database is PostgreSQL 16. The architecture decision record is ADR-017."
        ),
        embedding=compute_local_embedding("FastAPI Python PostgreSQL architecture decision record ADR-017")
    )

    # Chunk 2: PostgreSQL decision & registration constraints
    c2 = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=2,
        page_number=1,
        content=(
            "The pilot deployment runs in the Singapore region. The architecture decision record is ADR-017. "
            "Its main reason for choosing PostgreSQL was the need for relational constraints and reliable "
            "transactions during event registration. The team rejected a document database for the registration "
            "ledger because duplicate registrations must be prevented with a unique constraint on (event_id, student_id). "
            "3. Performance Experiment The team tested the registration endpoint using 250 concurrent virtual users over a 12-minute run."
        ),
        embedding=compute_local_embedding(
            "Singapore ADR-017 PostgreSQL relational constraints reliable transactions duplicate registrations unique constraint event_id student_id"
        )
    )

    # Chunk 3: Performance test results & capacity limitation
    c3 = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=3,
        page_number=1,
        content=(
            "The median response time was 145 milliseconds, the 95th-percentile response time (p95) was 420 milliseconds, "
            "and the measured error rate was 0.8%. The test environment used a 2-vCPU application instance and a PostgreSQL "
            "instance with 4 GB of memory. These figures describe only the pilot test; they are not a production capacity guarantee."
        ),
        embedding=compute_local_embedding(
            "median response time 145 milliseconds p95 420 milliseconds measured error rate 0.8% pilot test not a production capacity guarantee"
        )
    )

    # Chunk 6: Incomplete tests & missing cloud vendor statement
    c6 = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=6,
        page_number=2,
        content=(
            "The pilot showed that database constraints are an important last line of defense against duplicate registrations. "
            "It also showed that p95 latency is more informative than median latency alone when investigating slow requests. "
            "The team has not yet conducted a disaster-recovery drill, a test with more than 250 concurrent users, or an "
            "independent penetration test. The document does not specify a named cloud vendor, the names of individual "
            "developers, or a customer-support phone number."
        ),
        embedding=compute_local_embedding(
            "disaster-recovery drill 250 concurrent users independent penetration test not conducted not specify a named cloud vendor"
        )
    )

    # Chunk 7: Exact Values Reference table
    c7 = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=7,
        page_number=2,
        content=(
            "7. Exact Values Reference\n"
            "Item\nValue\n"
            "Architecture decision record\nADR-017\n"
            "Backend runtime\nPython 3.12\n"
            "Database version\nPostgreSQL 16\n"
            "Load-test concurrency\n250 virtual users\n"
            "Load-test duration\n12 minutes\n"
            "Median response time\n145 ms\n"
            "p95 response time\n420 ms\n"
            "Measured error rate\n0.8%\n"
            "Audit-event retention\n180 days\n"
        ),
        embedding=compute_local_embedding(
            "Exact Values Reference ADR-017 Python 3.12 PostgreSQL 16 250 virtual users 145 ms 420 ms 0.8%"
        )
    )

    db_session.add_all([c1, c2, c3, c6, c7])
    db_session.commit()
    return {
        "doc": doc,
        "c1": c1,
        "c2": c2,
        "c3": c3,
        "c6": c6,
        "c7": c7
    }


# ==============================================================================
# TEST A: PostgreSQL decision
# ==============================================================================
@pytest.mark.asyncio
async def test_a_postgresql_decision(rag_test_document_corpus, db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="PostgreSQL Decision")
    db_session.add(conv)
    db_session.commit()

    expected_answer = (
        "The team chose PostgreSQL because of the need for relational constraints and reliable transactions "
        "during event registration, specifically preventing duplicate registrations with a unique constraint "
        "on (event_id, student_id). The architecture decision record is ADR-017."
    )

    with patch("app.agent.graph.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = GeminiCallResult(
            success=True,
            text=expected_answer,
            finish_reason="STOP",
            prompt_tokens=150,
            output_tokens=45
        )

        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="What was the reason for choosing PostgreSQL, and what is the architecture decision record number?",
            conversation_id=conv.id,
            db=db_session
        )

    content = res["content"]
    assert res.get("status") != "error"
    assert "**Answer:**" in content
    # Expected key elements
    assert "ADR-017" in content
    assert "relational constraints" in content
    assert "(event_id, student_id)" in content
    # Answer must not begin with Singapore deployment statement
    direct_ans = content.split("**Grounded Evidentiary Sources:**")[0]
    assert not direct_ans.strip().startswith("**Answer:**\nThe pilot deployment runs in the Singapore region")
    # Grounded citations attached
    assert len(res["citations"]) >= 1
    assert res["citations"][0]["title"] == "AURELIA_RAG_Test_Document.pdf"


# ==============================================================================
# TEST B: Load-test metrics
# ==============================================================================
@pytest.mark.asyncio
async def test_b_load_test_metrics(rag_test_document_corpus, db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Load Test Metrics")
    db_session.add(conv)
    db_session.commit()

    expected_answer = (
        "The load-testing results were: a median response time of 145 ms, a p95 response time of 420 ms, "
        "a measured error rate of 0.8%, and 250 concurrent virtual users over a 12-minute run."
    )

    with patch("app.agent.graph.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = GeminiCallResult(
            success=True,
            text=expected_answer,
            finish_reason="STOP"
        )

        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="What were the load-testing results, including median response time, p95 response time, error rate, and concurrent virtual users?",
            conversation_id=conv.id,
            db=db_session
        )

    content = res["content"]
    assert "145" in content
    assert "420" in content
    assert "0.8%" in content
    assert "250" in content


# ==============================================================================
# TEST C: Incomplete testing activities and load-test limitation
# ==============================================================================
@pytest.mark.asyncio
async def test_c_incomplete_testing_activities(rag_test_document_corpus, db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Incomplete Testing")
    db_session.add(conv)
    db_session.commit()

    expected_answer = (
        "The testing activities that have not yet been completed are:\n"
        "1. A disaster-recovery drill\n"
        "2. A test with more than 250 concurrent users\n"
        "3. An independent penetration test\n\n"
        "Regarding the load-test results, the document explicitly states that the figures describe only the "
        "pilot test and are not a production capacity guarantee."
    )

    with patch("app.agent.graph.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = GeminiCallResult(
            success=True,
            text=expected_answer,
            finish_reason="STOP"
        )

        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Which testing activities have not yet been completed, and what limitation does the document state about the load-test results?",
            conversation_id=conv.id,
            db=db_session
        )

    content = res["content"]
    # All 4 core facts must be present
    assert "disaster-recovery drill" in content
    assert "250 concurrent users" in content
    assert "penetration test" in content
    assert "not a production capacity guarantee" in content
    # Main answer must NOT be the Exact Values Reference table
    direct_ans = content.split("**Grounded Evidentiary Sources:**")[0]
    assert "7. Exact Values Reference" not in direct_ans


# ==============================================================================
# TEST D: Missing information handling
# ==============================================================================
@pytest.mark.asyncio
async def test_d_missing_cloud_provider(rag_test_document_corpus, db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Missing Cloud Provider")
    db_session.add(conv)
    db_session.commit()

    expected_answer = (
        "The uploaded document does not specify a named cloud vendor or provider selected for production deployment."
    )

    with patch("app.agent.graph.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = GeminiCallResult(
            success=True,
            text=expected_answer,
            finish_reason="STOP"
        )

        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Which named cloud provider was selected for production deployment?",
            conversation_id=conv.id,
            db=db_session
        )

    content = res["content"]
    assert any(phrase in content.lower() for phrase in [
        "does not specify",
        "not mentioned",
        "do not provide enough information"
    ])


# ==============================================================================
# TEST E: Rate limit & quota error handling (HTTP 429)
# ==============================================================================
@pytest.mark.asyncio
async def test_e_rate_limit_handling(rag_test_document_corpus, db_session, test_user, client):
    from app.core.security import create_access_token
    token = create_access_token(data={"sub": test_user.id})
    headers = {"Authorization": f"Bearer {token}"}

    conv = Conversation(user_id=test_user.id, title="Rate Limit Test")
    db_session.add(conv)
    db_session.commit()

    # Mock Gemini returning 429 quota exhaustion
    mock_429_result = GeminiCallResult(
        success=False,
        error_category="quota_exhaustion",
        status_code=429,
        user_message="Gemini couldn't generate an answer because your API quota has been exhausted. Please check your plan, billing details, or quota allocation.",
        raw_error="You exceeded your current quota"
    )

    with patch("app.agent.graph.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_429_result

        # Run via orchestrator
        res = await agent_orchestrator.run(
            user_id=test_user.id,
            query="Which testing activities have not yet been completed?",
            conversation_id=conv.id,
            db=db_session
        )

        # 1. Structured error status returned
        assert res["status"] == "error"
        assert res["error"]["category"] == "quota_exhaustion"
        assert "quota has been exhausted" in res["content"]
        # 2. NO retrieved snippet fallback presented as answer
        assert "7. Exact Values Reference" not in res["content"]
        assert "The pilot showed that database constraints" not in res["content"]
        # 3. NO fake citations attached
        assert len(res["citations"]) == 0

    # 4. Verify API route chat_endpoint raises HTTP 429 and does NOT persist assistant message
    with patch("app.agent.graph.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_429_result

        api_res = client.post(
            "/api/chat",
            json={"message": "Which testing activities have not yet been completed?", "conversationId": conv.id},
            headers=headers
        )
        assert api_res.status_code == 429
        data = api_res.json()
        assert "quota has been exhausted" in data["detail"]

        # Confirm NO assistant message was saved to database
        asst_msgs = db_session.query(Message).filter(
            Message.conversation_id == conv.id,
            Message.role == "assistant"
        ).all()
        assert len(asst_msgs) == 0


# ==============================================================================
# TEST F: Other Gemini Failures (auth, timeout, safety, empty, MAX_TOKENS)
# ==============================================================================
@pytest.mark.asyncio
async def test_f_other_gemini_failures(rag_test_document_corpus, db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Other Failures")
    db_session.add(conv)
    db_session.commit()

    # 1. Invalid credentials
    mock_auth_err = GeminiCallResult(
        success=False,
        error_category="invalid_credentials",
        status_code=401,
        user_message="Gemini service is improperly configured or the API key is invalid. Please check your system configuration."
    )
    with patch("app.agent.graph.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_auth_err
        res = await agent_orchestrator.run(user_id=test_user.id, query="What is ADR-017?", conversation_id=conv.id, db=db_session)
        assert res["status"] == "error"
        assert "API key is invalid" in res["content"]

    # 2. Timeout
    mock_timeout = GeminiCallResult(
        success=False,
        error_category="timeout",
        status_code=504,
        user_message="The request to Gemini timed out. Please check your network connection and try again."
    )
    with patch("app.agent.graph.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_timeout
        res = await agent_orchestrator.run(user_id=test_user.id, query="What is ADR-017?", conversation_id=conv.id, db=db_session)
        assert res["status"] == "error"
        assert "timed out" in res["content"]

    # 3. Safety block
    mock_safety = GeminiCallResult(
        success=False,
        error_category="safety_block",
        status_code=200,
        finish_reason="SAFETY",
        user_message="The response was blocked by Gemini safety filters. Please rephrase your question."
    )
    with patch("app.agent.graph.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_safety
        res = await agent_orchestrator.run(user_id=test_user.id, query="What is ADR-017?", conversation_id=conv.id, db=db_session)
        assert res["status"] == "error"
        assert "safety filters" in res["content"]

    # 4. Truncation (MAX_TOKENS) — preserves available text with truncated flag
    mock_trunc = GeminiCallResult(
        success=True,
        text="The architecture decision record is ADR-017 which selected PostgreSQL.",
        finish_reason="MAX_TOKENS",
        truncated=True
    )
    with patch("app.agent.graph.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_trunc
        res = await agent_orchestrator.run(user_id=test_user.id, query="What is ADR-017?", conversation_id=conv.id, db=db_session)
        assert res.get("status") != "error"
        assert "ADR-017" in res["content"]


# ==============================================================================
# TEST G: Successful Gemini Generation & Persistence
# ==============================================================================
@pytest.mark.asyncio
async def test_g_successful_generation_and_persistence(rag_test_document_corpus, db_session, test_user, client):
    from app.core.security import create_access_token
    token = create_access_token(data={"sub": test_user.id})
    headers = {"Authorization": f"Bearer {token}"}

    conv = Conversation(user_id=test_user.id, title="Success Flow")
    db_session.add(conv)
    db_session.commit()

    valid_gemini_text = "The architecture decision record is ADR-017."
    mock_success = GeminiCallResult(
        success=True,
        text=valid_gemini_text,
        finish_reason="STOP"
    )

    with patch("app.agent.graph.call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_success
        api_res = client.post(
            "/api/chat",
            json={"message": "What is the ADR number?", "conversationId": conv.id},
            headers=headers
        )
        assert api_res.status_code == 200
        data = api_res.json()
        assert "**Answer:**" in data["content"]
        assert "ADR-017" in data["content"]
        assert "**Grounded Evidentiary Sources:**" in data["content"]
        assert len(data["citations"]) >= 1

        # Confirm saved in database
        saved_msg = db_session.query(Message).filter(Message.id == data["id"]).first()
        assert saved_msg is not None
        assert saved_msg.role == "assistant"
        assert "ADR-017" in saved_msg.content


# ==============================================================================
# TEST H: Evidence integrity
# ==============================================================================
@pytest.mark.asyncio
async def test_h_evidence_integrity(rag_test_document_corpus, db_session, test_user):
    retrieval_res = await retrieve_knowledge(
        "What was the reason for choosing PostgreSQL, and what is the architecture decision record number?",
        test_user.id,
        db_session,
        top_k=4
    )
    assert retrieval_res["mode"] == "targeted_rag"
    sources = retrieval_res["sources"]
    assert len(sources) >= 1

    top = sources[0]
    assert top["title"] == "AURELIA_RAG_Test_Document.pdf"
    assert top["page"] == 1
    assert "ADR-017" in top["fullContent"]
    # Excerpt wording matches database chunk content verbatim
    assert top["snippet"] in top["fullContent"]
