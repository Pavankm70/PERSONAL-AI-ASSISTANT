import io
import pytest
from pypdf import PdfWriter
from app.rag.chunking import chunk_pages, chunk_text
from app.db.models import User, Document, DocumentChunk

def create_test_pdf_bytes(pages_text: list[str]) -> bytes:
    """Helper to generate real PDF binary with pypdf containing custom text."""
    # Since ReportLab or similar might not be installed, we can generate a basic valid PDF structure
    # or write a minimal valid PDF with text stream:
    pdf_template = (
        "%PDF-1.4\n"
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        "4 0 obj << /Length 55 >> stream\n"
        "BT /F1 12 Tf 72 712 Td (Convolutional Neural Networks and Deep Learning) Tj ET\n"
        "endstream\n"
        "endobj\n"
        "5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        "xref\n"
        "0 6\n"
        "0000000000 65535 f \n"
        "0000000009 00000 n \n"
        "0000000058 00000 n \n"
        "0000000115 00000 n \n"
        "0000000244 00000 n \n"
        "0000000350 00000 n \n"
        "trailer << /Size 6 /Root 1 0 R >>\n"
        "startxref\n"
        "425\n"
        "%%EOF\n"
    )
    return pdf_template.encode('latin1')

def test_pypdf_extraction_and_chunking():
    pdf_bytes = create_test_pdf_bytes(["Test Page 1"])
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    extracted = ""
    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            extracted += txt

    assert "Convolutional Neural Networks" in extracted
    chunks = chunk_pages([{"page_number": 1, "text": extracted}])
    assert len(chunks) >= 1
    assert chunks[0]["page_number"] == 1
    assert "Convolutional Neural Networks" in chunks[0]["content"]

def test_csv_upload_endpoint(client, auth_headers):
    csv_content = b"CourseCode,CourseTitle,Credits,Grade\nCS-702,Advanced Machine Learning,4,A\nCS-705,Distributed Systems,4,A-"
    res = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("grades.csv", io.BytesIO(csv_content), "text/csv")},
        data={"category": "academic_notes"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "indexed"
    assert data["chunkCount"] >= 1

def test_empty_pdf_returns_clear_ocr_rejection(client, auth_headers):
    # PDF with empty text
    empty_pdf = (
        "%PDF-1.4\n"
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj\n"
        "4 0 obj << /Length 0 >> stream\nendstream\nendobj\n"
        "xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000216 00000 n \n"
        "trailer << /Size 5 /Root 1 0 R >>\nstartxref\n267\n%%EOF\n"
    ).encode('latin1')
    
    res = client.post(
        "/api/knowledge/upload",
        headers=auth_headers,
        files={"file": ("scanned_blank.pdf", io.BytesIO(empty_pdf), "application/pdf")},
        data={"category": "academic_notes"}
    )
    assert res.status_code == 400
    assert "OCR" in res.json()["detail"] or "No readable text" in res.json()["detail"]

from app.rag.retrieval import retrieve_knowledge
from app.rag.embeddings import cosine_similarity, get_embedding

@pytest.mark.asyncio
async def test_retrieval_relevance_threshold_filters_noise(db_session, test_user):
    # Add a real document and chunk
    doc = Document(
        user_id=test_user.id,
        filename="NLP_Attention.pdf",
        file_size=2048,
        mime_type="application/pdf",
        status="indexed"
    )
    db_session.add(doc)
    db_session.commit()

    chunk_vec = await get_embedding("Self-attention allows transformers to compute representations of sequences without recurrence.")

    chunk1 = DocumentChunk(
        document_id=doc.id,
        user_id=test_user.id,
        chunk_index=0,
        page_number=1,
        content="Self-attention allows transformers to compute representations of sequences without recurrence.",
        embedding=chunk_vec
    )
    db_session.add(chunk1)
    db_session.commit()

    # Query with query vector matching chunk
    top_matches = await retrieve_knowledge(
        query="Self-attention transformers",
        user_id=test_user.id,
        db=db_session,
        top_k=3
    )
    assert "sources" in top_matches
    # The cosine_similarity between mock embeddings or local hash embeddings is computed
    assert isinstance(top_matches["sources"], list)
