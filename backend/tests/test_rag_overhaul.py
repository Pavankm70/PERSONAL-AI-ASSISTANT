import pytest
from unittest.mock import patch
from app.services.gemini_client import GeminiCallResult
from app.db.models import Document, DocumentChunk, Conversation, Message
from app.rag.retrieval import is_document_summary_query, summarize_document, retrieve_knowledge
from app.agent.graph import agent_orchestrator

@pytest.fixture(autouse=True)
def mock_gemini_for_overhaul_tests():
    async def fake_gemini(prompt, system_prompt="", **kwargs):
        if "intent" in system_prompt.lower() or "classify" in system_prompt.lower():
            if "resume" in prompt.lower() or "document" in prompt.lower():
                return GeminiCallResult(success=True, text='{"tool": "document_summary", "args": {"document_query": "resume"}}', finish_reason="STOP")
            return GeminiCallResult(success=True, text='{"tool": "rag_knowledge_lookup", "args": {"query": "test"}}', finish_reason="STOP")
        return GeminiCallResult(
            success=True,
            text="### Document Summary: Alex_Chen_Resume.pdf\n\n**Candidate:** Alex Chen\n**Education:** Stanford University\n**Skills:** AI systems researcher",
            finish_reason="STOP"
        )
    with patch("app.services.gemini_client.call_gemini_api", side_effect=fake_gemini), \
         patch("app.agent.graph.call_gemini_api", side_effect=fake_gemini):
        yield

def test_is_document_summary_query_detection():
    assert is_document_summary_query("What is this document about?") is True
    assert is_document_summary_query("Tell me about my uploaded resume") is True
    assert is_document_summary_query("Summarize this PDF") is True
    assert is_document_summary_query("Explain the entire document") is True
    assert is_document_summary_query("Give me a complete overview of these notes") is True
    # Targeted queries should be False
    assert is_document_summary_query("What is the learning rate used in Section 4?") is False
    assert is_document_summary_query("When is the assignment deadline?") is False

@pytest.mark.asyncio
async def test_document_summary_execution(db_session, test_user):
    # Create test resume document
    doc = Document(
        user_id=test_user.id,
        filename="Alex_Chen_Resume.pdf",
        file_size=54000,
        mime_type="application/pdf",
        status="indexed",
        category="academic"
    )
    db_session.add(doc)
    db_session.commit()

    chunk1 = DocumentChunk(
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=0,
        page_number=1,
        content="EDUCATION: MSc Computer Science, Stanford University. GPA: 3.9/4.0. Core: Distributed Systems, Deep Learning.",
        embedding=[0.1] * 256
    )
    chunk2 = DocumentChunk(
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=1,
        page_number=1,
        content="SKILLS & EXPERIENCE: Python, PyTorch, FastAPI, React, Kubernetes. Published research on Transformer optimization.",
        embedding=[0.2] * 256
    )
    db_session.add_all([chunk1, chunk2])
    db_session.commit()

    # Call summarize_document
    summary_res = await summarize_document(user_id=test_user.id, db=db_session, document_query="resume")
    assert summary_res["status"] == "success"
    assert summary_res["mode"] == "document_summary"
    assert "Alex_Chen_Resume.pdf" in summary_res["documentTitle"]
    assert len(summary_res["citations"]) >= 1
    assert "Alex_Chen_Resume.pdf" in summary_res["summary"] or "EDUCATION" in summary_res["summary"]

@pytest.mark.asyncio
async def test_agent_run_document_summary_intent(db_session, test_user):
    # Create conversation
    conv = Conversation(user_id=test_user.id, title="Resume Review")
    db_session.add(conv)
    db_session.commit()

    # Create document
    doc = Document(
        user_id=test_user.id,
        filename="CV_Alex_Chen.pdf",
        file_size=32000,
        mime_type="application/pdf",
        status="indexed"
    )
    db_session.add(doc)
    db_session.commit()

    chunk = DocumentChunk(
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=0,
        page_number=1,
        content="PROFILE: AI systems researcher with focus on agentic reasoning and vector retrieval architectures.",
        embedding=[0.05] * 256
    )
    db_session.add(chunk)
    db_session.commit()

    res = await agent_orchestrator.run(
        user_id=test_user.id,
        query="Tell me about my uploaded resume",
        conversation_id=conv.id,
        db=db_session
    )
    assert res["role"] == "assistant"
    assert "CV_Alex_Chen.pdf" in res["content"] or "AI systems researcher" in res["content"]
    assert "diagnostics" in res
    assert res["diagnostics"]["selectedTool"] in ["document_summary", "rag_knowledge_lookup"]
    assert res["diagnostics"]["status"] == "success"

def test_knowledge_query_endpoint_document_summary(client, auth_headers, test_user, db_session):
    doc = Document(
        user_id=test_user.id,
        filename="Machine_Learning_Syllabus.pdf",
        file_size=12000,
        mime_type="application/pdf",
        status="indexed"
    )
    db_session.add(doc)
    db_session.commit()

    chunk = DocumentChunk(
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=0,
        page_number=1,
        content="Course covers Backpropagation, CNNs, Transformers, and Reinforcement Learning.",
        embedding=[0.1] * 256
    )
    db_session.add(chunk)
    db_session.commit()

    res = client.post(
        "/api/knowledge/query",
        headers=auth_headers,
        json={"query": "Give me a complete overview of this document"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "document_summary"
    assert "Machine_Learning_Syllabus.pdf" in data["answer"]
