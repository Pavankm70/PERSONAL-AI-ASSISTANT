"""
AURELIA AI — Evidence-Based RAG Answers with Source Citations Evaluation Test Suite
Verifies:
1. Correct answer and citation for a factual question.
2. Exact technical identifier retrieval.
3. Answers requiring multiple evidence passages.
4. Correct citations for multiple documents.
5. Correct page numbers when available.
6. Graceful handling of missing page metadata.
7. Honest handling of questions whose answers are absent.
8. No fabricated filenames, page numbers, or excerpts.
9. Strict user isolation (User A cannot access User B's documents).
10. Citations persist when conversation history is reloaded.
"""
import pytest
import uuid
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
from app.services.gemini_client import GeminiCallResult
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_gemini_for_citation_tests():
    """Mock Gemini API responses during citation tests to avoid live quota exhaustion."""
    async def fake_gemini(prompt, system_prompt="", **kwargs):
        query_part = prompt.lower()
        if "[user question]" in query_part:
            query_part = query_part.split("[user question]")[1]
        elif "user query:" in query_part:
            query_part = query_part.split("user query:")[1]

        if "algorithm" in query_part or "rs256" in query_part or "bearer token" in query_part:
            ans = "OAuth2 Bearer tokens are signed using the RS256 asymmetric cryptographic algorithm."
        elif "ceo" in query_part or "home address" in query_part or "mobile" in query_part:
            ans = "The uploaded documents do not provide enough information to answer this question."
        elif "compare" in query_part:
            ans = "In AURELIA_RAG_Test_Document.pdf, the team chose PostgreSQL under ADR-017, while in Architecture_Decisions.md, RS256 was selected for signing tokens."
        elif "caching ttl" in query_part or ("adr-018" in query_part and "database" in query_part):
            ans = "ADR-017 selected PostgreSQL for database storage, and ADR-018 selected Redis with a default TTL of 300 seconds for session tokens."
        elif "postgresql" in query_part or "adr-017" in query_part or "database" in query_part:
            ans = "The team chose PostgreSQL under ADR-017 for relational constraints and reliable transactions during event registration."
        else:
            ans = "The architecture decision record is ADR-017."
        return GeminiCallResult(success=True, text=ans, finish_reason="STOP")

    with patch("app.agent.graph.call_gemini_api", side_effect=fake_gemini), \
         patch("app.agent.graph.settings.GEMINI_API_KEY", "mock_api_key_test"):
        yield


@pytest.fixture
def evidence_corpus(db_session: Session, test_user: User):
    """
    Populates diverse test documents:
    1. AURELIA_RAG_Test_Document.pdf (with page numbers 1 and 2)
    2. Architecture_Decisions.md (missing page metadata, page=None)
    3. Research_Findings.txt (page=1)
    """
    # Doc 1: PDF with pages 1 and 2
    doc1 = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="AURELIA_RAG_Test_Document.pdf",
        file_size=64000,
        mime_type="application/pdf",
        status="indexed",
        page_count=2
    )
    db_session.add(doc1)

    chunk1_1 = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc1.id,
        user_id=test_user.id,
        chunk_index=0,
        page_number=1,
        content="The architecture decision record is ADR-017. Its main reason for choosing PostgreSQL was the need for relational constraints and reliable transactions during event registration.",
        embedding=compute_local_embedding("The architecture decision record is ADR-017 PostgreSQL relational constraints")
    )
    chunk1_2 = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc1.id,
        user_id=test_user.id,
        chunk_index=1,
        page_number=2,
        content="Under ADR-018, Redis was selected as the distributed caching layer with a default TTL of 300 seconds for session tokens.",
        embedding=compute_local_embedding("ADR-018 Redis distributed caching TTL 300 seconds")
    )
    db_session.add_all([chunk1_1, chunk1_2])

    # Doc 2: Markdown file with NO page metadata (page_number=None)
    doc2 = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="Architecture_Decisions.md",
        file_size=32000,
        mime_type="text/markdown",
        status="indexed",
        page_count=1
    )
    db_session.add(doc2)

    chunk2_1 = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc2.id,
        user_id=test_user.id,
        chunk_index=0,
        page_number=None,  # Missing page metadata!
        content="For identity federation, OAuth2 Bearer tokens are signed using the RS256 asymmetric cryptographic algorithm.",
        embedding=compute_local_embedding("identity federation OAuth2 Bearer tokens RS256 cryptographic algorithm")
    )
    db_session.add(chunk2_1)

    db_session.commit()
    return {
        "doc1": doc1,
        "doc2": doc2,
        "chunk1_1": chunk1_1,
        "chunk1_2": chunk1_2,
        "chunk2_1": chunk2_1
    }


# ==============================================================================
# TEST 1: Correct Answer and Citation for a Factual Question
# ==============================================================================
@pytest.mark.asyncio
async def test_factual_question_direct_answer_and_citations(evidence_corpus, db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="PostgreSQL Query")
    db_session.add(conv)
    db_session.commit()

    res = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Why did the team choose PostgreSQL, and what is the architecture decision record number?",
        conversation_id=conv.id,
        db=db_session
    )

    content = res["content"]
    assert "**Answer:**" in content
    assert "**Grounded Evidentiary Sources:**" in content
    assert "ADR-017" in content
    assert "PostgreSQL" in content
    assert "AURELIA_RAG_Test_Document.pdf (Page 1)" in content
    assert "> The architecture decision record is ADR-017" in content
    assert len(res["citations"]) >= 1
    assert res["citations"][0]["title"] == "AURELIA_RAG_Test_Document.pdf"
    assert res["citations"][0]["page"] == 1


# ==============================================================================
# TEST 2: Exact Technical Identifier Retrieval
# ==============================================================================
@pytest.mark.asyncio
async def test_exact_technical_identifier_retrieval(evidence_corpus, db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Algorithm Query")
    db_session.add(conv)
    db_session.commit()

    res = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What cryptographic algorithm signs the OAuth2 Bearer tokens?",
        conversation_id=conv.id,
        db=db_session
    )

    content = res["content"]
    assert "RS256" in content
    assert "**Grounded Evidentiary Sources:**" in content
    assert "Architecture_Decisions.md" in content
    assert any("RS256" in c["snippet"] for c in res["citations"])


# ==============================================================================
# TEST 3: Answers Requiring Multiple Evidence Passages
# ==============================================================================
@pytest.mark.asyncio
async def test_multiple_evidence_passages(evidence_corpus, db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Multi-Passage Query")
    db_session.add(conv)
    db_session.commit()

    res = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What was decided in ADR-017 for database storage, and what was decided in ADR-018 for caching TTL?",
        conversation_id=conv.id,
        db=db_session
    )

    content = res["content"]
    assert "**Answer:**" in content
    assert "**Grounded Evidentiary Sources:**" in content
    # Must cite both passages (Page 1 and Page 2)
    assert "(Page 1)" in content
    assert "(Page 2)" in content
    assert "ADR-017" in content
    assert "ADR-018" in content


# ==============================================================================
# TEST 4: Correct Citations for Multiple Documents
# ==============================================================================
@pytest.mark.asyncio
async def test_multi_document_citations(evidence_corpus, db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Cross-Doc Comparison")
    db_session.add(conv)
    db_session.commit()

    res = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Compare the database decision in AURELIA_RAG_Test_Document with the token signing in Architecture_Decisions",
        conversation_id=conv.id,
        db=db_session
    )

    content = res["content"]
    assert "**Answer:**" in content
    assert "**Grounded Evidentiary Sources:**" in content
    assert "AURELIA_RAG_Test_Document.pdf" in content
    assert "Architecture_Decisions.md" in content


# ==============================================================================
# TEST 5: Correct Page Numbers When Available
# ==============================================================================
def test_page_number_when_available():
    assert format_page_citation(1) == "Page 1"
    assert format_page_citation(42) == "Page 42"


# ==============================================================================
# TEST 6: Graceful Handling of Missing Page Metadata
# ==============================================================================
def test_missing_page_metadata_graceful_handling():
    assert format_page_citation(None) == "Page unavailable"
    assert format_page_citation(0) == "Page unavailable"
    assert format_page_citation(-1) == "Page unavailable"

    # In formatted RAG response:
    resp = format_grounded_rag_response(
        answer="Tokens use RS256.",
        sources=[{
            "title": "Architecture_Decisions.md",
            "page": None,
            "snippet": "OAuth2 Bearer tokens are signed using the RS256 algorithm."
        }]
    )
    assert "Architecture_Decisions.md (Page unavailable)" in resp
    assert "> OAuth2 Bearer tokens are signed using the RS256 algorithm." in resp


# ==============================================================================
# TEST 7: Honest Handling of Questions Whose Answers Are Absent
# ==============================================================================
@pytest.mark.asyncio
async def test_absent_fact_honest_handling(evidence_corpus, db_session, test_user):
    conv = Conversation(user_id=test_user.id, title="Absent Fact Query")
    db_session.add(conv)
    db_session.commit()

    res = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What is the CEO's personal home address and mobile phone number?",
        conversation_id=conv.id,
        db=db_session
    )

    content = res["content"]
    assert "**Answer:**" in content
    # Explicitly states limitation
    assert any(phrase in content.lower() for phrase in ["do not provide enough information", "not found", "does not mention", "no sufficient evidence"])
    # MUST NOT attach manufactured citations
    assert "AURELIA_RAG_Test_Document.pdf" not in content or len(res["citations"]) == 0


# ==============================================================================
# TEST 8: No Fabricated Filenames, Page Numbers, or Excerpts
# ==============================================================================
@pytest.mark.asyncio
async def test_no_fabricated_filenames_or_excerpts(evidence_corpus, db_session, test_user):
    res = await retrieve_knowledge("PostgreSQL relational transactions ADR-017", test_user.id, db_session, top_k=3)
    assert res["status"] == "success"
    sources = res["sources"]
    assert len(sources) > 0

    top_source = sources[0]
    # Check that title matches actual database Document filename
    assert top_source["title"] == "AURELIA_RAG_Test_Document.pdf"
    # Check that excerpt matches actual chunk content verbatim
    assert "ADR-017" in top_source["snippet"]
    assert "PostgreSQL" in top_source["snippet"]
    assert top_source["page"] == 1


# ==============================================================================
# TEST 9: Strict User Isolation (User A cannot access User B's documents)
# ==============================================================================
@pytest.mark.asyncio
async def test_tenant_isolation_strictly_enforced(evidence_corpus, db_session, test_user):
    # Create User B with confidential salary doc
    user_b = User(
        id="usr_confidential_999",
        email="confidential@corp.org",
        full_name="Confidential Officer"
    )
    db_session.add(user_b)
    db_session.commit()

    secret_doc = Document(
        id=str(uuid.uuid4()),
        user_id=user_b.id,
        filename="Executive_Payroll_Confidential.pdf",
        file_size=10000,
        mime_type="application/pdf",
        status="indexed"
    )
    db_session.add(secret_doc)

    secret_chunk = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=secret_doc.id,
        user_id=user_b.id,
        chunk_index=0,
        page_number=1,
        content="Confidential compensation: Annual package is $750,000 USD plus equity options.",
        embedding=compute_local_embedding("Confidential compensation Annual package $750,000")
    )
    db_session.add(secret_chunk)
    db_session.commit()

    # User A searches for compensation
    res_a = await retrieve_knowledge("What is the annual compensation package?", test_user.id, db_session, top_k=5)
    for s in res_a.get("sources", []):
        assert "$750,000" not in s["snippet"]
        assert s["title"] != "Executive_Payroll_Confidential.pdf"


# ==============================================================================
# TEST 10: Citations Persist When Conversation History is Reloaded
# ==============================================================================
def test_citations_persist_when_conversation_reloaded(client, test_user, db_session):
    from app.core.security import create_access_token

    token = create_access_token(data={"sub": test_user.id})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create a conversation
    conv = Conversation(user_id=test_user.id, title="Persisted RAG Session")
    db_session.add(conv)
    db_session.commit()

    # 2. Add an assistant message with grounded evidentiary citations
    test_citations = [
        {
            "id": "cit_1",
            "sourceType": "document",
            "title": "AURELIA_RAG_Test_Document.pdf",
            "page": 1,
            "pageLabel": "Page 1",
            "snippet": "The architecture decision record is ADR-017. Its main reason for choosing PostgreSQL was the need for relational constraints."
        }
    ]
    formatted_msg_content = (
        "**Answer:**\nThe team chose PostgreSQL under ADR-017 for relational constraints.\n\n"
        "**Grounded Evidentiary Sources:**\n\n"
        "AURELIA_RAG_Test_Document.pdf (Page 1)\n\n"
        "> The architecture decision record is ADR-017. Its main reason for choosing PostgreSQL was the need for relational constraints."
    )

    asst_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=formatted_msg_content,
        citations=test_citations,
        tool_executions=[{"toolName": "KnowledgeBaseRetrieval", "status": "success"}]
    )
    db_session.add(asst_msg)
    db_session.commit()

    # 3. Reload conversation via API GET /api/conversations/{id}
    res = client.get(f"/api/conversations/{conv.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["id"] == conv.id
    assert len(data["messages"]) == 1
    loaded_msg = data["messages"][0]
    assert loaded_msg["role"] == "assistant"
    assert "**Answer:**" in loaded_msg["content"]
    assert "**Grounded Evidentiary Sources:**" in loaded_msg["content"]
    assert len(loaded_msg["citations"]) == 1
    assert loaded_msg["citations"][0]["title"] == "AURELIA_RAG_Test_Document.pdf"
    assert loaded_msg["citations"][0]["page"] == 1
    assert "ADR-017" in loaded_msg["citations"][0]["snippet"]
