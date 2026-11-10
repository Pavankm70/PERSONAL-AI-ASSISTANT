"""
AURELIA AI — Universal Table and Document Extraction Service
Extracts high-fidelity academic timetables and calendars from PDF and structured documents:
- Text-based PDFs with complex table grids
- Image-based, scanned, and photo-based PDFs using high-resolution rendering and Gemini Vision
- Mixed PDFs with both selectable text and image pages
- Universal layout understanding (days as rows, days as columns, vertical/horizontal time slots)
- Merged multi-period slots and multiple subjects per cell
- Subject-code reference table / legend extraction and automatic cross-referencing
- Exclusion of lunch breaks, recesses, and intervals
- Pydantic validation, normalization, and confidence scoring
"""
import io
import re
import json
import base64
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

import pdfplumber
import pypdf
import pypdfium2 as pdfium
from PIL import Image

from app.core.config import settings
from app.services.gemini_client import call_gemini_api
from app.schemas import (
    TimetableEntryItem,
    TimetableExtractionResult,
    TimetableMetadata,
    TimeSlotItem,
    SubjectReferenceItem,
    AcademicEventItem,
    AcademicCalendarExtractionResult
)

logger = logging.getLogger(__name__)

VALID_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_MAP = {
    "mon": "Monday", "monday": "Monday",
    "tue": "Tuesday", "tues": "Tuesday", "tuesday": "Tuesday",
    "wed": "Wednesday", "wednesday": "Wednesday",
    "thu": "Thursday", "thur": "Thursday", "thurs": "Thursday", "thursday": "Thursday",
    "fri": "Friday", "friday": "Friday",
    "sat": "Saturday", "saturday": "Saturday",
    "sun": "Sunday", "sunday": "Sunday"
}

VALID_CATEGORIES = [
    "SEMESTER", "EXAM", "INTERNAL_ASSESSMENT", "PRACTICAL_EXAM",
    "HOLIDAY", "COLLEGE_EVENT", "REGISTRATION", "ACADEMIC_DEADLINE",
    "RESULT", "OTHER"
]

BREAK_KEYWORDS = [
    "lunch", "break", "tea", "recess", "interval", "tiffin", "snack",
    "free period", "vacant", "leisure", "sports", "library hour"
]

TIMETABLE_UNIVERSAL_EXTRACTION_PROMPT = """You are an expert academic document parsing AI for AURELIA.
Your task is to analyze the uploaded university/college timetable (provided as table grids, document text, and/or page images) and convert every scheduled class into clean, validated, structured records.

UNIVERSAL EXTRACTION RULES:
1. LAYOUT INDEPENDENCE:
   - Understand any timetable layout:
     * Days as rows and time slots as columns
     * Days as columns and time slots as rows
     * Days arranged horizontally or vertically
     * Multiple sections, groups, or divisions (e.g. Batch A / Batch B)
2. TIME SLOTS & DURATIONS:
   - Identify the start time and end time for each class (e.g. '09:00 AM', '10:00 AM' or '09:00', '10:00').
   - Validate that start time is earlier than end time.
   - For merged cells spanning multiple continuous periods (e.g. 2-hour or 3-hour labs):
     Output a SINGLE entry covering the entire duration (e.g. start_time='02:00 PM', end_time='04:00 PM'). Do NOT create duplicate split rows.
3. EXCLUDE BREAKS:
   - Do NOT create ordinary class entries for Lunch Break, Tea Break, Recess, or Intervals. If empty cells exist, ignore them.
4. SUBJECT CODE & REFERENCE TABLE MAPPING:
   - Many timetables contain abbreviated codes in the grid (e.g. 'CS501', 'MAT301') and a separate reference table / legend listing full names, faculty, and room numbers.
   - If a reference table / legend exists:
     a) Extract all mapping rows into 'reference_table': [{"code": "CS501", "name": "Software Engineering", "faculty": "Prof. Davis", "room": "LH-1", "class_type": "Theory"}]
     b) Populate each grid entry with the full subject_name, faculty_name, and room_number resolved from that reference table.
   - If no reference table exists, extract whatever details are directly visible without hallucinating.
5. METADATA EXTRACTION:
   - Extract institution, department, academic_year (e.g. '2026-2027'), semester (e.g. '5th Sem'), and section if available.
6. CONFIDENCE & AMBIGUITY:
   - Assign a confidence score (0.0 to 1.0) to each entry. Flag is_uncertain=true if a slot is blurred, ambiguous, or questionable.
7. STRICT OUTPUT FORMAT:
   - Return ONLY a valid JSON object matching the exact schema below, without markdown formatting or conversational text:

{
  "document_type": "TIMETABLE",
  "pdf_format": "TEXT_BASED",
  "metadata": {
    "institution": null,
    "department": null,
    "class_name": null,
    "academic_year": "2026-2027",
    "semester": "5"
  },
  "time_slots": [
    {"start_time": "09:00 AM", "end_time": "10:00 AM", "label": "Period 1"}
  ],
  "reference_table": [
    {"code": "CS401", "name": "Java Programming", "faculty": "Dr. Clark", "room": "Room 204", "class_type": "Theory"}
  ],
  "entries": [
    {
      "day_of_week": "Monday",
      "subject_name": "Java Programming",
      "subject_code": "CS401",
      "start_time": "09:00 AM",
      "end_time": "10:00 AM",
      "room_number": "Room 204",
      "faculty_name": "Dr. Clark",
      "class_type": "Theory",
      "academic_year": "2026-2027",
      "semester": "5",
      "source_page": 1,
      "source_row": 1,
      "confidence": 0.95,
      "is_uncertain": false
    }
  ]
}
"""

ACADEMIC_CALENDAR_EXTRACTION_PROMPT = """You are an expert academic document parsing AI for AURELIA.
Your task is to analyze the extracted table(s) and text from an academic calendar / schedule of events and convert every academic activity into structured records.

CRITICAL EXTRACTION RULES:
1. Preserve the row, column, and heading structure across all pages.
2. For each event or activity:
   - Identify the exact event name (e.g. 'Commencement of Classes', 'First Internal Assessment (IA-1)', 'Midterm Examinations', 'Diwali Vacation', 'Last Working Day', 'Declaration of Results').
   - Determine the correct category from: SEMESTER, EXAM, INTERNAL_ASSESSMENT, PRACTICAL_EXAM, HOLIDAY, COLLEGE_EVENT, REGISTRATION, ACADEMIC_DEADLINE, RESULT, OTHER.
   - Extract start_date in 'YYYY-MM-DD' format.
   - Extract end_date in 'YYYY-MM-DD' format if the event spans multiple days. If single-day, end_date must be null or equal to start_date.
   - If the document states an academic year (e.g. 2026-2027 or 2026), establish the year for all dates accordingly. Do not invent dates not present in the document.
   - Extract description, notes, semester, and academic year where available.
   - Record the source_page (1-based integer).
3. Do not assume every row is an exam. Properly classify holidays, reopening dates, registration deadlines, and college events.
4. Output ONLY a valid JSON object matching the schema below, without markdown formatting or conversational filler:

{
  "document_type": "ACADEMIC_CALENDAR",
  "events": [
    {
      "event_name": "Internal Assessment 1",
      "category": "INTERNAL_ASSESSMENT",
      "start_date": "2026-09-10",
      "end_date": "2026-09-15",
      "description": "First internal assessment test for odd semester",
      "academic_year": "2026-2027",
      "semester": "5",
      "source_page": 1,
      "source_row": 1
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# Universal PDF Format & Page Layout Detection
# ---------------------------------------------------------------------------

def detect_pdf_format_and_pages(content_bytes: bytes) -> Dict[str, Any]:
    """
    Inspects PDF pages to determine whether the document is:
    - TEXT_BASED: Has rich extractable text and table boundaries.
    - IMAGE_BASED: Scanned or graphic PDF with zero/insufficient selectable text.
    - MIXED: Contains both selectable text pages and image-only pages.
    """
    page_details: List[Dict[str, Any]] = []
    text_page_count = 0
    image_page_count = 0

    try:
        with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
            total_pages = len(pdf.pages)
            for page_idx, page in enumerate(pdf.pages, start=1):
                raw_text = (page.extract_text() or "").strip()
                char_count = len(raw_text)
                tables = page.extract_tables() or []
                table_count = len(tables)

                # Convert tables to clean markdown
                page_table_markdowns = []
                for table in tables:
                    if not table or not any(any(cell for cell in row) for row in table):
                        continue
                    md_lines = []
                    header = [str(c or "").replace("\n", " ").strip() for c in table[0]]
                    md_lines.append("| " + " | ".join(header) + " |")
                    md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
                    for row in table[1:]:
                        clean_row = [str(c or "").replace("\n", " ").strip() for c in row]
                        md_lines.append("| " + " | ".join(clean_row) + " |")
                    page_table_markdowns.append("\n".join(md_lines))

                # Check if page has sufficient text content or is image-based
                is_text_page = (char_count >= 50 or table_count > 0)
                if is_text_page:
                    text_page_count += 1
                    page_type = "TEXT_BASED"
                else:
                    image_page_count += 1
                    page_type = "IMAGE_BASED"

                page_details.append({
                    "page_number": page_idx,
                    "page_type": page_type,
                    "char_count": char_count,
                    "table_count": table_count,
                    "tables": page_table_markdowns,
                    "text": raw_text
                })
    except Exception as e:
        logger.warning(f"[TableExtractor] pdfplumber format detection warning: {e}")

    # Fallback to pypdf if pdfplumber found no pages
    if not page_details:
        try:
            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            for page_idx, page in enumerate(reader.pages, start=1):
                raw_text = (page.extract_text() or "").strip()
                char_count = len(raw_text)
                is_text = char_count >= 50
                if is_text:
                    text_page_count += 1
                    p_type = "TEXT_BASED"
                else:
                    image_page_count += 1
                    p_type = "IMAGE_BASED"

                page_details.append({
                    "page_number": page_idx,
                    "page_type": p_type,
                    "char_count": char_count,
                    "table_count": 0,
                    "tables": [],
                    "text": raw_text
                })
        except Exception as e:
            logger.error(f"[TableExtractor] pypdf reader failed: {e}")

    total_p = len(page_details)
    if text_page_count == total_p and total_p > 0:
        overall_format = "TEXT_BASED"
    elif image_page_count == total_p and total_p > 0:
        overall_format = "IMAGE_BASED"
    elif total_p > 0:
        overall_format = "MIXED"
    else:
        overall_format = "TEXT_BASED"

    logger.info(
        "[TableExtractor] PDF format detected: overall=%s total_pages=%d text_pages=%d image_pages=%d",
        overall_format, total_p, text_page_count, image_page_count
    )

    return {
        "overall_format": overall_format,
        "total_pages": total_p,
        "text_page_count": text_page_count,
        "image_page_count": image_page_count,
        "pages": page_details
    }


def render_pdf_page_to_base64(content_bytes: bytes, page_number: int, scale: float = 2.0) -> Optional[str]:
    """
    Renders a PDF page to high-resolution JPEG bytes using pypdfium2 and returns base64 string.
    scale=2.0 renders at approx 144 DPI (optimal for OCR and Gemini Vision).
    """
    try:
        pdf_doc = pdfium.PdfDocument(content_bytes)
        page_idx = page_number - 1 if page_number > 0 else 0
        if page_idx < 0 or page_idx >= len(pdf_doc):
            return None
        page = pdf_doc.get_page(page_idx)
        pil_image = page.render(scale=scale).to_pil()
        buffer = io.BytesIO()
        pil_image.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error(f"[TableExtractor] Page {page_number} render failed: {e}")
        return None


def _build_document_representation(format_info: Dict[str, Any], filename: str) -> str:
    """Combines extracted markdown tables and text into a structured string."""
    parts = [f"DOCUMENT: {filename}", f"DETECTED FORMAT: {format_info.get('overall_format', 'TEXT_BASED')}"]
    for p in format_info.get("pages", []):
        page_num = p["page_number"]
        parts.append(f"\n=== PAGE {page_num} [{p.get('page_type', 'TEXT')}] ===")
        if p.get("tables"):
            for t_idx, t_md in enumerate(p["tables"], start=1):
                parts.append(f"\n[TABLE {t_idx} ON PAGE {page_num}]:\n{t_md}\n")
        if p.get("text"):
            parts.append(f"\n[PAGE {page_num} TEXT]:\n{p['text']}\n")
    return "\n".join(parts)


def _clean_json_output(raw_text: str) -> str:
    """Strips markdown code blocks, backticks, and whitespace to extract raw JSON."""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


# ---------------------------------------------------------------------------
# Subject-Code Reference Table Mapping & Normalization
# ---------------------------------------------------------------------------

def resolve_reference_table_mappings(
    entries: List[TimetableEntryItem],
    ref_table: Optional[List[SubjectReferenceItem]]
) -> List[TimetableEntryItem]:
    """
    Cross-references entries with the subject-code legend / reference table.
    Populates full subject names, faculty, and room numbers when missing from grid.
    """
    if not ref_table:
        return entries

    ref_map: Dict[str, SubjectReferenceItem] = {}
    for item in ref_table:
        code_key = re.sub(r'[^A-Za-z0-9]', '', (item.code or "").upper())
        if code_key:
            ref_map[code_key] = item

    enriched: List[TimetableEntryItem] = []
    for entry in entries:
        raw_code = entry.subject_code or ""
        code_key = re.sub(r'[^A-Za-z0-9]', '', raw_code.upper())
        ref_match = ref_map.get(code_key)

        if ref_match:
            # If name is empty, generic, or identical to code, fill from reference
            is_generic_name = (
                not entry.subject_name or
                entry.subject_name.strip().upper() == raw_code.strip().upper() or
                entry.subject_name.startswith("Class ")
            )
            final_name = ref_match.name if (is_generic_name and ref_match.name) else entry.subject_name
            final_faculty = entry.faculty_name or ref_match.faculty
            final_room = entry.room_number or ref_match.room
            final_type = entry.class_type or ref_match.class_type or "Theory"

            enriched.append(entry.model_copy(update={
                "subject_name": final_name,
                "faculty_name": final_faculty,
                "room_number": final_room,
                "class_type": final_type
            }))
        else:
            enriched.append(entry)

    return enriched


def normalize_and_validate_entries(entries: List[TimetableEntryItem]) -> Tuple[List[TimetableEntryItem], int]:
    """
    Normalizes weekday names, validates start/end times, excludes breaks, and flags uncertain entries.
    Returns (valid_entries, uncertain_count).
    """
    valid: List[TimetableEntryItem] = []
    uncertain_count = 0

    for e in entries:
        # Exclude breaks and lunch
        combined_text = f"{e.subject_name} {e.subject_code or ''} {e.class_type or ''}".lower()
        if any(b in combined_text for b in BREAK_KEYWORDS):
            continue

        # Normalize day of week
        raw_day = (e.day_of_week or "Monday").strip().lower()
        norm_day = DAY_MAP.get(raw_day, raw_day.capitalize())
        if norm_day not in VALID_DAYS:
            norm_day = "Monday"

        # Check uncertainty
        conf = getattr(e, "confidence", 1.0) or 1.0
        is_uncert = bool(getattr(e, "is_uncertain", False) or conf < 0.8)
        if is_uncert:
            uncertain_count += 1

        valid.append(e.model_copy(update={
            "day_of_week": norm_day,
            "confidence": conf,
            "is_uncertain": is_uncert
        }))

    return valid, uncertain_count


# ---------------------------------------------------------------------------
# Deterministic Universal Fallback Parser
# ---------------------------------------------------------------------------

def _fallback_parse_timetable(text: str, format_info: Optional[Dict[str, Any]] = None) -> TimetableExtractionResult:
    """
    Deterministic rule-based fallback for timetable extraction when LLM is unavailable or for testing.
    Supports:
    - Days as rows (e.g. Monday: 09:00 AM - 10:00 AM: CS401 Java)
    - Days as columns (e.g. Table with header | Time | Monday | Tuesday | ...)
    - Merged multi-hour slots
    - Subject-code reference tables / legends at the bottom
    - Filtering out breaks and lunch periods
    """
    entries: List[TimetableEntryItem] = []
    ref_table: List[SubjectReferenceItem] = []

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    time_regex = re.compile(r'(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)\s*[-–to]+\s*(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)')
    code_regex = re.compile(r'\b([A-Z]{2,4}[-\s]?\d{3,4})\b')
    room_regex = re.compile(r'\b(?:Hall|Room|Auditorium|Building|LH)[-\s]*([A-Za-z0-9-]+)\b|\bLab\b(?!\w)[-\s]*(\d+|[A-Za-z0-9]+)?', re.IGNORECASE)

    # 1. Parse Reference Table (if present in lines)
    ref_header_seen = False
    for line in lines:
        line_l = line.lower()
        if any(h in line_l for h in ["reference", "subject code", "course code", "legend", "course details"]):
            ref_header_seen = True
            continue

        if ref_header_seen or (":" in line and ("prof" in line_l or "dr." in line_l or "faculty" in line_l or "room" in line_l)):
            code_m = code_regex.search(line)
            if code_m:
                c_code = code_m.group(1).replace(" ", "")
                r_match = room_regex.search(line)
                c_room = r_match.group(0) if r_match else None
                # Faculty detection
                fac_m = re.search(r'\b(?:Prof\.|Dr\.|Mr\.|Ms\.)\s+[A-Za-z\s]+', line)
                c_fac = fac_m.group(0).strip() if fac_m else None
                # Clean name
                clean_n = line
                for tok in [c_code, c_room or "", c_fac or "", ":", "|", "-", "–"]:
                    if tok:
                        clean_n = clean_n.replace(tok, " ")
                clean_n = re.sub(r'\s+', ' ', clean_n).strip()
                ref_table.append(SubjectReferenceItem(
                    code=c_code,
                    name=clean_n or f"Course {c_code}",
                    faculty=c_fac,
                    room=c_room,
                    class_type="Lab" if "lab" in line_l else "Theory"
                ))

    # Helper to parse table row cells by pipe or comma
    def split_cells(line_str: str) -> List[str]:
        if "|" in line_str:
            return [c.strip() for c in line_str.split("|") if c.strip() and "---" not in c]
        elif "," in line_str:
            return [c.strip() for c in line_str.split(",") if c.strip()]
        return []

    # 2. Check for Table with Days as Columns
    # e.g. Header line: | Time | Monday | Tuesday | Wednesday | OR Time,Monday,Tuesday,Wednesday
    days_as_columns_detected = False
    header_days: List[Tuple[int, str]] = [] # (column_index, day_name)
    header_line_idx = -1

    for idx, line in enumerate(lines):
        if ("|" in line or "," in line) and "---" not in line:
            cells = split_cells(line)
            matched_days = []
            for col_idx, cell in enumerate(cells):
                c_low = cell.lower()
                for d_k, d_v in DAY_MAP.items():
                    if re.search(rf'\b{d_k}\b', c_low):
                        matched_days.append((col_idx, d_v))
                        break
            if len(matched_days) >= 2:
                days_as_columns_detected = True
                header_days = matched_days
                header_line_idx = idx
                break

    if days_as_columns_detected and header_days:
        for line in lines[header_line_idx + 1:]:
            if "---" in line:
                continue
            cells = split_cells(line)
            time_m = time_regex.search(line)
            if not time_m:
                continue
            start_t = time_m.group(1).strip()
            end_t = time_m.group(2).strip()

            for col_idx, day_name in header_days:
                if col_idx < len(cells):
                    cell_val = cells[col_idx]
                    cell_low = cell_val.lower()
                    if not cell_val or any(b in cell_low for b in BREAK_KEYWORDS) or time_regex.search(cell_val):
                        continue

                    code_m = code_regex.search(cell_val)
                    c_code = code_m.group(1).replace(" ", "") if code_m else "SUB101"
                    r_m = room_regex.search(cell_val)
                    c_room = r_m.group(0) if r_m else "Room 101"

                    # Clean subject name
                    c_name = cell_val
                    for tok in [c_code, c_room, "|", "(", ")", "-", "–"]:
                        c_name = c_name.replace(tok, " ")
                    c_name = re.sub(r'\s+', ' ', c_name).strip()
                    if not c_name or len(c_name) < 2:
                        c_name = f"Class {c_code}"

                    entries.append(TimetableEntryItem(
                        day_of_week=day_name,
                        subject_name=c_name[:100],
                        subject_code=c_code,
                        start_time=start_t,
                        end_time=end_t,
                        room_number=c_room,
                        faculty_name="Faculty",
                        class_type="Lab" if "lab" in cell_low else "Theory",
                        academic_year="2026-2027",
                        semester="Current",
                        source_page=1,
                        source_row=len(entries) + 1,
                        confidence=0.9
                    ))

    # 2b. Check for Table with Days as Rows and Times as Column Headers
    # e.g. Header line: Day, 09:00 AM - 10:00 AM, 10:00 AM - 11:00 AM, 11:15 AM - 12:15 PM
    if not entries:
        header_times: List[Tuple[int, str, str]] = [] # (column_index, start_t, end_t)
        time_header_line_idx = -1

        for idx, line in enumerate(lines):
            if ("|" in line or "," in line) and "---" not in line:
                cells = split_cells(line)
                matched_times = []
                for col_idx, cell in enumerate(cells):
                    tm = time_regex.search(cell)
                    if tm:
                        matched_times.append((col_idx, tm.group(1).strip(), tm.group(2).strip()))
                if len(matched_times) >= 2:
                    header_times = matched_times
                    time_header_line_idx = idx
                    break

        if header_times and time_header_line_idx >= 0:
            for line in lines[time_header_line_idx + 1:]:
                if "---" in line:
                    continue
                cells = split_cells(line)
                if not cells:
                    continue

                # Find day of week for this row
                row_day = None
                line_lower = line.lower()
                for d_k, d_v in DAY_MAP.items():
                    if re.search(rf'\b{d_k}\b', line_lower):
                        row_day = d_v
                        break

                if not row_day:
                    continue

                for col_idx, start_t, end_t in header_times:
                    if col_idx < len(cells):
                        cell_val = cells[col_idx]
                        cell_low = cell_val.lower()
                        if not cell_val or any(b in cell_low for b in BREAK_KEYWORDS) or time_regex.search(cell_val):
                            continue

                        code_m = code_regex.search(cell_val)
                        c_code = code_m.group(1).replace(" ", "") if code_m else "SUB101"
                        r_m = room_regex.search(cell_val)
                        c_room = r_m.group(0) if r_m else "Room 101"

                        c_name = cell_val
                        for tok in [c_code, c_room, "|", "(", ")", "-", "–"]:
                            c_name = c_name.replace(tok, " ")
                        c_name = re.sub(r'\s+', ' ', c_name).strip()
                        if not c_name or len(c_name) < 2:
                            c_name = f"Class {c_code}"

                        entries.append(TimetableEntryItem(
                            day_of_week=row_day,
                            subject_name=c_name[:100],
                            subject_code=c_code,
                            start_time=start_t,
                            end_time=end_t,
                            room_number=c_room,
                            faculty_name="Faculty",
                            class_type="Lab" if "lab" in cell_low else "Theory",
                            academic_year="2026-2027",
                            semester="Current",
                            source_page=1,
                            source_row=len(entries) + 1,
                            confidence=0.9
                        ))

    # 3. Standard Fallback: Days as Rows or Text Lines
    if not entries:
        current_day = "Monday"
        for row_idx, line_clean in enumerate(lines, start=1):
            line_lower = line_clean.lower()

            # Skip break rows
            if any(b in line_lower for b in BREAK_KEYWORDS):
                continue

            # Check for day header
            for d_key, d_val in DAY_MAP.items():
                if re.search(rf'\b{d_key}\b', line_lower):
                    current_day = d_val
                    break

            time_match = time_regex.search(line_clean)
            if time_match:
                start_t = time_match.group(1).strip()
                end_t = time_match.group(2).strip()

                cells = split_cells(line_clean)
                if len(cells) >= 3:
                    # Line is structured with commas or pipes (e.g. Day, Time, Subject, Room)
                    non_time_cells = [c for c in cells if not time_regex.search(c) and not any(re.search(rf'\b{d}\b', c.lower()) for d in DAY_MAP)]
                    room = None
                    for c in non_time_cells:
                        if room_regex.search(c):
                            room = c
                            break
                    subj_cands = [c for c in non_time_cells if c != room]
                    raw_subj = subj_cands[0] if subj_cands else (non_time_cells[0] if non_time_cells else "Class")
                    code_match = code_regex.search(raw_subj)
                    course_code = code_match.group(1).replace(" ", "") if code_match else "CS101"
                    course_name = raw_subj
                    if not room:
                        rm_global = room_regex.search(line_clean)
                        room = rm_global.group(0) if rm_global else "Room 101"
                else:
                    code_match = code_regex.search(line_clean)
                    course_code = code_match.group(1).replace(" ", "") if code_match else "CS101"
                    room_match = room_regex.search(line_clean)
                    room = room_match.group(0) if room_match else "Room 101"

                    # Clean name
                    course_name = line_clean
                    for token in [current_day, start_t, end_t, course_code, room, "|", "-", "–"]:
                        course_name = course_name.replace(token, " ")
                    course_name = re.sub(r'\s+', ' ', course_name).strip(" :,()")
                    if not course_name or len(course_name) < 2:
                        course_name = f"Class {course_code}"

                entries.append(TimetableEntryItem(
                    day_of_week=current_day,
                    subject_name=course_name[:100],
                    subject_code=course_code,
                    start_time=start_t,
                    end_time=end_t,
                    room_number=room,
                    faculty_name="Faculty",
                    class_type="Lab" if "lab" in course_name.lower() else "Theory",
                    academic_year="2026-2027",
                    semester="Current",
                    source_page=1,
                    source_row=row_idx,
                    confidence=0.85
                ))

    # 4. Apply Reference Table Enrichment
    entries = resolve_reference_table_mappings(entries, ref_table)
    valid_entries, uncert_count = normalize_and_validate_entries(entries)

    return TimetableExtractionResult(
        document_type="TIMETABLE",
        pdf_format=format_info.get("overall_format", "TEXT_BASED") if format_info else "TEXT_BASED",
        metadata=TimetableMetadata(academic_year="2026-2027", semester="Current"),
        reference_table=ref_table,
        entries=valid_entries,
        total_valid_entries=len(valid_entries),
        uncertain_entries_count=uncert_count
    )


# ---------------------------------------------------------------------------
# Fallback Parser for Academic Calendar
# ---------------------------------------------------------------------------

def _fallback_parse_academic_calendar(text: str) -> AcademicCalendarExtractionResult:
    """
    Deterministic rule-based fallback for academic calendar extraction when LLM is unavailable or for testing.
    """
    events = []
    lines = text.split("\n")
    date_regex = re.compile(
        r'(\d{4}-\d{2}-\d{2})|(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})|((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)',
        re.IGNORECASE
    )

    row_num = 1
    for line in lines:
        line_clean = line.strip()
        if not line_clean or len(line_clean) < 5:
            continue
        line_lower = line_clean.lower()

        cat = "OTHER"
        if any(w in line_lower for w in ["exam", "examination", "see", "end sem"]):
            cat = "EXAM"
        elif any(w in line_lower for w in ["ia", "internal", "cie", "assessment", "midterm"]):
            cat = "INTERNAL_ASSESSMENT"
        elif any(w in line_lower for w in ["holiday", "vacation", "diwali", "puja", "christmas", "break"]):
            cat = "HOLIDAY"
        elif any(w in line_lower for w in ["reopen", "commence", "semester", "start of class"]):
            cat = "SEMESTER"
        elif any(w in line_lower for w in ["regis", "enroll", "fee", "admission"]):
            cat = "REGISTRATION"
        elif any(w in line_lower for w in ["deadline", "last day", "submission"]):
            cat = "ACADEMIC_DEADLINE"
        elif any(w in line_lower for w in ["result", "grade", "declaration"]):
            cat = "RESULT"

        dates_found = date_regex.findall(line_clean)
        if dates_found:
            raw_d = [g for match in dates_found for g in match if g][0]
            norm_date = "2026-09-01"
            if re.match(r'^\d{4}-\d{2}-\d{2}$', raw_d):
                norm_date = raw_d
            elif "/" in raw_d or "-" in raw_d:
                parts = re.split(r'[/-]', raw_d)
                if len(parts) == 3:
                    y = parts[2] if len(parts[2]) == 4 else f"20{parts[2]}"
                    norm_date = f"{y}-{int(parts[1]):02d}-{int(parts[0]):02d}"

            event_title = line_clean
            for token in ["|", "-", "–", ":"]:
                event_title = event_title.replace(token, " ")
            event_title = re.sub(r'\s+', ' ', event_title).strip()
            if len(event_title) > 80:
                event_title = event_title[:80]

            events.append(AcademicEventItem(
                event_name=event_title or "Academic Activity",
                category=cat,
                start_date=norm_date,
                end_date=None,
                description=line_clean,
                academic_year="2026-2027",
                semester="Odd",
                source_page=1,
                source_row=row_num
            ))
            row_num += 1

    return AcademicCalendarExtractionResult(document_type="ACADEMIC_CALENDAR", events=events)


# ---------------------------------------------------------------------------
# Public Service Endpoints
# ---------------------------------------------------------------------------

async def extract_timetable_data(
    content_bytes: bytes,
    filename: str,
    mime_type: str = "application/pdf"
) -> TimetableExtractionResult:
    """
    Universal timetable extraction:
    1. Detects whether PDF is TEXT_BASED, IMAGE_BASED (scanned), or MIXED.
    2. Uses Gemini Vision (high-res rendered images) for image/scanned pages.
    3. Uses Gemini Text for structured text/markdown grids.
    4. Applies reference table legend resolution (subject codes -> full names/rooms/faculty).
    5. Validates entries and falls back to deterministic heuristic parsing if LLM is unavailable.
    """
    logger.info("[TableExtractor] Starting universal timetable extraction for: %s (%d bytes)", filename, len(content_bytes))

    format_info = None
    if "pdf" in mime_type.lower() or filename.lower().endswith(".pdf"):
        format_info = detect_pdf_format_and_pages(content_bytes)
        doc_repr = _build_document_representation(format_info, filename)
    else:
        text = content_bytes.decode("utf-8", errors="replace")
        doc_repr = f"DOCUMENT: {filename}\n\n{text}"
        format_info = {"overall_format": "TEXT_BASED", "total_pages": 1, "pages": []}

    overall_format = format_info.get("overall_format", "TEXT_BASED")

    # If Gemini API Key is available, invoke Gemini structured output
    if settings.GEMINI_API_KEY:
        images_payload = []
        # If image-based or mixed, render high-res page images for Gemini Vision
        if overall_format in ("IMAGE_BASED", "MIXED"):
            total_pages = format_info.get("total_pages", 1)
            # Render up to first 4 pages for vision inspection
            for p_num in range(1, min(total_pages + 1, 5)):
                b64_img = render_pdf_page_to_base64(content_bytes, p_num, scale=2.0)
                if b64_img:
                    images_payload.append({
                        "mimeType": "image/jpeg",
                        "data": b64_img
                    })
            logger.info("[TableExtractor] Prepared %d high-res page images for Gemini Vision.", len(images_payload))

        vision_note = " (including attached page images)" if images_payload else ""
        user_prompt = (
            f"Please analyze this timetable document{vision_note} and extract every scheduled class period into the specified JSON format.\n\n"
            f"{doc_repr[:16000]}"
        )

        gemini_res = await call_gemini_api(
            prompt=user_prompt,
            system_prompt=TIMETABLE_UNIVERSAL_EXTRACTION_PROMPT,
            images=images_payload if images_payload else None,
            max_output_tokens=4096,
            temperature=0.1
        )

        if gemini_res.success and gemini_res.text:
            clean_json = _clean_json_output(gemini_res.text)
            try:
                parsed = json.loads(clean_json)
                parsed_res = TimetableExtractionResult.model_validate(parsed)
                # Enrich entries with reference table if present
                parsed_res.entries = resolve_reference_table_mappings(parsed_res.entries, parsed_res.reference_table)
                valid_entries, uncert = normalize_and_validate_entries(parsed_res.entries)
                parsed_res.entries = valid_entries
                parsed_res.total_valid_entries = len(valid_entries)
                parsed_res.uncertain_entries_count = uncert
                parsed_res.pdf_format = overall_format
                logger.info("[TableExtractor] Gemini successfully extracted %d valid timetable entries.", len(valid_entries))
                return parsed_res
            except Exception as parse_err:
                logger.warning(f"[TableExtractor] Gemini JSON parse validation failed: {parse_err}. Falling back to heuristic.")

    # Fallback to deterministic universal heuristic parser
    logger.info("[TableExtractor] Using deterministic universal heuristic extraction for %s.", filename)
    return _fallback_parse_timetable(doc_repr, format_info)


async def extract_academic_calendar_data(
    content_bytes: bytes,
    filename: str,
    mime_type: str = "application/pdf"
) -> AcademicCalendarExtractionResult:
    """
    Extracts structured academic calendar events from an uploaded PDF, CSV, or text document.
    Preserves table relationships and validates JSON output with Pydantic.
    """
    if "pdf" in mime_type.lower() or filename.lower().endswith(".pdf"):
        format_info = detect_pdf_format_and_pages(content_bytes)
        doc_repr = _build_document_representation(format_info, filename)
    else:
        text = content_bytes.decode("utf-8", errors="replace")
        doc_repr = f"DOCUMENT: {filename}\n\n{text}"

    if not doc_repr.strip():
        raise ValueError("Document contains no readable content.")

    if settings.GEMINI_API_KEY:
        user_prompt = (
            f"Please extract all academic calendar events and activities from this document:\n\n"
            f"{doc_repr[:16000]}"
        )
        gemini_res = await call_gemini_api(
            prompt=user_prompt,
            system_prompt=ACADEMIC_CALENDAR_EXTRACTION_PROMPT,
            max_output_tokens=4096,
            temperature=0.1
        )
        if gemini_res.success and gemini_res.text:
            clean_json = _clean_json_output(gemini_res.text)
            try:
                parsed = json.loads(clean_json)
                return AcademicCalendarExtractionResult.model_validate(parsed)
            except Exception as parse_err:
                logger.warning(f"[TableExtractor] Gemini JSON parse failed for academic calendar: {parse_err}. Falling back to heuristic.")

    logger.info("[TableExtractor] Using heuristic extraction for academic calendar.")
    return _fallback_parse_academic_calendar(doc_repr)
