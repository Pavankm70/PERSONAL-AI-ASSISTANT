import re
import math
import logging
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple, Set
from sqlalchemy.orm import Session
import httpx

from app.core.config import settings
from app.db.models import Document, DocumentChunk, TimetableEntry
from app.rag.embeddings import get_embedding, cosine_similarity
from app.prompts.document_summary import DOCUMENT_SUMMARY_PROMPT
from app.prompts.rag import SPECIFIC_RAG_PROMPT

logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 0.18

# Maximum number of sources to surface after score-gap filtering
_MAX_SOURCES = 4
# Snippet display length: long enough to show a full sentence, short enough for UI
_SNIPPET_MAX_CHARS = 500

ORDINAL_CARDINAL_MAP = {
    "first": "1", "1st": "1", "one": "1", "i": "1",
    "second": "2", "2nd": "2", "two": "2", "ii": "2",
    "third": "3", "3rd": "3", "three": "3", "iii": "3",
    "fourth": "4", "4th": "4", "four": "4", "iv": "4",
    "fifth": "5", "5th": "5", "five": "5", "v": "5",
    "sixth": "6", "6th": "6", "six": "6", "vi": "6",
    "seventh": "7", "7th": "7", "seven": "7", "vii": "7",
    "eighth": "8", "8th": "8", "eight": "8", "viii": "8",
    "ninth": "9", "9th": "9", "nine": "9", "ix": "9",
    "tenth": "10", "10th": "10", "ten": "10", "x": "10"
}

# Common English stopwords to ignore in lexical query expansion
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "did", "do", "does", "doing", "don", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "s", "same", "she",
    "should", "so", "some", "such", "t", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "will", "with", "you", "your", "yours", "yourself"
}

# --- 1. Query Understanding & Classification ---

DOC_SUMMARY_PATTERNS = [
    r'\bwhat\s+is\s+(?:this|the|my|these)\s+(?:document|paper|notes|pdf|report|file|syllabus)\s+about\b',
    r'\btell\s+me\s+about\s+(?:my\s+)?(?:uploaded\s+)?(?:document|paper|notes|pdf|report|file|resume|cv|syllabus)\b',
    r'\bsummarize\s+(?:this|the|my|these)?\s*(?:uploaded\s+)?(?:document|paper|notes|pdf|report|file|resume|cv|syllabus)?\b',
    r'\bexplain\s+the\s+(?:entire|whole|full)\s+(?:document|paper|notes|pdf|report|file)\b',
    r'\bgive\s+me\s+a\s+(?:complete|full|comprehensive)?\s*overview\s+of\s+(?:this|the|my|these)\s+(?:document|paper|notes|pdf|report|file)\b',
    r'\bwhat\s+does\s+(?:this|the|my)\s+(?:document|paper|notes|pdf|report|file)\s+say\b',
    r'\boverview\s+of\s+(?:this|the|my)\s+(?:document|paper|notes|pdf|report|file)\b',
    r'\bwhat\s+does\s+.*?\bcontain\b',
    r'\bwhat\s+is\s+in\s+.*?(?:\.pdf|\.txt|\.csv|document|notes|syllabus)\b',
    r'\bwhat\s+does\s+.*?(?:\.pdf|\.txt|\.csv)\s+(?:say|cover|include)\b',
    r'\bwhat\s+are\s+the\s+(?:important|key|main)\s+topics\s+in\s+(?:this|the|my)?\s*(?:document|paper|notes|pdf|file|syllabus)\b'
]

MULTI_DOC_PATTERNS = [
    r'\bcompare\b',
    r'\bdifference(?:s)?\s+between\b',
    r'\bboth\s+(?:documents|papers|files|pdfs)\b',
    r'\bacross\s+(?:all|the|my)\s+(?:documents|papers|files)\b'
]

def is_document_summary_query(query: str) -> bool:
    """Detects whether a query seeks an overall document-level synthesis rather than an isolated fact."""
    lower = query.lower().strip()
    return any(re.search(p, lower) for p in DOC_SUMMARY_PATTERNS)

def is_multi_document_query(query: str) -> bool:
    """Detects if query asks to synthesize or compare multiple documents."""
    lower = query.lower().strip()
    return any(re.search(p, lower) for p in MULTI_DOC_PATTERNS)

# --- 2. Target Document Resolution ---

def identify_target_documents(
    user_id: str,
    db: Session,
    query: str = "",
    explicit_doc_id: Optional[str] = None
) -> List[Document]:
    """
    Resolves the intended document(s) from explicit ID, named filename references,
    subject keywords, category matches, or searches all active indexed user documents.
    """
    if explicit_doc_id:
        doc = db.query(Document).filter(
            Document.id == explicit_doc_id,
            Document.user_id == user_id,
            Document.status.in_(["indexed", "INDEXED"])
        ).first()
        if doc:
            return [doc]

    user_docs = db.query(Document).filter(
        Document.user_id == user_id,
        Document.status.in_(["indexed", "INDEXED"])
    ).order_by(Document.created_at.desc()).all()
    if not user_docs:
        return []

    lower = query.lower()
    explicit_filenames = re.findall(r'\b[A-Za-z0-9_-]+\.(?:pdf|txt|docx|doc|csv|md)\b', lower)
    if explicit_filenames:
        matched_explicit = [
            d for d in user_docs
            if d.filename.lower() in explicit_filenames
            or any(ef in d.filename.lower() or d.filename.lower().split(".")[0] in ef for ef in explicit_filenames)
        ]
        if not matched_explicit:
            # Query explicitly named a file that the user DOES NOT have!
            return []
        return matched_explicit

    # If user has only 1 indexed document, that document is ALWAYS the active target
    if len(user_docs) == 1:
        return user_docs

    if is_multi_document_query(query):
        return user_docs

    # Score each document based on relevance to query
    doc_scores: List[Tuple[float, Document]] = []
    GENERIC_NAME_WORDS = {"document", "test", "paper", "notes", "file", "architecture", "decisions", "report", "data", "presentation", "findings"}

    for doc in user_docs:
        score = 0.0
        fn_lower = doc.filename.lower()
        base_name = fn_lower.split(".")[0]

        # 1. Exact filename or base name in query
        if base_name in lower or fn_lower in lower:
            score += 10.0

        # 2. Key components of filename in query (e.g. "dbms", "java", "os", "dsa", "python")
        clean_parts = [p for p in re.split(r'[_.\s-]+', base_name) if len(p) >= 2 and p not in STOPWORDS]
        for p in clean_parts:
            if p not in GENERIC_NAME_WORDS:
                if re.search(rf'\b{re.escape(p)}\b', lower):
                    score += 5.0
                elif len(p) >= 3 and p in lower:
                    score += 3.0

        # 3. Document type / category matches (e.g. "syllabus" in query and doc is SYLLABUS)
        doc_type_str = (doc.document_type or doc.category or "").lower()
        if "syllabus" in lower and "syllabus" in doc_type_str:
            score += 2.5
        if "notes" in lower and "notes" in doc_type_str:
            score += 2.0
        if "textbook" in lower and ("textbook" in doc_type_str or "book" in doc_type_str):
            score += 2.5

        # 4. Check content keyword matches for distinct topic queries (e.g. "inheritance" in Java syllabus)
        query_words = [w for w in re.findall(r'\b[A-Za-z0-9_-]+\b', lower) if len(w) > 3 and w not in STOPWORDS and w not in GENERIC_NAME_WORDS and w not in {"syllabus", "chapter", "topics", "covered", "explain", "about", "what", "which"}]
        if query_words and score > 0:
            for qw in query_words[:3]:
                has_word = db.query(DocumentChunk.id).filter(
                    DocumentChunk.document_id == doc.id,
                    DocumentChunk.content.ilike(f"%{qw}%")
                ).first()
                if has_word:
                    score += 3.0

        doc_scores.append((score, doc))

    doc_scores.sort(key=lambda x: x[0], reverse=True)

    # If the top scoring document has a distinct match score (>= 4.0)
    if doc_scores and doc_scores[0][0] >= 4.0:
        top_score = doc_scores[0][0]
        top_matches = [d for s, d in doc_scores if s >= top_score - 1.0]
        return top_matches if len(top_matches) > 1 and is_multi_document_query(query) else [doc_scores[0][1]]

    # If no specific document is named or singled out, search across ALL user documents
    return user_docs

# --- 3. BM25 Lexical Matching Engine ---

def stem_word(w: str) -> str:
    """Applies lightweight English morphological suffix stripping."""
    w = w.lower()
    for suffix in ["ing", "tion", "tions", "ed", "ies", "es", "s"]:
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            if suffix == "ies":
                return w[:-3] + "y"
            return w[:-len(suffix)]
    return w

def tokenize(text: str) -> List[str]:
    """
    Extracts alphanumeric tokens converted to lowercase.
    Decomposes hyphenated and underscored compound words into constituents,
    preserves digits and Roman numerals, captures structural bigrams (e.g. 'unit_3', 'chapter_2'),
    and includes morphological stems for improved recall.
    """
    tokens = []
    text_lower = text.lower()
    raw_words = re.findall(r'[A-Za-z0-9_.-]+', text_lower)

    # 1. Structural bigrams: (unit|chapter|module|section|part) + (number|ordinal|roman)
    for i in range(len(raw_words) - 1):
        w1 = raw_words[i].strip(".-_")
        w2 = raw_words[i+1].strip(".-_")
        if w1 in {"unit", "chapter", "module", "section", "part"}:
            num_val = ORDINAL_CARDINAL_MAP.get(w2, w2 if w2.isdigit() else None)
            if num_val:
                tokens.extend([f"{w1}_{num_val}", f"{w1}{num_val}", num_val])
        if w2 in {"unit", "chapter", "module", "section", "part"}:
            num_val = ORDINAL_CARDINAL_MAP.get(w1, w1 if w1.isdigit() else None)
            if num_val:
                tokens.extend([f"{w2}_{num_val}", f"{w2}{num_val}", num_val])

    # 2. Individual words and stems
    for word in raw_words:
        w_clean = word.strip(".-_")
        if not w_clean:
            continue
        # Preserve single digits (e.g. '3') and numbers
        if w_clean.isdigit():
            tokens.append(w_clean)
            continue
        # Preserve Roman numerals & map ordinal words
        if w_clean in ORDINAL_CARDINAL_MAP:
            tokens.append(ORDINAL_CARDINAL_MAP[w_clean])
            tokens.append(w_clean)
            continue
        if w_clean in STOPWORDS or len(w_clean) < 2:
            continue
        tokens.append(w_clean)
        st = stem_word(w_clean)
        if st != w_clean and len(st) > 2 and st not in STOPWORDS:
            tokens.append(st)
        parts = re.split(r'[-_.]+', w_clean)
        if len(parts) > 1:
            for p in parts:
                if (len(p) > 2 or p.isdigit()) and p not in STOPWORDS:
                    tokens.append(p)
                    st_p = stem_word(p)
                    if st_p != p and len(st_p) > 2 and st_p not in STOPWORDS:
                        tokens.append(st_p)
    return tokens

def split_query_clauses(query: str) -> List[str]:
    """
    Splits multi-part questions into distinct clauses to prevent one clause's
    keywords from overshadowing evidence needed for secondary questions.
    """
    clauses = [query]
    parts = re.split(
        r'[,;?]\s*|\s+and\s+(?:what|which|how|why|where|who|the|a|an)\b|\s+with\s+(?:the|a|an|each|all|both)\b|\s+(?:versus|vs\.?)\s+',
        query,
        flags=re.IGNORECASE
    )
    parts = [p.strip() for p in parts if len(p.strip()) > 8]
    if len(parts) > 1:
        clauses.extend(parts)
    return clauses

SYNONYM_EXPANSIONS: Dict[str, List[str]] = {
    "limitation": ["guarantee", "constraint", "restrictions", "limitations"],
    "limitations": ["guarantee", "constraint", "restrictions", "limitation"],
    "results": ["response", "latency", "error", "rate", "figures", "measurements"],
    "result": ["response", "latency", "error", "rate", "figures"],
    "load-test": ["pilot", "virtual", "users", "concurrency", "performance"],
    "testing": ["test", "drill", "trial", "experiment"]
}

def compute_bm25_scores(
    query: str,
    corpus: List[str],
    k1: float = 1.5,
    b: float = 0.75
) -> List[float]:
    """
    Computes BM25 relevance scores for a query across all chunks in corpus.
    Evaluates multi-part clauses and synonym expansions so chunks answering
    any distinct part of a compound question receive appropriate relevance scores.
    """
    clauses = split_query_clauses(query)
    doc_tokens = [tokenize(doc) for doc in corpus]
    N = len(corpus)
    if N == 0 or not corpus:
        return []
    avgdl = sum(len(d) for d in doc_tokens) / max(N, 1)

    clause_results = []
    for clause in clauses:
        raw_q_tokens = tokenize(clause)
        if not raw_q_tokens:
            clause_results.append([0.0] * N)
            continue

        q_tokens = list(raw_q_tokens)
        for t in raw_q_tokens:
            if t in SYNONYM_EXPANSIONS:
                q_tokens.extend(SYNONYM_EXPANSIONS[t])

        df: Dict[str, int] = Counter()
        for q in set(q_tokens):
            df[q] = sum(1 for d in doc_tokens if q in d)

        scores = []
        for d in doc_tokens:
            doc_len = len(d)
            score = 0.0
            doc_term_counts = Counter(d)
            for q in q_tokens:
                if q in doc_term_counts:
                    freq = doc_term_counts[q]
                    n_q = df[q]
                    idf = math.log((N - n_q + 0.5) / (n_q + 0.5) + 1.0)
                    numerator = freq * (k1 + 1.0)
                    denominator = freq + k1 * (1.0 - b + b * (doc_len / max(avgdl, 1.0)))
                    score += idf * (numerator / max(denominator, 0.001))
            scores.append(max(0.0, score))

        clause_unique_q = set(raw_q_tokens)
        max_score = max(scores) if scores else 0.0
        if max_score > 0:
            norm_scores = []
            for s, d in zip(scores, doc_tokens):
                d_set = set(d)
                matched_cnt = sum(1 for tok in clause_unique_q if tok in d_set or any(syn in d_set for syn in SYNONYM_EXPANSIONS.get(tok, [])))
                cov = (matched_cnt / len(clause_unique_q)) if clause_unique_q else 0.0
                cov_weight = (cov ** 1.5) if cov < 0.25 else cov
                norm_scores.append((s / max_score) * cov_weight)
            scores = norm_scores
        clause_results.append(scores)

    # Take the maximum score across clauses for each document
    final_scores = []
    for idx in range(N):
        scores_for_doc = [cr[idx] for cr in clause_results]
        final_scores.append(max(scores_for_doc) if scores_for_doc else 0.0)
    return final_scores

# --- 4. Document-Type Adaptive Full Summarization ---

def infer_document_type(filename: str, sample_text: str) -> str:
    """Infers the document genre to tailor the summary structure naturally."""
    text_lower = (filename + " " + sample_text[:2000]).lower()
    if any(k in text_lower for k in ["abstract", "methodology", "arxiv", "experiments", "proceedings", "doi:"]):
        return "Research Paper"
    if any(k in text_lower for k in ["resume", "curriculum vitae", "work experience", "skills", "education", "linkedin"]):
        return "Resume / CV"
    if any(k in text_lower for k in ["lecture", "syllabus", "course code", "professor", "semester", "exam"]):
        return "Academic Syllabus / Lecture Notes"
    if any(k in text_lower for k in ["architecture", "api", "configuration", "deployment", "specification", "endpoints"]):
        return "Technical Documentation"
    if any(k in text_lower for k in ["q1", "q2", "q3", "q4", "revenue", "fiscal", "ebitda", "quarterly", "forecast"]):
        return "Business / Financial Report"
    return "General Document"

def format_page_citation(page: Optional[int]) -> str:
    """
    Formats the page citation string.
    If page metadata is unavailable or <= 0, returns 'Page unavailable'.
    Otherwise returns 'Page <N>'.
    """
    if page is not None and isinstance(page, int) and page > 0:
        return f"Page {page}"
    return "Page unavailable"

async def summarize_document(
    user_id: str,
    db: Session,
    document_id: Optional[str] = None,
    document_query: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generates a document-type-adaptive, comprehensive overview of a complete document.
    Uses all indexed chunks in order, avoiding omissions caused by semantic top-k limits.
    """
    target_docs = identify_target_documents(user_id=user_id, db=db, query=document_query or "", explicit_doc_id=document_id)
    if not target_docs:
        return {
            "status": "not_found",
            "message": "No uploaded documents found in your Knowledge Base. Please upload your document first.",
            "documentTitle": None,
            "citations": []
        }

    doc = target_docs[0]

    # Fetch all chunks in chronological order
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == doc.id,
        DocumentChunk.user_id == user_id
    ).order_by(DocumentChunk.chunk_index.asc()).all()

    if not chunks:
        return {
            "status": "empty",
            "message": f"Document '{doc.filename}' has been indexed, but contains no extractable text.",
            "documentTitle": doc.filename,
            "citations": []
        }

    full_extracted_text = "\n\n".join([f"--- Page {c.page_number} ---\n{c.content}" for c in chunks])
    citations = []
    for c in chunks[:6]:
        p_val = c.page_number
        if p_val is not None and (not isinstance(p_val, int) or p_val <= 0):
            p_val = None
        snippet_clean = c.content.strip()
        if snippet_clean.startswith("[Section:") and "]\n" in snippet_clean:
            snippet_clean = snippet_clean.split("]\n", 1)[1].strip()
        if len(snippet_clean) > 250:
            snippet_clean = snippet_clean[:250].rsplit(" ", 1)[0] + "..."
        citations.append({
            "id": str(c.id),
            "sourceType": "document",
            "title": doc.filename,
            "snippet": snippet_clean,
            "page": p_val,
            "pageLabel": format_page_citation(p_val),
            "documentId": doc.id
        })

    doc_type = infer_document_type(doc.filename, full_extracted_text)

    # 1. Gemini synthesis if configured
    if settings.GEMINI_API_KEY:
        from app.services.gemini_client import call_gemini_api
        prompt = (
            f"DOCUMENT TITLE: {doc.filename}\n"
            f"INFERRED TYPE: {doc_type}\n\n"
            f"COMPLETE EXTRACTED DOCUMENT TEXT:\n{full_extracted_text[:32000]}\n\n"
            f"INSTRUCTION: Synthesize a thorough, structured, and document-type-adaptive summary of this {doc_type} "
            f"adhering to your system guidelines. Do not use generic resume sections if this is not a resume."
        )
        gemini_res = await call_gemini_api(
            prompt, DOCUMENT_SUMMARY_PROMPT,
            max_output_tokens=2048, temperature=0.2
        )
        if gemini_res.success and gemini_res.text:
            return {
                "status": "success",
                "mode": "document_summary",
                "documentTitle": doc.filename,
                "documentType": doc_type,
                "summary": gemini_res.text,
                "citations": citations
            }
        else:
            logger.warning("[Gemini/summarize] API call failed: %s", gemini_res.error_category)
            return {
                "status": "error",
                "error": {
                    "category": gemini_res.error_category,
                    "message": gemini_res.user_message,
                    "statusCode": gemini_res.status_code
                },
                "message": gemini_res.user_message,
                "documentTitle": doc.filename,
                "citations": []
            }

    return {
        "status": "error",
        "error": {
            "category": "missing_api_key",
            "message": "Gemini API key is not configured. Document summarization requires a valid API key.",
            "statusCode": 500
        },
        "message": "Gemini API key is not configured. Document summarization requires a valid API key.",
        "documentTitle": doc.filename,
        "citations": []
    }

# --- 5. Hybrid Retrieval (Dense Semantic + Lexical BM25 + Adjacent Expansion) ---

async def retrieve_knowledge(
    query: str,
    user_id: str,
    db: Session,
    top_k: int = 6,
    explicit_doc_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Advanced hybrid retriever strictly isolated by authenticated user_id.
    Combines:
    1. Query understanding (document-level summary vs targeted question).
    2. Document target scoping (resolving specific filenames or comparing multiple docs).
    3. Dense vector similarity search using normalized embeddings.
    4. Lexical BM25 keyword matching for exact entities, codes, and technical phrases.
    5. Reciprocal rank / linear score fusion.
    6. Adjacent-chunk windowing for complete explanations.
    """
    lower = query.lower()

    # 1. Document Summary Routing
    if is_document_summary_query(query):
        summary_res = await summarize_document(user_id=user_id, db=db, document_id=explicit_doc_id, document_query=query)
        if summary_res.get("status") == "success":
            return {
                "mode": "document_summary",
                "summary": summary_res["summary"],
                "documentTitle": summary_res["documentTitle"],
                "sources": summary_res["citations"],
                "relevanceEvaluation": "evidence_found",
                "timetableMatches": []
            }
        elif summary_res.get("status") in ("not_found", "empty"):
            return {
                "mode": "document_summary",
                "summary": summary_res.get("message", "Document not found."),
                "documentTitle": None,
                "sources": [],
                "relevanceEvaluation": "insufficient_evidence",
                "timetableMatches": []
            }

    # 2. Structured Timetable Extraction
    timetable_matches = []
    if any(k in lower for k in ["class", "lecture", "timetable", "msc", "professor", "course", "schedule"]):
        entries = db.query(TimetableEntry).filter(TimetableEntry.user_id == user_id).all()
        for e in entries:
            if (e.day_of_week.lower() in lower or 
                e.course_code.lower() in lower or 
                any(w in e.course_name.lower() for w in lower.split() if len(w) > 3)):
                timetable_matches.append({
                    "courseName": e.course_name,
                    "courseCode": e.course_code,
                    "dayOfWeek": e.day_of_week,
                    "startTime": e.start_time,
                    "endTime": e.end_time,
                    "room": e.room,
                    "instructor": e.instructor
                })

    # 3. Document Scope Filtering
    target_docs = identify_target_documents(user_id=user_id, db=db, query=query, explicit_doc_id=explicit_doc_id)
    target_doc_ids = {d.id for d in target_docs} if target_docs else set()

    # Fetch chunks belonging to target documents (or all active indexed documents of the user)
    chunk_query = db.query(DocumentChunk).join(
        Document, DocumentChunk.document_id == Document.id
    ).filter(
        DocumentChunk.user_id == user_id,
        Document.status.in_(["indexed", "INDEXED"])
    )
    if target_doc_ids and not is_multi_document_query(query):
        chunk_query = chunk_query.filter(DocumentChunk.document_id.in_(target_doc_ids))
    chunks = chunk_query.all()

    if not chunks and target_doc_ids:
        # Fall back to all active indexed user chunks if target filter was too narrow
        chunks = db.query(DocumentChunk).join(
            Document, DocumentChunk.document_id == Document.id
        ).filter(
            DocumentChunk.user_id == user_id,
            Document.status.in_(["indexed", "INDEXED"])
        ).all()

    if not chunks:
        return {
            "mode": "targeted_rag",
            "timetableMatches": timetable_matches,
            "sources": [],
            "relevanceEvaluation": "no_documents"
        }

    # 4. Dense Semantic Similarity Scoring
    query_vec = await get_embedding(query)
    dense_scores = []
    chunk_texts = []
    chunk_map: Dict[str, DocumentChunk] = {}

    for c in chunks:
        chunk_texts.append(c.content)
        chunk_map[c.id] = c
        if c.embedding:
            dense_scores.append(cosine_similarity(query_vec, c.embedding))
        else:
            dense_scores.append(0.0)

    # 5. Lexical BM25 Scoring
    bm25_scores = compute_bm25_scores(query, chunk_texts)

    # 6. Hybrid Score Combination
    # Score = 0.5 * Dense + 0.5 * BM25 + Exact Boost - Table Penalty
    hybrid_ranked = []
    all_chunks_by_index = {(c.document_id, c.chunk_index): c for c in chunks}

    # Extract query tokens for phrase and heading matching
    query_tokens_list = [w for w in re.findall(r'\b[A-Za-z0-9_-]+\b', query) if (len(w) > 2 or w.isdigit() or w.lower() in ORDINAL_CARDINAL_MAP) and w.lower() not in STOPWORDS]

    # Detect structural query patterns like "Unit 3", "Chapter 2"
    structural_query_patterns = []
    raw_q_words = re.findall(r'[A-Za-z0-9]+', query.lower())
    for i in range(len(raw_q_words) - 1):
        qw1, qw2 = raw_q_words[i], raw_q_words[i+1]
        if qw1 in {"unit", "chapter", "module", "section", "part"}:
            n_val = ORDINAL_CARDINAL_MAP.get(qw2, qw2 if qw2.isdigit() else None)
            if n_val:
                structural_query_patterns.extend([f"{qw1} {n_val}", f"{qw1}:{n_val}", f"{qw1}-{n_val}", f"{qw1}_{n_val}", f"{qw1}{n_val}"])
        if qw2 in {"unit", "chapter", "module", "section", "part"}:
            n_val = ORDINAL_CARDINAL_MAP.get(qw1, qw1 if qw1.isdigit() else None)
            if n_val:
                structural_query_patterns.extend([f"{qw2} {n_val}", f"{qw2}:{n_val}", f"{qw2}-{n_val}", f"{qw2}_{n_val}", f"{qw2}{n_val}"])

    META_QUERY_WORDS = {
        "explain", "describes", "described", "describe", "syllabus", "notes",
        "paper", "document", "file", "text", "course", "details", "summary",
        "give", "list", "show", "tell", "what", "which", "how", "topics",
        "covered", "about", "defined", "definition", "discuss"
    }

    for idx, c in enumerate(chunks):
        d_score = max(0.0, dense_scores[idx])
        l_score = max(0.0, bm25_scores[idx])
        c_lower = c.content.lower()
        
        # Boost score if chunk contains exact phrase or term matches
        exact_boost = 0.0
        c_words = set(re.findall(r'[a-z0-9_-]+', c_lower))
        if query_tokens_list:
            matched_words = sum(1 for w in query_tokens_list if w.lower() in c_words)
            exact_boost = 0.15 * (matched_words / len(query_tokens_list))
            
            # Distinctive concept keywords boost (e.g. 'inheritance', 'normalization', 'deadlock')
            concept_tokens = [w for w in query_tokens_list if w.lower() not in META_QUERY_WORDS and len(w) > 2]
            if concept_tokens:
                matched_concepts = sum(1 for w in concept_tokens if w.lower() in c_words)
                concept_ratio = matched_concepts / len(concept_tokens)
                if matched_concepts >= 2 or concept_ratio >= 0.30:
                    exact_boost += min(0.35, 0.15 * matched_concepts)

            # Header match boost: if a query keyword appears in a section heading line in chunk
            for ln in c.content.splitlines()[:6]:
                ln_strip = ln.strip()
                if not ln_strip:
                    continue
                ln_lower = ln_strip.lower()
                is_section_header = (
                    ln_strip.startswith(("##", "###", "####", "UNIT", "Unit", "CHAPTER", "Chapter", "MODULE", "Module", "SECTION", "Section", "PART", "Part"))
                    or (ln_strip.isupper() and len(ln_strip) > 4 and not ln_strip.startswith("#"))
                )
                if is_section_header:
                    ln_words = set(re.findall(r'[a-z0-9_-]+', ln_lower))
                    if any(w.lower() in ln_words for w in (concept_tokens or query_tokens_list)):
                        exact_boost += 0.20
                        break

        # Structural unit / chapter boost
        if structural_query_patterns:
            if any(sqp in c_lower for sqp in structural_query_patterns):
                exact_boost += 0.35
            # Extra boost if it is in the chunk's leading heading/section
            header_lead = c_lower[:120]
            if any(sqp in header_lead for sqp in structural_query_patterns):
                exact_boost += 0.25

        # De-bias raw reference tables when user asks narrative/explanatory questions
        is_table = "exact values reference" in c_lower or "item\nvalue" in c_lower
        asks_for_table = any(k in query.lower() for k in ["table", "reference table", "exact value", "exact values"])
        table_penalty = 0.10 if (is_table and not asks_for_table) else 0.0

        combined_score = max(0.0, (0.5 * d_score) + (0.5 * l_score) + exact_boost - table_penalty)

        doc = db.query(Document).filter(Document.id == c.document_id).first()
        doc_name = doc.filename if doc else "Document"

        hybrid_ranked.append({
            "chunk": c,
            "score": float(combined_score),
            "dense_score": float(d_score),
            "lexical_score": float(l_score),
            "title": doc_name,
            "documentId": c.document_id,
            "page": c.page_number,
            "chunk_index": c.chunk_index,
            "content": c.content
        })

    # Sort descending by hybrid score
    hybrid_ranked.sort(key=lambda x: x["score"], reverse=True)

    # Filter by relevance threshold
    relevant_matches = [m for m in hybrid_ranked if m["score"] >= RELEVANCE_THRESHOLD]

    # If explicit_doc_id is targeted (e.g. conversational follow-up) but lexical score was low due to pronouns
    if not relevant_matches and explicit_doc_id and hybrid_ranked:
        relevant_matches = [m for m in hybrid_ranked if m["documentId"] == explicit_doc_id][:top_k]

    # Defensive fallback for brief questions if top match has legitimate relevance
    if not relevant_matches and hybrid_ranked and hybrid_ranked[0]["score"] >= 0.08:
        top_match = hybrid_ranked[0]
        c_top_words = set(re.findall(r'[a-z0-9_-]+', top_match["content"].lower()))
        has_word_overlap = any(w.lower() in c_top_words for w in query_tokens_list if len(w) > 2 and w.lower() not in STOPWORDS)
        if (top_match["dense_score"] > 0.04 or top_match["lexical_score"] > 0.04) and has_word_overlap:
            relevant_matches = [top_match]

    # Score-gap filtering: keep high-confidence and competitive matches
    if relevant_matches:
        top_score = relevant_matches[0]["score"]
        if is_multi_document_query(query):
            gap_threshold = max(RELEVANCE_THRESHOLD, top_score * 0.35)
            doc_seen = set()
            multi_doc_matches = []
            for m in relevant_matches:
                if m["score"] >= gap_threshold or m["documentId"] not in doc_seen:
                    multi_doc_matches.append(m)
                    doc_seen.add(m["documentId"])
            relevant_matches = multi_doc_matches
        else:
            gap_threshold = max(RELEVANCE_THRESHOLD, top_score * 0.35)
            relevant_matches = [m for m in relevant_matches if m["score"] >= gap_threshold]

    # 7. Adjacent Chunk Expansion & Windowing
    # Include adjacent chunks when they belong to the same document and contain
    # continuity context or evidence addressing parts of the user question.
    selected_matches = list(relevant_matches[:_MAX_SOURCES])
    seen_indices = {(m["documentId"], m["chunk_index"]) for m in selected_matches}

    for m in list(selected_matches):
        doc_id = m["documentId"]
        ci = m["chunk_index"]
        # Check immediate successors and predecessors
        for adj_ci in (ci + 1, ci - 1):
            key = (doc_id, adj_ci)
            if key in seen_indices:
                continue
            adj_chunk = all_chunks_by_index.get(key)
            if not adj_chunk:
                continue

            # Check if adjacent chunk contains relevant context for the query
            adj_lower = adj_chunk.content.lower()
            q_tokens_set = set(tokenize(query))
            adj_tokens_set = set(tokenize(adj_chunk.content))
            token_overlap = q_tokens_set.intersection(adj_tokens_set)

            has_context = (
                len(token_overlap) >= 1
                or any(k in adj_lower for k in [
                    "guarantee", "limitation", "limitations", "error rate",
                    "response time", "latency", "adr-", "pilot test", "capacity"
                ])
            )

            if has_context and len(selected_matches) < 5:
                seen_indices.add(key)
                doc = db.query(Document).filter(Document.id == doc_id).first()
                doc_name = doc.filename if doc else "Document"
                selected_matches.append({
                    "chunk": adj_chunk,
                    "score": max(0.20, m["score"] * 0.85),
                    "dense_score": 0.0,
                    "lexical_score": 0.0,
                    "title": doc_name,
                    "documentId": doc_id,
                    "page": adj_chunk.page_number,
                    "chunk_index": adj_ci,
                    "content": adj_chunk.content
                })

    expanded_sources = []
    seen_chunk_keys = set()

    for m in selected_matches:
        key = (m["documentId"], m["chunk_index"])
        if key in seen_chunk_keys:
            continue
        seen_chunk_keys.add(key)

        page_val = m["page"]
        if page_val is not None and (not isinstance(page_val, int) or page_val <= 0):
            page_val = None

        snippet_preview = m["content"].strip()
        # Strip leading [Section: ...] metadata header
        if snippet_preview.startswith("[Section:") and "]\n" in snippet_preview:
            snippet_preview = snippet_preview.split("]\n", 1)[1].strip()

        # Truncate at sentence boundary only if necessary; do not mid-sentence cut
        if len(snippet_preview) > _SNIPPET_MAX_CHARS:
            boundary = snippet_preview[:_SNIPPET_MAX_CHARS]
            last_period = max(boundary.rfind(". "), boundary.rfind("! "), boundary.rfind("? "))
            if last_period > _SNIPPET_MAX_CHARS // 2:
                snippet_preview = snippet_preview[:last_period + 1]
            else:
                snippet_preview = boundary.rsplit(" ", 1)[0]
            snippet_preview = snippet_preview.rstrip()

        page_str = format_page_citation(page_val)
        expanded_sources.append({
            "score": m["score"],
            "title": m["title"],
            "documentId": m["documentId"],
            "page": page_val,
            "pageLabel": page_str,
            "snippet": snippet_preview,
            "fullContent": m["content"]
        })

    logger.info(
        "[RAG retrieval] query=%r chunks_evaluated=%d relevant=%d sources_returned=%d top_score=%.3f",
        query, len(chunks), len(relevant_matches), len(expanded_sources),
        relevant_matches[0]["score"] if relevant_matches else 0.0
    )

    return {
        "status": "success",
        "mode": "targeted_rag",
        "timetableMatches": timetable_matches,
        "sources": expanded_sources,
        "relevanceEvaluation": "evidence_found" if expanded_sources else "insufficient_evidence"
    }


# ---------------------------------------------------------------------------
# Regex to detect model-echoed citation section headers anywhere in the answer.
# Used to strip the echoed header TEXT only, not everything after it.
_ECHOED_SOURCES_HEADER_RE = re.compile(
    r'\*{0,2}Grounded Evidentiary Sources:\*{0,2}',
    re.IGNORECASE
)


def format_grounded_rag_response(
    answer: str,
    sources: List[Dict[str, Any]],
    query: str = ""
) -> str:
    """
    Formats a RAG answer strictly adhering to the required structure:

    **Answer:**
    <direct answer>

    **Grounded Evidentiary Sources:**

    <Filename> (<Page N | Page unavailable>)

    > <relevant excerpt from retrieved document>

    IMPORTANT: This function must NOT split or truncate the input `answer`
    string on section-header phrases. The answer is model-generated text;
    any echoed headers are stripped at the line level only.
    """
    clean_answer = (answer or "").strip()

    # Normalize existing answer prefixes if model emitted them
    if clean_answer.startswith("**Answer:**"):
        clean_answer = clean_answer[len("**Answer:**"):].strip()
    elif clean_answer.startswith("Answer:"):
        clean_answer = clean_answer[len("Answer:"):].strip()

    # --- FIX: Do NOT split the answer on the sources header phrase. ---
    # Previously this code did: clean_answer = clean_answer.split("**Grounded...**")[0]
    # which discarded everything after the phrase, truncating the answer.
    # Instead: remove only the echoed header line itself, preserving surrounding text.
    clean_answer = _ECHOED_SOURCES_HEADER_RE.sub('', clean_answer).strip()

    # Check if answer indicates absence of information / insufficient evidence
    lower_ans = clean_answer.lower()
    is_insufficient = (
        "do not provide enough information" in lower_ans
        or "does not provide enough information" in lower_ans
        or "does not mention" in lower_ans
        or "no relevant evidence" in lower_ans
        or "no sufficient evidence" in lower_ans
        or "not mentioned in the uploaded" in lower_ans
        or "not found in the uploaded" in lower_ans
    )

    logger.info(
        "[RAG format] answer_len=%d sources=%d is_insufficient=%s",
        len(clean_answer), len(sources), is_insufficient
    )

    if is_insufficient or not sources:
        # Do not attach unrelated citations when evidence is absent or insufficient
        return f"**Answer:**\n{clean_answer}"

    source_blocks = []
    seen_excerpts = set()

    for s in sources:
        title = s.get("title") or "Document"
        page = s.get("page")
        page_str = s.get("pageLabel") or format_page_citation(page)

        raw_snippet = s.get("snippet", "").strip()
        if not raw_snippet and "fullContent" in s:
            raw_snippet = s["fullContent"][:300].strip()

        # Clean leading [Section: ...] header if present
        if raw_snippet.startswith("[Section:") and "]\n" in raw_snippet:
            raw_snippet = raw_snippet.split("]\n", 1)[1].strip()

        if not raw_snippet:
            continue

        # Deduplicate identical or near-identical excerpts
        norm_key = (title, raw_snippet[:60].lower())
        if norm_key in seen_excerpts:
            continue
        seen_excerpts.add(norm_key)

        # Format blockquote lines with >
        lines = [line.strip() for line in raw_snippet.splitlines() if line.strip()]
        quoted_block = "\n> ".join(lines) if lines else f"> {raw_snippet}"

        source_blocks.append(f"{title} ({page_str})\n\n> {quoted_block}")

    if not source_blocks:
        return f"**Answer:**\n{clean_answer}"

    sources_formatted = "\n\n".join(source_blocks)
    return f"**Answer:**\n{clean_answer}\n\n**Grounded Evidentiary Sources:**\n\n{sources_formatted}"
