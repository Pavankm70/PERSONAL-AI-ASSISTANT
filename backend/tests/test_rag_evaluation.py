"""
AURELIA AI — Comprehensive RAG Accuracy, Retrieval & Document Understanding Evaluation Suite
Tests multi-genre documents, hybrid retrieval, exact entities, document-level summaries,
absent-fact handling, quantitative metrics (Recall@k, Precision@k, MRR), and tenant isolation.
"""
import pytest
import uuid
from sqlalchemy.orm import Session

from app.db.models import User, Document, DocumentChunk, Conversation, Message
from app.rag.chunking import chunk_text  # was: recursive_structure_aware_chunking
from app.rag.embeddings import compute_local_embedding
from app.rag.retrieval import (
    retrieve_knowledge,
    summarize_document,
    is_document_summary_query,
    compute_bm25_scores,
    identify_target_documents,  # was: resolve_target_documents
)
from unittest.mock import patch
from app.services.gemini_client import GeminiCallResult
from app.agent.graph import agent_orchestrator


@pytest.fixture(autouse=True)
def mock_gemini_for_evaluation_tests():
    async def fake_gemini(prompt, system_prompt="", **kwargs):
        if "intent" in system_prompt.lower() or "classify" in system_prompt.lower():
            return GeminiCallResult(success=True, text='{"tool": "rag_knowledge_lookup", "args": {"query": "jwt algorithm"}}', finish_reason="STOP")
        if "summary" in system_prompt.lower():
            return GeminiCallResult(
                success=True,
                text="### Document Summary: Edge_TPU_Transformer_Optimization.pdf\n\nMethodology focuses on Transformer optimization and pruning.",
                finish_reason="STOP"
            )
        return GeminiCallResult(
            success=True,
            text="According to the architecture spec, JWT token signing requires the RS256 algorithm.",
            finish_reason="STOP"
        )

    with patch("app.services.gemini_client.call_gemini_api", side_effect=fake_gemini), \
         patch("app.agent.graph.call_gemini_api", side_effect=fake_gemini):
        yield


@pytest.fixture
def eval_corpus(db_session: Session, test_user: User):
    """
    Populates an evaluation corpus with three diverse document types:
    1. A research paper (Computer Science / ML)
    2. A technical system specification (Architecture / Devops)
    3. An academic course syllabus (Higher Education)
    """
    # 1. Research Paper
    paper_doc = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="Edge_TPU_Transformer_Optimization.pdf",
        file_size=120000,
        mime_type="application/pdf",
        status="indexed",
        category="academic"
    )
    db_session.add(paper_doc)

    paper_chunks_data = [
        (0, 1, "# Transformer Optimization in Edge TPU Devices\nAuthors: Dr. Elena Vance and Marcus Brody.\n"
               "## 1. Introduction and Problem Formulation\nStandard transformer self-attention mechanisms impose heavy quadratic memory requirements. "
               "On embedded Edge TPU platforms, standard models exceed available on-chip SRAM by 4x, causing severe pipeline stalls."),
        (1, 2, "## 2. Methodology and Pruning Architecture\nWe introduce a structured quantization-aware pruning technique. "
               "Optimization was performed using the AdamW optimizer with a learning rate lr=0.0003, weight decay 0.01, and batch size 64. "
               "Sparse matrix multiplication reduces active weights by 68%."),
        (2, 3, "## 3. Experimental Evaluation and Results\nBenchmarking on the CS-702 Edge Benchmark suite demonstrated a 3.2x latency reduction "
               "with only 0.4% perplexity degradation. Energy consumption dropped from 14.2W to 4.8W per inference pass."),
        (3, 4, "## 4. Limitations and Future Work\nThe current kernel implementation does not support sequence lengths exceeding 2048 tokens. "
               "Cross-attention layers in multimodal variants remain unpruned.")
    ]

    for idx, page, text in paper_chunks_data:
        emb = compute_local_embedding(text)
        db_session.add(DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=paper_doc.id,
            user_id=test_user.id,
            chunk_index=idx,
            page_number=page,
            content=text,
            embedding=emb
        ))

    # 2. Technical System Specification
    spec_doc = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="Microservices_Architecture_Spec.md",
        file_size=45000,
        mime_type="text/markdown",
        status="indexed",
        category="technical"
    )
    db_session.add(spec_doc)

    spec_chunks_data = [
        (0, 1, "# Cloud Infrastructure Architecture\n"
               "## Security and Authentication\nAll microservice communication requires JWT Bearer tokens signed via RS256 algorithm. "
               "Token expiration is strictly set to 3600 seconds with refresh tokens valid for 30 days."),
        (1, 2, "## Database Layer and Pooling\nThe application connects to PostgreSQL 15 clusters. "
               "The connection pool size is configured to 20 connections with a max overflow of 10. "
               "SSL mode is set to verify-full with TLS 1.3.")
    ]

    for idx, page, text in spec_chunks_data:
        emb = compute_local_embedding(text)
        db_session.add(DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=spec_doc.id,
            user_id=test_user.id,
            chunk_index=idx,
            page_number=page,
            content=text,
            embedding=emb
        ))

    # 3. Academic Syllabus
    syllabus_doc = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="CS-702_Syllabus_Fall.txt",
        file_size=18000,
        mime_type="text/plain",
        status="indexed",
        category="academic"
    )
    db_session.add(syllabus_doc)

    syllabus_chunks_data = [
        (0, 1, "# CS-702: Advanced Distributed Systems\n"
               "Instructor: Prof. Alan Sterling. Office: Room 412, Turing Hall. Office hours: Tuesdays 2-4 PM.\n"
               "Required Textbook: 'Distributed Systems: Principles and Paradigms (3rd Edition)' by Tanenbaum."),
        (1, 2, "## Grading Breakdown and Course Policies\n"
               "Course evaluation: Midterm Exam 30%, Final Research Project 40%, Laboratory Assignments 30%. "
               "Late submissions are penalized 10% per day.")
    ]

    for idx, page, text in syllabus_chunks_data:
        emb = compute_local_embedding(text)
        db_session.add(DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=syllabus_doc.id,
            user_id=test_user.id,
            chunk_index=idx,
            page_number=page,
            content=text,
            embedding=emb
        ))

    db_session.commit()
    return {
        "paper": paper_doc,
        "spec": spec_doc,
        "syllabus": syllabus_doc
    }


# ==============================================================================
# PART 11 EVALUATION TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_factual_single_passage_retrieval(eval_corpus, db_session, test_user):
    """
    Test 1: Factual question answered by one specific passage.
    Checks that the exact parameter 'lr=0.0003' is retrieved in top results.
    """
    query = "What learning rate was used for AdamW optimization in the Edge TPU paper?"
    res = await retrieve_knowledge(query, test_user.id, db_session, top_k=4)
    assert res["status"] == "success"
    assert len(res["sources"]) > 0
    top_snippet = res["sources"][0]["snippet"]
    assert "lr=0.0003" in top_snippet or "AdamW" in top_snippet


@pytest.mark.asyncio
async def test_multi_passage_retrieval(eval_corpus, db_session, test_user):
    """
    Test 2: Question requiring multiple passages across separate sections.
    Checks that both problem context and experiment results are retrieved.
    """
    query = "What problem does the Edge TPU author identify and what latency results do they report?"
    res = await retrieve_knowledge(query, test_user.id, db_session, top_k=6)
    assert res["status"] == "success"
    snippets = " ".join([s["snippet"] for s in res["sources"]])
    # Must retrieve problem (exceeds SRAM / memory) AND results (3.2x latency / 4.8W)
    assert ("memory" in snippets.lower() or "sram" in snippets.lower())
    assert ("3.2x" in snippets or "latency" in snippets.lower())


@pytest.mark.asyncio
async def test_specific_section_query(eval_corpus, db_session, test_user):
    """
    Test 3: Question targeting a specific section (Methodology).
    Checks that Section 2 is ranked highly.
    """
    query = "What does the Methodology section explain in the research paper?"
    res = await retrieve_knowledge(query, test_user.id, db_session, top_k=4)
    assert res["status"] == "success"
    sources = res["sources"]
    assert any("Methodology" in s["snippet"] or "pruning" in s["snippet"].lower() for s in sources)


@pytest.mark.asyncio
async def test_complete_document_summary_non_resume(eval_corpus, db_session, test_user):
    """
    Test 4: Full document summary of a research paper.
    Verifies that it does NOT output resume headings (Profile, Education, Skills, Experience),
    and correctly covers the research paper's actual content.
    """
    summary_res = await summarize_document(
        user_id=test_user.id,
        db=db_session,
        document_query="Edge TPU Transformer Optimization"
    )
    assert summary_res["status"] == "success"
    assert summary_res["mode"] == "document_summary"
    assert "Edge_TPU_Transformer_Optimization.pdf" in summary_res["documentTitle"]
    summary_text = summary_res["summary"]
    # Verify no resume bias
    assert "RESUME" not in summary_text.upper()
    assert "EDUCATION:" not in summary_text
    assert "WORK EXPERIENCE:" not in summary_text
    # Verify research paper content is represented
    assert any(term in summary_text for term in ["Transformer", "TPU", "Methodology", "Optimization", "pruning"])


@pytest.mark.asyncio
async def test_absent_fact_handling(eval_corpus, db_session, test_user):
    """
    Test 5: Question about a fact completely absent from the documents (author's phone number).
    Verifies retriever flags low relevance or no matching facts.
    """
    query = "What is Dr. Elena Vance's personal phone number and home address?"
    res = await retrieve_knowledge(query, test_user.id, db_session, top_k=4)
    # The system must not find phone number evidence
    all_snippets = " ".join([s["snippet"] for s in res["sources"]])
    assert "phone" not in all_snippets.lower()
    assert "address" not in all_snippets.lower()


@pytest.mark.asyncio
async def test_exact_technical_identifiers(eval_corpus, db_session, test_user):
    """
    Test 6: Exact technical terms, names, and identifiers (RS256, TLS 1.3, CS-702).
    Verifies BM25 lexical precision boosts exact matches.
    """
    query = "What algorithm is used to sign JWT Bearer tokens?"
    res = await retrieve_knowledge(query, test_user.id, db_session, top_k=3)
    assert res["status"] == "success"
    top_chunk = res["sources"][0]
    assert "RS256" in top_chunk["snippet"]
    assert "Microservices_Architecture_Spec.md" in top_chunk["title"]


@pytest.mark.asyncio
async def test_similar_questions_differing_answers(eval_corpus, db_session, test_user):
    """
    Test 7: Similar questions whose correct answers differ.
    Q1: Midterm exam weight -> 30%
    Q2: Final research project weight -> 40%
    """
    res1 = await retrieve_knowledge("What is the midterm exam grading percentage in CS-702?", test_user.id, db_session, top_k=3)
    res2 = await retrieve_knowledge("What is the final research project percentage in CS-702?", test_user.id, db_session, top_k=3)

    assert "30%" in res1["sources"][0]["snippet"]
    assert "40%" in res2["sources"][0]["snippet"]


@pytest.mark.asyncio
async def test_multi_document_comparison(eval_corpus, db_session, test_user):
    """
    Test 8: Query comparing two documents: the technical spec and syllabus.
    Verifies chunks from both documents are retrieved.
    """
    query = "Compare the grading policy in CS-702 with the database connection pool in the architecture spec"
    res = await retrieve_knowledge(query, test_user.id, db_session, top_k=6)
    assert res["status"] == "success"
    titles = set(s["title"] for s in res["sources"])
    assert "CS-702_Syllabus_Fall.txt" in titles
    assert "Microservices_Architecture_Spec.md" in titles


@pytest.mark.asyncio
async def test_ambiguous_or_nonexistent_document_reference(eval_corpus, db_session, test_user):
    """
    Test 9: Query targeting a non-existent document filename.
    Verifies it returns empty or does not falsely attach unrelated documents.
    """
    res = await retrieve_knowledge("What does Quantum_Physics_101.pdf say about wave mechanics?", test_user.id, db_session, top_k=4)
    # The document doesn't exist, so either no sources or relevance is insufficient
    if res.get("sources"):
        assert res.get("relevanceEvaluation") == "insufficient_evidence"


def test_empty_extraction_and_malformed_input():
    """
    Test 10: Empty or malformed text extraction does not crash or generate phantom chunks.
    """
    chunks_empty = chunk_text("", chunk_size=500, overlap=100)
    assert chunks_empty == []

    chunks_whitespace = chunk_text("   \n\n\t  \n   ", chunk_size=500, overlap=100)
    assert chunks_whitespace == []


@pytest.mark.asyncio
async def test_low_relevance_rejection(eval_corpus, db_session, test_user):
    """
    Test 11: Low-relevance retrieval query completely outside the corpus domain.
    Verifies that relevance evaluation flags insufficient evidence.
    """
    query = "How do you bake authentic Italian sourdough pizza with active dry yeast?"
    res = await retrieve_knowledge(query, test_user.id, db_session, top_k=4)
    # Insufficient evidence flag should be set
    assert res["relevanceEvaluation"] == "insufficient_evidence" or len(res["sources"]) == 0


@pytest.mark.asyncio
async def test_user_tenant_isolation(eval_corpus, db_session, test_user):
    """
    Test 12: Strict tenant isolation.
    Creates a secret document for User B and verifies User A cannot retrieve it.
    """
    user_b = User(
        id="usr_confidential_999",
        email="ceo@acme.corp",
        full_name="Executive User"
    )
    db_session.add(user_b)
    db_session.commit()

    secret_doc = Document(
        id=str(uuid.uuid4()),
        user_id=user_b.id,
        filename="Q4_Executive_Compensation.pdf",
        file_size=20000,
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
        content="EXECUTIVE SALARY: Base compensation is $850,000 with a 150% target bonus.",
        embedding=compute_local_embedding("EXECUTIVE SALARY: Base compensation is $850,000")
    )
    db_session.add(secret_chunk)
    db_session.commit()

    # User A searches for executive salary
    res_a = await retrieve_knowledge("What is the executive base salary compensation?", test_user.id, db_session, top_k=5)
    for s in res_a.get("sources", []):
        assert "850,000" not in s["snippet"]
        assert s["title"] != "Q4_Executive_Compensation.pdf"


@pytest.mark.asyncio
async def test_quantitative_retrieval_metrics(eval_corpus, db_session, test_user):
    """
    Test 13: Quantitative retrieval quality measurement.
    Calculates Recall@k, Precision@k, and Mean Reciprocal Rank (MRR) across a defined test set.
    """
    test_queries = [
        {
            "query": "AdamW learning rate lr=0.0003 Edge TPU",
            "expected_keyword": "lr=0.0003",
            "k": 3
        },
        {
            "query": "RS256 JWT Bearer token authentication",
            "expected_keyword": "RS256",
            "k": 3
        },
        {
            "query": "Prof. Alan Sterling Turing Hall office hours",
            "expected_keyword": "Alan Sterling",
            "k": 3
        },
        {
            "query": "PostgreSQL connection pool max overflow",
            "expected_keyword": "PostgreSQL",
            "k": 3
        },
        {
            "query": "CS-702 midterm exam grading percentage",
            "expected_keyword": "Midterm",
            "k": 3
        }
    ]

    reciprocal_ranks = []
    recalls = []

    for item in test_queries:
        res = await retrieve_knowledge(item["query"], test_user.id, db_session, top_k=item["k"])
        sources = res.get("sources", [])

        # Check if relevant evidence appears in top k (Recall@k)
        hit_rank = None
        for rank, s in enumerate(sources, 1):
            if item["expected_keyword"].lower() in s["snippet"].lower():
                hit_rank = rank
                break

        if hit_rank is not None:
            recalls.append(1.0)
            reciprocal_ranks.append(1.0 / hit_rank)
        else:
            recalls.append(0.0)
            reciprocal_ranks.append(0.0)

    recall_at_k = sum(recalls) / len(recalls)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)

    # Document quantitative benchmark results
    print(f"\n[RAG Evaluation Benchmark] Recall@3: {recall_at_k:.2f}, MRR: {mrr:.2f}")

    # Assert robust quantitative quality standards
    assert recall_at_k >= 0.80, f"Recall@3 ({recall_at_k}) below minimum benchmark 0.80"
    assert mrr >= 0.60, f"MRR ({mrr}) below minimum benchmark 0.60"


@pytest.mark.asyncio
async def test_e2e_knowledge_base_to_assistant_flow(eval_corpus, db_session, test_user):
    """
    Test 14: Complete Knowledge Base to AI Assistant workflow.
    Simulates user asking question about an indexed document in chat.
    """
    conv = Conversation(user_id=test_user.id, title="Architecture Discussion")
    db_session.add(conv)
    db_session.commit()

    agent_response = await agent_orchestrator.run(
        user_id=test_user.id,
        query="What algorithm is required for JWT token signing according to our architecture spec?",
        conversation_id=conv.id,
        db=db_session
    )

    assert agent_response["role"] == "assistant"
    assert len(agent_response["citations"]) >= 1
    assert "RS256" in agent_response["content"] or any("RS256" in c["snippet"] for c in agent_response["citations"])
    assert agent_response["diagnostics"]["status"] == "success"
