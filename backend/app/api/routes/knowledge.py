import os
import io
import csv
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
import pypdf

import httpx
from app.core.config import settings
from app.db.session import get_db
from app.db.models import User, Document, DocumentChunk, Timetable, TimetablePeriod, TimetableEntry, AcademicEvent
from app.middleware.auth_middleware import get_current_user
from app.rag.chunking import chunk_text, chunk_pages
from app.rag.embeddings import get_embedding
from app.rag.retrieval import retrieve_knowledge, format_grounded_rag_response, format_page_citation
from app.schemas import KnowledgeQueryRequest, DocumentConfirmRequest
from app.services.table_extractor import (
    extract_timetable_data,
    extract_academic_calendar_data,
    DAY_MAP,
    VALID_CATEGORIES
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base & RAG"])

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB limit

def extract_timetable_from_text(text: str, user_id: str) -> List[TimetableEntry]:
    """
    Attempts to extract structured class schedule records from timetable text.
    Looks for day names, time ranges, and course codes.
    """
    entries = []
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    lines = text.split("\n")
    
    time_regex = re.compile(r'(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))\s*[-–to]+\s*(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))')
    code_regex = re.compile(r'\b([A-Z]{2,4}[-\s]?\d{3,4})\b')
    room_regex = re.compile(r'\b(?:Hall|Room|Lab|Auditorium|Building|LH)\s*([A-Za-z0-9-]+)\b', re.IGNORECASE)
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        line_lower = line_clean.lower()
        
        found_day = None
        for d in days:
            if d in line_lower:
                found_day = d.capitalize()
                break
                
        time_match = time_regex.search(line_clean)
        if found_day and time_match:
            start_time, end_time = time_match.group(1), time_match.group(2)
            code_match = code_regex.search(line_clean)
            course_code = code_match.group(1) if code_match else "COURSE"
            room_match = room_regex.search(line_clean)
            room = room_match.group(0) if room_match else "TBD"
            
            # Clean course name from remaining text
            course_name = line_clean
            for token in [found_day, start_time, end_time, course_code, room, "-", "–"]:
                course_name = course_name.replace(token, "")
            course_name = re.sub(r'\s+', ' ', course_name).strip(" :,()")
            if not course_name:
                course_name = f"Class {course_code}"
                
            entries.append(TimetableEntry(
                user_id=user_id,
                course_name=course_name[:255],
                course_code=course_code[:50],
                day_of_week=found_day,
                start_time=start_time,
                end_time=end_time,
                room=room[:100],
                instructor=None
            ))
            
    return entries

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form("general"),
    document_type: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Validates file and routes according to document type:
    - College Timetable: High-fidelity table extraction into structured TimetableEntry records.
    - Academic Calendar: High-fidelity table extraction into structured AcademicEvent records.
    - Syllabus & Notes: Standard RAG ingestion, chunking, and embedding generation.
    """
    content_bytes = await file.read()
    file_size = len(content_bytes)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes)."
        )

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)} MB."
        )

    filename = file.filename or "uploaded_document"
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    mime_type = file.content_type or "application/octet-stream"

    # Resolve document type and category for RAG knowledge ingestion
    type_candidate = (document_type or category or "NOTES").upper().strip()
    if type_candidate in ("SYLLABUS", "APPROVED_SYLLABUS", "ACADEMIC"):
        resolved_type = "SYLLABUS"
        resolved_category = "syllabus"
    elif type_candidate in ("TEXTBOOK", "BOOK"):
        resolved_type = "TEXTBOOK"
        resolved_category = "textbook"
    else:
        resolved_type = "NOTES"
        resolved_category = "notes"

    # Save binary file locally for persistent document retrieval
    save_dir = os.path.join("uploads", "knowledge", user.id)
    os.makedirs(save_dir, exist_ok=True)
    local_file_path = os.path.join(save_dir, f"{filename}")
    try:
        with open(local_file_path, "wb") as f:
            f.write(content_bytes)
    except Exception:
        local_file_path = None

    # --- KNOWLEDGE DOCUMENTS RAG INGESTION PIPELINE (Syllabus, Notes, Textbooks) ---

    pages_data: List[Dict[str, Any]] = []
    full_text = ""

    # 1. PDF Parsing
    if ext == "pdf" or "pdf" in mime_type:
        try:
            pdf_stream = io.BytesIO(content_bytes)
            reader = pypdf.PdfReader(pdf_stream)
            
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="The uploaded PDF is password-protected and cannot be read."
                    )

            num_pages = len(reader.pages)
            if num_pages == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The uploaded PDF contains zero pages."
                )

            for idx, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                page_text_clean = page_text.strip()
                if page_text_clean:
                    pages_data.append({
                        "page_number": idx + 1,
                        "text": page_text_clean
                    })
                    full_text += f"\n\n[Page {idx + 1}]\n" + page_text_clean

            if not pages_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The PDF contains no extractable text. Scanned or image-only documents require OCR, which is not currently supported."
                )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse PDF document: {str(e)}"
            )

    # 2. CSV Parsing
    elif ext == "csv" or "csv" in mime_type:
        try:
            decoded_csv = content_bytes.decode('utf-8', errors='replace')
            csv_reader = csv.reader(io.StringIO(decoded_csv))
            rows = list(csv_reader)
            if not rows:
                raise HTTPException(status_code=400, detail="CSV file contains no data.")

            header = rows[0] if rows else []
            csv_lines = []
            for r_idx, row in enumerate(rows[1:], start=1):
                row_items = []
                for c_idx, val in enumerate(row):
                    col_name = header[c_idx] if c_idx < len(header) else f"Col{c_idx+1}"
                    row_items.append(f"{col_name}: {val.strip()}")
                csv_lines.append(f"Row {r_idx} -> " + ", ".join(row_items))

            full_text = f"CSV Dataset: {filename}\nHeaders: {', '.join(header)}\n\n" + "\n".join(csv_lines)
            pages_data.append({"page_number": 1, "text": full_text})
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse CSV file: {str(e)}")

    # 3. Plain Text, Markdown, JSON, etc.
    else:
        try:
            full_text = content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                full_text = content_bytes.decode('latin-1')
            except Exception:
                raise HTTPException(status_code=400, detail="Unable to decode file text as UTF-8 or Latin-1.")

        if not full_text.strip():
            raise HTTPException(status_code=400, detail="Uploaded file contains no readable text.")

        pages_data.append({"page_number": 1, "text": full_text.strip()})

    # Chunk content preserving page numbers
    chunks = chunk_pages(pages_data, chunk_size=600, overlap=100)
    if not chunks:
        raise HTTPException(status_code=400, detail="No readable content chunks could be generated from document.")

    # De-duplicate: Clean up existing document with the same filename for this user
    existing_doc = db.query(Document).filter(
        Document.user_id == user.id,
        Document.filename == filename
    ).first()

    if existing_doc:
        db.query(TimetableEntry).filter(TimetableEntry.document_id == existing_doc.id).delete()
        db.query(AcademicEvent).filter(AcademicEvent.document_id == existing_doc.id).delete()
        db.query(DocumentChunk).filter(DocumentChunk.document_id == existing_doc.id).delete()
        db.delete(existing_doc)
        db.commit()

    # Create new Document record in PROCESSING state
    doc = Document(
        user_id=user.id,
        filename=filename,
        file_size=file_size,
        mime_type=mime_type,
        category=resolved_category,
        document_type=resolved_type,
        page_count=len(pages_data),
        chunk_count=len(chunks),
        file_path=local_file_path,
        status="processing",
        processing_status="PROCESSING",
        is_active=True
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Generate embeddings and persist chunks with robust failure recovery
    try:
        for c in chunks:
            vec = await get_embedding(c["content"])
            chunk_record = DocumentChunk(
                document_id=doc.id,
                user_id=user.id,
                chunk_index=c["chunk_index"],
                content=c["content"],
                page_number=c.get("page_number", 1),
                embedding=vec
            )
            db.add(chunk_record)

        doc.status = "indexed"
        doc.processing_status = "INDEXED"
        doc.processed_at = datetime.now(timezone.utc)
        doc.processing_error = None
        db.commit()
        db.refresh(doc)
    except Exception as e:
        db.rollback()
        doc.status = "failed"
        doc.processing_status = "FAILED"
        doc.processing_error = f"Embedding generation failed: {str(e)}"
        doc.error_message = str(e)
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate embeddings and index document: {str(e)}"
        )

    return {
        "id": doc.id,
        "filename": doc.filename,
        "fileSize": doc.file_size,
        "mimeType": doc.mime_type,
        "chunkCount": doc.chunk_count,
        "category": doc.category,
        "documentType": doc.document_type,
        "status": "INDEXED",
        "processingStatus": "INDEXED",
        "uploadedAt": doc.created_at.isoformat()
    }

@router.get("/documents")
def list_documents(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    docs = db.query(Document).filter(Document.user_id == user.id).order_by(Document.created_at.desc()).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "fileSize": d.file_size,
            "mimeType": d.mime_type,
            "chunkCount": d.chunk_count,
            "category": d.category,
            "documentType": d.document_type or "NOTES",
            "status": d.status,
            "processingStatus": d.processing_status or "COMPLETED",
            "uploadedAt": d.created_at.isoformat(),
            "processedAt": d.processed_at.isoformat() if d.processed_at else None
        }
        for d in docs
    ]

@router.get("/documents/{document_id}/preview")
def get_document_preview(
    document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = db.query(Document).filter(Document.id == document_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "documentType": doc.document_type or "NOTES",
        "processingStatus": doc.processing_status or "COMPLETED",
        "extractedData": doc.extracted_data or {},
        "uploadedAt": doc.created_at.isoformat(),
        "processedAt": doc.processed_at.isoformat() if doc.processed_at else None
    }

@router.post("/documents/{document_id}/confirm")
def confirm_document_extraction(
    document_id: str,
    req: DocumentConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = db.query(Document).filter(Document.id == document_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc_type = req.document_type or doc.document_type or "TIMETABLE"

    if doc_type == "TIMETABLE":
        raw_entries = req.entries if req.entries is not None else (doc.extracted_data or {}).get("entries", [])
        # Transactional clean replacement for this document
        db.query(TimetableEntry).filter(TimetableEntry.document_id == doc.id).delete()
        inserted = 0
        for item in raw_entries:
            day_str = str(item.get("day_of_week") or item.get("day") or "Monday").upper().strip()
            norm_day = DAY_MAP.get(day_str.lower(), day_str.capitalize())
            subj_name = item.get("subject_name") or item.get("course_name") or item.get("course") or "Class"
            subj_code = item.get("subject_code") or item.get("course_code") or item.get("code") or "COURSE"
            start_t = item.get("start_time") or item.get("start") or "09:00 AM"
            end_t = item.get("end_time") or item.get("end") or "10:00 AM"
            room = item.get("room_number") or item.get("room") or "Room 101"
            faculty = item.get("faculty_name") or item.get("instructor")
            c_type = item.get("class_type") or "Theory"
            acad_year = item.get("academic_year")
            sem = item.get("semester")
            src_p = item.get("source_page") or 1
            src_r = item.get("source_row")
            conf = float(item.get("confidence") or 1.0)

            tt = TimetableEntry(
                user_id=user.id,
                document_id=doc.id,
                course_name=subj_name[:255],
                course_code=subj_code[:50],
                day_of_week=norm_day,
                start_time=start_t[:20],
                end_time=end_t[:20],
                room=room[:100] if room else None,
                instructor=faculty[:255] if faculty else None,
                class_type=c_type[:50] if c_type else "Theory",
                academic_year=acad_year[:50] if acad_year else None,
                semester=sem[:50] if sem else None,
                source_page=src_p,
                source_row=src_r,
                confidence=conf
            )
            db.add(tt)
            inserted += 1

        doc.processing_status = "COMPLETED"
        doc.status = "indexed"
        doc.chunk_count = inserted
        doc.processed_at = datetime.now(timezone.utc)
        db.commit()
        return {
            "success": True,
            "documentId": doc.id,
            "documentType": "TIMETABLE",
            "insertedCount": inserted
        }

    elif doc_type == "ACADEMIC_CALENDAR":
        raw_events = req.events if req.events is not None else (doc.extracted_data or {}).get("events", [])
        db.query(AcademicEvent).filter(AcademicEvent.document_id == doc.id).delete()
        inserted = 0
        for item in raw_events:
            ev_name = item.get("event_name") or item.get("name") or "Academic Event"
            cat = str(item.get("category") or "OTHER").upper().strip()
            if cat not in VALID_CATEGORIES:
                cat = "OTHER"
            start_d = item.get("start_date") or item.get("date") or datetime.now().strftime("%Y-%m-%d")
            end_d = item.get("end_date")
            desc = item.get("description")
            acad_year = item.get("academic_year")
            sem = item.get("semester")
            page = item.get("source_page")
            row = item.get("source_row")

            ev = AcademicEvent(
                user_id=user.id,
                document_id=doc.id,
                event_name=ev_name[:255],
                category=cat[:50],
                start_date=start_d[:10],
                end_date=end_d[:10] if end_d else None,
                description=desc,
                academic_year=acad_year[:50] if acad_year else None,
                semester=sem[:50] if sem else None,
                source_page=page,
                source_row=row
            )
            db.add(ev)
            inserted += 1

        doc.processing_status = "COMPLETED"
        doc.status = "indexed"
        doc.chunk_count = inserted
        doc.processed_at = datetime.now(timezone.utc)
        db.commit()
        return {
            "success": True,
            "documentId": doc.id,
            "documentType": "ACADEMIC_CALENDAR",
            "insertedCount": inserted
        }
    else:
        doc.processing_status = "COMPLETED"
        db.commit()
        return {"success": True, "documentId": doc.id, "insertedCount": 0}


@router.post("/documents/{document_id}/retry")
async def retry_document_extraction(
    document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retries extraction on an existing uploaded document using its stored binary file
    without requiring the user to upload the file again.
    """
    doc = db.query(Document).filter(Document.id == document_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    file_bytes = None
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            with open(doc.file_path, "rb") as f:
                file_bytes = f.read()
        except Exception as e:
            logger.error(f"[Knowledge] Failed reading file {doc.file_path} for retry: {e}")

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Document binary content is not available for retry on server. Please re-upload the file."
        )

    doc_type = (doc.document_type or "TIMETABLE").upper()
    if doc_type == "TIMETABLE":
        extraction_res = await extract_timetable_data(file_bytes, doc.filename, doc.mime_type or "application/pdf")
        doc.extracted_data = extraction_res.model_dump()
        if len(extraction_res.entries) > 0:
            doc.processing_status = "REVIEW_REQUIRED"
            doc.processing_error = None
            doc.chunk_count = len(extraction_res.entries)
        else:
            doc.processing_status = "FAILED"
            doc.processing_error = "No timetable entries could be extracted from this document."
            doc.chunk_count = 0
    elif doc_type == "ACADEMIC_CALENDAR":
        extraction_res = await extract_academic_calendar_data(file_bytes, doc.filename, doc.mime_type or "application/pdf")
        doc.extracted_data = extraction_res.model_dump()
        if len(extraction_res.events) > 0:
            doc.processing_status = "REVIEW_REQUIRED"
            doc.processing_error = None
            doc.chunk_count = len(extraction_res.events)
        else:
            doc.processing_status = "FAILED"
            doc.processing_error = "No academic calendar events could be extracted."
            doc.chunk_count = 0

    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "documentType": doc.document_type,
        "processingStatus": doc.processing_status,
        "processingError": doc.processing_error,
        "preview": doc.extracted_data or {}
    }

@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = db.query(Document).filter(Document.id == document_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Cascading safe cleanup for this specific document only
    db.query(TimetableEntry).filter(TimetableEntry.document_id == doc.id, TimetableEntry.user_id == user.id).delete()
    db.query(AcademicEvent).filter(AcademicEvent.document_id == doc.id, AcademicEvent.user_id == user.id).delete()
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id, DocumentChunk.user_id == user.id).delete()
    db.delete(doc)
    db.commit()
    return {"success": True, "deletedDocumentId": document_id}

@router.post("/query")
async def query_knowledge(
    req: KnowledgeQueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    retrieval_res = await retrieve_knowledge(req.query, user.id, db, top_k=6)
    
    # Check if document-level summary was triggered
    if retrieval_res.get("mode") == "document_summary" and retrieval_res.get("summary"):
        sources = retrieval_res.get("sources", [])
        formatted_summary = format_grounded_rag_response(retrieval_res["summary"], sources[:3], query=req.query)
        return {
            "answer": formatted_summary,
            "sources": sources,
            "timetableMatches": [],
            "mode": "document_summary"
        }

    sources = retrieval_res.get("sources", [])
    timetable_matches = retrieval_res.get("timetableMatches", [])
    relevance_eval = retrieval_res.get("relevanceEvaluation", "sufficient_evidence")

    if timetable_matches and not sources:
        tm = timetable_matches[0]
        answer = f"**Answer:**\nAccording to your structured timetable: **{tm['courseName']}** ({tm['courseCode']}) is on **{tm['dayOfWeek']}** from **{tm['startTime']}** to **{tm['endTime']}** in **{tm['room']}** with **{tm['instructor']}**."
        return {
            "answer": answer,
            "sources": sources,
            "timetableMatches": timetable_matches,
            "mode": "timetable"
        }

    if not sources or relevance_eval == "insufficient_evidence":
        return {
            "answer": "**Answer:**\nThe uploaded documents do not provide enough information to answer this question.",
            "sources": [],
            "timetableMatches": timetable_matches,
            "mode": "no_evidence"
        }

    # Synthesize answer using Gemini if configured
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Gemini API key is not configured. Answer generation requires a valid API key."
        )

    from app.services.gemini_client import call_gemini_api
    from app.prompts.rag import SPECIFIC_RAG_PROMPT

    evidence_blocks = "\n\n".join([
        f"[{s['title']} - {s.get('pageLabel') or format_page_citation(s.get('page'))}]\n{s.get('fullContent', s['snippet'])}"
        for s in sources[:4]
    ])
    user_prompt = (
        f"USER QUESTION: {req.query}\n\n"
        f"RETRIEVED DOCUMENT EVIDENCE:\n{evidence_blocks}\n\n"
        f"INSTRUCTIONS:\n"
        f"1. Answer the USER QUESTION directly in the first sentence.\n"
        f"2. Lead with facts that directly address the question.\n"
        f"3. For a question containing multiple parts, address every part accurately and completely.\n"
        f"4. Do NOT begin with incidental context or unrelated tables/sections unless specifically asked.\n"
        f"5. Base your answer strictly on the evidence above.\n"
        f"6. If evidence is insufficient, state: "
        f"'The uploaded documents do not provide enough information to answer this question.'\n"
        f"7. Do not invent facts, citations, or identifiers not present in the evidence.\n"
        f"8. Do not output reference tables or full sections unless explicitly requested."
    )

    gemini_res = await call_gemini_api(
        user_prompt, SPECIFIC_RAG_PROMPT,
        max_output_tokens=2048, temperature=0.1
    )

    if not gemini_res.success:
        err_status = gemini_res.status_code or 503
        if err_status not in (400, 401, 403, 429, 500, 502, 503, 504):
            err_status = 503
        raise HTTPException(
            status_code=err_status,
            detail=gemini_res.user_message
        )

    raw_answer = gemini_res.text

    formatted_answer = format_grounded_rag_response(raw_answer, sources, query=req.query)

    return {
        "answer": formatted_answer,
        "sources": sources,
        "timetableMatches": timetable_matches,
        "mode": "grounded_rag"
    }

@router.get("/timetables")
def get_user_timetables(
    day: Optional[str] = None,
    subject: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Returns timetable entries for the authenticated user (prioritizing manual TimetablePeriod).
    """
    pq = db.query(TimetablePeriod).filter(TimetablePeriod.user_id == user.id)
    if day:
        day_clean = DAY_MAP.get(day.lower(), day.capitalize())
        pq = pq.filter(TimetablePeriod.day_of_week == day_clean)
    if subject:
        kw = f"%{subject.strip()}%"
        pq = pq.filter(
            (TimetablePeriod.subject_name.ilike(kw)) |
            (TimetablePeriod.subject_code.ilike(kw))
        )
    periods = pq.order_by(TimetablePeriod.created_at.desc()).all()
    if periods:
        return [
            {
                "id": p.id,
                "timetableId": p.timetable_id,
                "courseName": p.subject_name,
                "courseCode": p.subject_code,
                "dayOfWeek": p.day_of_week,
                "startTime": p.start_time,
                "endTime": p.end_time,
                "room": p.room or "TBD",
                "instructor": p.faculty or "Faculty",
                "classType": p.class_type or "Lecture",
                "notes": p.notes
            }
            for p in periods
        ]

    # Fallback to TimetableEntry
    q = db.query(TimetableEntry).filter(TimetableEntry.user_id == user.id)
    if day:
        day_clean = DAY_MAP.get(day.lower(), day.capitalize())
        q = q.filter(TimetableEntry.day_of_week == day_clean)
    if subject:
        kw = f"%{subject.strip()}%"
        q = q.filter(
            (TimetableEntry.course_name.ilike(kw)) |
            (TimetableEntry.course_code.ilike(kw))
        )
    entries = q.order_by(TimetableEntry.created_at.desc()).all()
    return [
        {
            "id": e.id,
            "documentId": e.document_id,
            "courseName": e.course_name,
            "courseCode": e.course_code,
            "dayOfWeek": e.day_of_week,
            "startTime": e.start_time,
            "endTime": e.end_time,
            "room": e.room or "TBD",
            "instructor": e.instructor or "Faculty",
            "classType": e.class_type or "Theory",
            "academicYear": e.academic_year,
            "semester": e.semester
        }
        for e in entries
    ]

@router.get("/academic-events")
def get_user_academic_events(
    category: Optional[str] = None,
    query: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    month: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Deprecated: Structured academic calendar storage is removed. Timetables are managed manually.
    """
    return []
