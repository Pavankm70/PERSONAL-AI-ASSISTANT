import math
import hashlib
from typing import List, Optional
import numpy as np
import httpx
from app.core.config import settings

VECTOR_DIM = 256

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

NUMBER_WORD_MAP = {
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

def compute_local_embedding(text: str, dim: int = VECTOR_DIM) -> List[float]:
    """
    Enhanced deterministic subword & token feature hashing embedding.
    Applies stopword dampening, structural phrase hashing (e.g. Unit 3, Chapter 2),
    and subword n-gram weight boost.
    Used for local testing, development, and fallback without external API costs.
    """
    if not text:
        return [0.0] * dim

    vec = np.zeros(dim, dtype=np.float32)
    raw_words = text.lower().replace("\n", " ").split()
    all_tokens = []

    # Detect structural compounds (e.g. "Unit 3", "Chapter 2")
    for i in range(len(raw_words) - 1):
        w1 = "".join(c for c in raw_words[i] if c.isalnum())
        w2 = "".join(c for c in raw_words[i+1] if c.isalnum())
        if w1 in {"unit", "chapter", "module", "section", "part"}:
            num_val = NUMBER_WORD_MAP.get(w2, w2 if w2.isdigit() else None)
            if num_val:
                all_tokens.extend([f"{w1}_{num_val}", f"{w1}{num_val}", num_val])
        if w2 in {"unit", "chapter", "module", "section", "part"}:
            num_val = NUMBER_WORD_MAP.get(w1, w1 if w1.isdigit() else None)
            if num_val:
                all_tokens.extend([f"{w2}_{num_val}", f"{w2}{num_val}", num_val])

    for word in raw_words:
        clean_word = "".join(c for c in word if c.isalnum() or c in "-_")
        if clean_word:
            all_tokens.append(clean_word)
            if clean_word in NUMBER_WORD_MAP:
                all_tokens.append(NUMBER_WORD_MAP[clean_word])
            if "-" in clean_word or "_" in clean_word:
                for part in clean_word.replace("_", "-").split("-"):
                    if len(part) > 1 and part not in STOPWORDS:
                        all_tokens.append(part)

    for clean_word in all_tokens:
        is_num = clean_word.isdigit() or clean_word in NUMBER_WORD_MAP.values()
        is_structural = any(clean_word.startswith(prefix) for prefix in ["unit_", "chapter_", "module_", "section_", "part_"])
        
        weight = 0.15 if (clean_word in STOPWORDS and not is_num) else (1.5 if (is_structural or is_num) else 1.0)

        # Primary word hash
        h = int(hashlib.md5(clean_word.encode('utf-8')).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[idx] += sign * weight

        # Secondary hash for rare words or technical terms
        if len(clean_word) > 2 or is_num or is_structural:
            h2 = int(hashlib.sha1(clean_word.encode('utf-8')).hexdigest(), 16)
            idx2 = (h2 + 13) % dim
            sign2 = 1.0 if (h2 // dim) % 2 == 0 else -1.0
            vec[idx2] += sign2 * weight * 0.7

    # Character 3-grams for typo resilience and morphology
    clean_text = text.lower()
    for i in range(len(clean_text) - 2):
        gram = clean_text[i:i+3]
        if " " not in gram:
            h = int(hashlib.sha256(gram.encode('utf-8')).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if (h // dim) % 2 == 0 else -1.0
            vec[idx] += sign * 0.25

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()

async def get_embedding(text: str) -> List[float]:
    """
    Retrieves vector embedding using configured Gemini embedding API if key is present,
    otherwise uses the fast local embedding engine.
    """
    if settings.GEMINI_API_KEY and settings.EMBEDDING_PROVIDER == "gemini":
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.EMBEDDING_MODEL}:embedContent?key={settings.GEMINI_API_KEY}"
            payload = {
                "model": f"models/{settings.EMBEDDING_MODEL}",
                "content": {"parts": [{"text": text[:2000]}]}
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    values = data.get("embedding", {}).get("values", [])
                    if values:
                        return values
        except Exception:
            pass # fallback to local

    return compute_local_embedding(text)

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """
    Computes cosine similarity between two vectors.
    Safely handles dimensionality mismatches (e.g. 256 vs 768) without throwing exceptions.
    """
    if not v1 or not v2:
        return 0.0

    len1, len2 = len(v1), len(v2)
    if len1 != len2:
        # Align dimensions to the minimum common length
        min_len = min(len1, len2)
        a = np.array(v1[:min_len], dtype=np.float32)
        b = np.array(v2[:min_len], dtype=np.float32)
    else:
        a = np.array(v1, dtype=np.float32)
        b = np.array(v2, dtype=np.float32)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0

    dot = np.dot(a, b)
    score = float(dot / (norm_a * norm_b))
    return max(-1.0, min(1.0, score))
