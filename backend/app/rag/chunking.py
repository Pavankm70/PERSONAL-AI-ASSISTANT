import re
from typing import List, Dict, Any, Optional

SECTION_PATTERNS = [
    # Markdown headings
    r'^#{1,4}\s+(.+)$',
    # Unit, Chapter, Module, Section, Part headings (e.g. "UNIT 3: NORMALIZATION", "Unit 3 - Normalization", "Chapter 2: Relational Model")
    r'^(?:UNIT|CHAPTER|MODULE|SECTION|PART|LESSON)\s+[0-9IVXLCDMivxlcdm]+(?::|\s*[-–]\s*|\s+).+$',
    r'^(?:UNIT|CHAPTER|MODULE|SECTION|PART|LESSON)\s+[0-9IVXLCDMivxlcdm]+$',
    # Numbered headings (e.g. "1.1 Introduction", "3.0 Relational Design")
    r'^[0-9]+(?:\.[0-9]+)+\s+(.+)$',
    # All-caps headings (e.g. "COURSE OBJECTIVES", "NORMALIZATION AND DATABASE DESIGN")
    r'^[A-Z0-9\s,:\-–]{4,80}$'
]

def extract_section_header(text: str) -> Optional[str]:
    """
    Extracts a section header if the text begins with or contains a prominent heading,
    such as Markdown headers, Unit/Chapter numbers, or uppercase titles.
    """
    if not text or not text.strip():
        return None
    first_line = text.strip().splitlines()[0].strip()
    if not first_line or len(first_line) > 120:
        return None

    if first_line.startswith("#"):
        return first_line.lstrip("#").strip()

    # Check for unit / chapter / module patterns (case-insensitive)
    unit_match = re.match(r'^(?:UNIT|CHAPTER|MODULE|SECTION|PART|LESSON)\s+[0-9IVXLCDMivxlcdm]+(?::|\s*[-–]\s*|\s+)?.*', first_line, re.IGNORECASE)
    if unit_match and len(first_line) < 100:
        return first_line.strip().rstrip(":")

    # Check for numbered headings
    num_match = re.match(r'^[0-9]+(?:\.[0-9]+)*\s+[A-Za-z0-9]', first_line)
    if num_match and len(first_line) < 80:
        return first_line.strip().rstrip(":")

    # Check for prominent uppercase titles (at least 2 alphabetic words, >70% uppercase)
    letters = [c for c in first_line if c.isalpha()]
    if len(letters) >= 6 and len(first_line) < 80:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.75 and not first_line.endswith("."):
            return first_line.strip().rstrip(":")

    return None

def split_into_sentences(text: str) -> List[str]:
    """Splits a paragraph into clean sentences without splitting decimals or abbreviations."""
    if not text:
        return []
    # Avoid splitting on common abbreviations like e.g., i.e., Dr., Prof., etc.
    sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]

def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 120,
    page_number: int = 1,
    start_index: int = 0,
    section_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Structure-aware recursive text splitter:
    - Preserves paragraphs and complete sentences.
    - Tracks section headings across chunks so evidence retain section context.
    - Employs whole-sentence overlap rather than cutting words in half.
    """
    if not text or not text.strip():
        return []

    clean = re.sub(r'\r\n', '\n', text)
    paragraphs = [p.strip() for p in clean.split('\n\n') if p.strip()]

    chunks = []
    current_sentences: List[str] = []
    current_length = 0
    chunk_index = start_index
    active_section = section_name or ""

    def flush_chunk(sentences: List[str], header: str):
        nonlocal chunk_index
        if not sentences:
            return None
        body = " ".join(sentences).strip()
        if not body:
            return None
        
        # Attach section header metadata to chunk content if identified
        prefix = f"[Section: {header}]\n" if header else ""
        content = prefix + body

        chunk_obj = {
            "chunk_index": chunk_index,
            "content": content,
            "page_number": page_number,
            "section": header
        }
        chunk_index += 1
        return chunk_obj

    for para in paragraphs:
        # Detect section headings in the paragraph
        detected_header = extract_section_header(para)
        if detected_header:
            active_section = detected_header

        para_sentences = split_into_sentences(para)
        if not para_sentences:
            para_sentences = [para]

        for s in para_sentences:
            s_len = len(s)
            # If adding sentence exceeds target chunk size and we already have content:
            if current_length + s_len > chunk_size and current_sentences:
                new_chunk = flush_chunk(current_sentences, active_section)
                if new_chunk:
                    chunks.append(new_chunk)

                # Sentence-based overlap: take the last sentence(s) up to overlap limit
                overlap_sentences = []
                overlap_len = 0
                for prev_s in reversed(current_sentences):
                    if overlap_len + len(prev_s) <= overlap:
                        overlap_sentences.insert(0, prev_s)
                        overlap_len += len(prev_s) + 1
                    else:
                        break

                current_sentences = overlap_sentences + [s]
                current_length = sum(len(x) for x in current_sentences) + len(current_sentences)
            else:
                current_sentences.append(s)
                current_length += s_len + 1

    # Flush remaining sentences
    if current_sentences:
        last_chunk = flush_chunk(current_sentences, active_section)
        if last_chunk:
            chunks.append(last_chunk)

    return chunks

def chunk_pages(
    pages: List[Dict[str, Any]],
    chunk_size: int = 800,
    overlap: int = 120
) -> List[Dict[str, Any]]:
    """
    Chunks a list of pages with accurate page boundaries and continuous section awareness.
    """
    all_chunks = []
    current_index = 0
    active_section = ""

    for page in pages:
        p_num = page.get("page_number", 1)
        p_text = page.get("text", "")
        p_chunks = chunk_text(
            p_text,
            chunk_size=chunk_size,
            overlap=overlap,
            page_number=p_num,
            start_index=current_index,
            section_name=active_section
        )
        if p_chunks:
            # Update active section for next page continuity
            active_section = p_chunks[-1].get("section", active_section)
            all_chunks.extend(p_chunks)
            current_index += len(p_chunks)

    return all_chunks
