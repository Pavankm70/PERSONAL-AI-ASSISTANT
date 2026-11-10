"""
AURELIA AI — Test Suite: Document Discovery and RAG Retrieval Reliability
Tests A through J verifying:
A: First-question document discovery without naming filename
B: Filename-independent retrieval based on content & concept matching
C: Multi-document scoping and prioritization
D: Follow-up conversational resolution using prior citations
E: Document replacement and stale chunk cleanup
F: Document deletion excluding chunks from retrieval
G: Strict tenant and user isolation
H: Exclusion of failed or unindexed documents
I: Empty and irrelevant question handling (no hallucination)
J: Heuristic & intent routing for unit/topic queries
"""

import pytest
import uuid
from datetime import datetime, timezone
from app.db.models import User, Document, DocumentChunk, Message, Conversation
from app.rag.retrieval import retrieve_knowledge, identify_target_documents, tokenize
from app.rag.embeddings import compute_local_embedding
from app.agent.graph import heuristic_classify_intent, AureliaAgent

@pytest.fixture
def second_user(db_session):
    u = User(
        id="usr_test_user_b",
        email="user_b@university.edu",
        full_name="User B",
        timezone="UTC",
        onboarding_complete=True
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u

@pytest.mark.asyncio
async def test_a_first_question_document_discovery(client, auth_headers, db_session, test_user):
    """
    Test A: The core bug reproduction test.
    User uploads 'DBMS_Syllabus.txt'.
    Without mentioning the filename or first asking 'What does DBMS_Syllabus contain?',
    the user directly asks: 'What topics are covered in Unit 3?'.
    The system must automatically discover the syllabus, prioritize the Unit 3 chunk,
    and return sufficient evidence.
    """
    syllabus_text = """
UNIT 1: INTRODUCTION TO DATABASE SYSTEMS
Database system concepts, architecture, data models, ER diagrams, relational model basics.

UNIT 2: RELATIONAL ALGEBRA AND SQL
Relational algebra operations, tuple calculus, DDL, DML, complex SQL queries, views, and integrity constraints.

UNIT 3: NORMALIZATION AND DATABASE DESIGN
Functional dependencies, closure of attribute sets, canonical cover, normal forms: 1NF, 2NF, 3NF, BCNF. Multi-valued dependencies and 4NF. Lossless-join decomposition and dependency preservation.

UNIT 4: TRANSACTION PROCESSING AND CONCURRENCY CONTROL
Transaction states, ACID properties, serializability, two-phase locking protocol, strict 2PL, timestamp ordering, deadlock detection and recovery.
"""
    # Upload through the standard API endpoint
    response = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("DBMS_Syllabus.txt", syllabus_text.encode("utf-8"), "text/plain")},
        data={"document_type": "SYLLABUS", "category": "Syllabus"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "INDEXED"
    assert data["chunkCount"] >= 1

    # Now execute the first question directly without naming the filename
    user_query = "What topics are covered in Unit 3?"
    result = await retrieve_knowledge(
        query=user_query,
        user_id=test_user.id,
        db=db_session,
        top_k=4
    )

    assert result["relevanceEvaluation"] in ("evidence_found", "sufficient_evidence"), "Expected evidence for Unit 3"
    assert len(result["sources"]) > 0, "Expected at least one matching source chunk"
    top_chunk = result["sources"][0]
    assert top_chunk["title"] == "DBMS_Syllabus.txt"
    # Verify the top chunk contains Unit 3 content (Normalization, 3NF, BCNF, etc.)
    top_text = top_chunk["snippet"].upper() + " " + top_chunk.get("fullContent", "").upper()
    assert "NORMALIZATION" in top_text or "UNIT 3" in top_text or "3NF" in top_text

@pytest.mark.asyncio
async def test_b_filename_independent_retrieval(client, auth_headers, db_session, test_user):
    """
    Test B: Filename-independent retrieval.
    User asks: 'Explain inheritance as described in my syllabus'.
    System must discover 'Java_Course_Spec.txt' through semantic/lexical matching
    even though the word 'Java_Course_Spec.txt' is not in the prompt.
    """
    content = """
CHAPTER 1: OBJECT ORIENTED BASICS
Classes, objects, constructors, encapsulation, information hiding.

CHAPTER 2: INHERITANCE AND POLYMORPHISM
Subclassing, super keyword, method overriding, dynamic method dispatch. Single, multilevel, and hierarchical inheritance. Abstract classes, interfaces, and polymorphism.

CHAPTER 3: EXCEPTION HANDLING AND PACKAGES
Try, catch, throw, throws, finally blocks. Built-in exceptions and custom exceptions. Creating and importing user packages.
"""
    res = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("Java_Course_Spec.txt", content.encode("utf-8"), "text/plain")},
        data={"document_type": "SYLLABUS", "category": "Syllabus"}
    )
    assert res.status_code == 200

    query = "Explain inheritance as described in my syllabus"
    result = await retrieve_knowledge(query=query, user_id=test_user.id, db=db_session)

    assert result["relevanceEvaluation"] in ("evidence_found", "sufficient_evidence")
    sources = result["sources"]
    assert len(sources) > 0
    assert any("INHERITANCE" in s["snippet"].upper() for s in sources)
    assert sources[0]["title"] == "Java_Course_Spec.txt"

@pytest.mark.asyncio
async def test_c_multiple_documents_prioritization(client, auth_headers, db_session, test_user):
    """
    Test C: Multi-document discrimination.
    When user has multiple uploaded documents (DBMS, Java, Operating Systems),
    targeted questions must prioritize the relevant document over unrelated ones.
    """
    docs_payload = [
        ("DBMS_Curriculum.txt", "Unit 1: ER modeling. Unit 2: SQL joins and subqueries. Unit 3: Normalization BCNF 3NF. Unit 4: ACID transactions."),
        ("Java_Curriculum.txt", "Unit 1: Java syntax. Unit 2: Inheritance and interfaces. Unit 3: Multithreading and synchronization. Unit 4: Generics."),
        ("OS_Curriculum.txt", "Unit 1: OS structures. Unit 2: Process scheduling CPU. Unit 3: Virtual memory and page replacement LRU. Unit 4: File systems.")
    ]
    for fn, text in docs_payload:
        res = client.post(
            "/api/knowledge/upload",
            headers=auth_headers,
            files={"file": (fn, text.encode("utf-8"), "text/plain")},
            data={"document_type": "SYLLABUS", "category": "Syllabus"}
        )
        assert res.status_code == 200

    # Query 1: DBMS specific
    r1 = await retrieve_knowledge("What is BCNF and normalization?", test_user.id, db_session)
    assert r1["relevanceEvaluation"] in ("evidence_found", "sufficient_evidence")
    assert r1["sources"][0]["title"] == "DBMS_Curriculum.txt"

    # Query 2: Java specific
    r2 = await retrieve_knowledge("Explain multithreading and synchronization", test_user.id, db_session)
    assert r2["relevanceEvaluation"] in ("evidence_found", "sufficient_evidence")
    assert r2["sources"][0]["title"] == "Java_Curriculum.txt"

    # Query 3: OS specific
    r3 = await retrieve_knowledge("What is virtual memory and page replacement?", test_user.id, db_session)
    assert r3["relevanceEvaluation"] in ("evidence_found", "sufficient_evidence")
    assert r3["sources"][0]["title"] == "OS_Curriculum.txt"

@pytest.mark.asyncio
async def test_d_follow_up_conversational_resolution(client, auth_headers, db_session, test_user):
    """
    Test D: Follow-up conversational resolution.
    After an initial question that retrieves a document, a short follow-up query like
    'Give an example' or 'Explain 3NF' preserves the document focus via explicit_doc_id.
    """
    syllabus_text = """
UNIT 3: NORMALIZATION AND DATABASE DESIGN
Functional dependencies, normal forms: 1NF, 2NF, 3NF, BCNF.
Example of 3NF: A relation R(A, B, C) where A -> B and B -> C violates 3NF because of transitive dependency.
To fix this, decompose R into R1(A, B) and R2(B, C).
"""
    res = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("DBMS_Notes.txt", syllabus_text.encode("utf-8"), "text/plain")},
        data={"document_type": "NOTES", "category": "Notes"}
    )
    doc_id = res.json()["id"]

    # Initial query
    r1 = await retrieve_knowledge("Explain normalization in Unit 3", test_user.id, db_session)
    assert r1["relevanceEvaluation"] in ("evidence_found", "sufficient_evidence")

    # Follow-up query with explicit_doc_id passed
    r2 = await retrieve_knowledge("Give an example", test_user.id, db_session, explicit_doc_id=doc_id)
    assert r2["relevanceEvaluation"] in ("evidence_found", "sufficient_evidence")
    assert r2["sources"][0]["documentId"] == doc_id
    assert "3NF" in r2["sources"][0]["snippet"] or "EXAMPLE" in r2["sources"][0]["snippet"].upper()

@pytest.mark.asyncio
async def test_e_document_replacement_and_deduplication(client, auth_headers, db_session, test_user):
    """
    Test E: Document replacement.
    Re-uploading a document with the same filename must safely replace existing chunks
    without leaving stale chunks or duplicate document entries.
    """
    v1_text = "Version 1: Old preliminary network syllabus covering basic OSI model only."
    res1 = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("Network_Syllabus.txt", v1_text.encode("utf-8"), "text/plain")},
        data={"document_type": "SYLLABUS", "category": "Syllabus"}
    )
    assert res1.status_code == 200

    docs = db_session.query(Document).filter(
        Document.user_id == test_user.id,
        Document.filename == "Network_Syllabus.txt"
    ).all()
    assert len(docs) == 1

    # Upload version 2
    v2_text = "Version 2: Modern network syllabus covering TCP/IP, Congestion Control BBR, and HTTP/3 QUIC protocol."
    res2 = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("Network_Syllabus.txt", v2_text.encode("utf-8"), "text/plain")},
        data={"document_type": "SYLLABUS", "category": "Syllabus"}
    )
    assert res2.status_code == 200

    docs_after = db_session.query(Document).filter(
        Document.user_id == test_user.id,
        Document.filename == "Network_Syllabus.txt"
    ).all()
    assert len(docs_after) == 1, "Only one active document record should exist after replacement"

    # Verify retrieval returns new version content
    r = await retrieve_knowledge("Explain HTTP/3 QUIC protocol", test_user.id, db_session)
    assert r["relevanceEvaluation"] in ("evidence_found", "sufficient_evidence")
    assert "QUIC" in r["sources"][0]["snippet"]

@pytest.mark.asyncio
async def test_f_document_deletion_excludes_from_retrieval(client, auth_headers, db_session, test_user):
    """
    Test F: Document deletion.
    Deleting a document via DELETE /api/knowledge/documents/{id} must delete its chunks
    and make its content unretrievable.
    """
    algo_text = "CHAPTER 4: GREEDY ALGORITHMS AND DIJKSTRA. Shortest path algorithm with priority queues."
    res = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("Algorithms_Guide.txt", algo_text.encode("utf-8"), "text/plain")},
        data={"document_type": "NOTES", "category": "Notes"}
    )
    doc_id = res.json()["id"]

    # Verify it is retrievable
    r_before = await retrieve_knowledge("Explain Dijkstra algorithm", test_user.id, db_session)
    assert r_before["relevanceEvaluation"] in ("evidence_found", "sufficient_evidence")

    # Delete the document
    del_res = client.delete(f"/api/knowledge/documents/{doc_id}", headers=auth_headers)
    assert del_res.status_code == 200

    # Verify chunks are gone from retrieval
    r_after = await retrieve_knowledge("Explain Dijkstra algorithm", test_user.id, db_session)
    assert r_after["relevanceEvaluation"] in ("insufficient_evidence", "no_documents")
    assert len(r_after["sources"]) == 0

@pytest.mark.asyncio
async def test_g_user_isolation_enforcement(client, auth_headers, db_session, test_user, second_user):
    """
    Test G: Tenant and user isolation.
    User A's documents must never be retrievable by User B.
    """
    secret_text = "CONFIDENTIAL PROJECT: Project Falcon secret architecture and encryption keys."
    res = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("Falcon_Secret.txt", secret_text.encode("utf-8"), "text/plain")},
        data={"document_type": "NOTES", "category": "Notes"}
    )
    assert res.status_code == 200

    # User B queries for Falcon
    r_b = await retrieve_knowledge("Project Falcon secret architecture", second_user.id, db_session)
    assert r_b["relevanceEvaluation"] == "insufficient_evidence" or r_b["relevanceEvaluation"] == "no_documents"
    assert len(r_b["sources"]) == 0

@pytest.mark.asyncio
async def test_h_failed_indexing_exclusion(db_session, test_user):
    """
    Test H: Documents with status FAILED or PROCESSING must be excluded from retrieval.
    """
    doc_failed = Document(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        filename="Corrupt_File.pdf",
        file_size=1024,
        mime_type="application/pdf",
        status="failed",
        processing_status="FAILED",
        category="Notes",
        document_type="NOTES"
    )
    db_session.add(doc_failed)
    db_session.commit()

    # identify_target_documents must ignore failed document
    targets = identify_target_documents(test_user.id, db_session, query="Corrupt_File.pdf")
    assert doc_failed.id not in [d.id for d in targets]

@pytest.mark.asyncio
async def test_i_empty_and_irrelevant_questions(client, auth_headers, db_session, test_user):
    """
    Test I: Irrelevant and empty queries must be rejected safely with insufficient_evidence
    without hallucinations.
    """
    text = "BIOLOGY 101: Photosynthesis, cellular respiration, mitosis and meiosis cell division."
    res_up = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("Biology.txt", text.encode("utf-8"), "text/plain")},
        data={"document_type": "NOTES", "category": "Notes"}
    )
    assert res_up.status_code == 200

    # Completely unrelated query
    r_unrelated = await retrieve_knowledge("What is the recipe for baking chocolate brownies?", test_user.id, db_session)
    assert r_unrelated["relevanceEvaluation"] == "insufficient_evidence"

    # Whitespace query
    r_empty = await retrieve_knowledge("   ", test_user.id, db_session)
    assert r_empty["relevanceEvaluation"] == "insufficient_evidence"

def test_j_intent_routing_and_tokenization():
    """
    Test J: Verify intent routing and tokenization preserving units, single digits, and ordinal numbers.
    """
    # 1. Tokenizer preserves single digits & Roman numerals
    tokens = tokenize("Unit 3 topics covered in Chapter 4 section II")
    assert "3" in tokens
    assert "unit_3" in tokens
    assert "unit3" in tokens
    assert "chapter_4" in tokens
    assert "chapter4" in tokens

    # 2. Heuristic classifier routes unit/topic queries to rag_knowledge_lookup
    queries = [
        "What topics are covered in Unit 3?",
        "Explain the topics in Unit 1",
        "What is covered in Unit 2?",
        "Explain inheritance as described in my syllabus",
        "What are the chapters in my notes?"
    ]
    for q in queries:
        classified = heuristic_classify_intent(q)
        assert classified["tool"] == "rag_knowledge_lookup", f"Failed for query: {q}"
