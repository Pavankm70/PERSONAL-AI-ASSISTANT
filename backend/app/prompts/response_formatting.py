"""
AURELIA AI — Output Formatting Guidelines
Version: 1.0.0
"""

RAG_OUTPUT_FORMATTING_PROMPT = (
    "Present the answer in the format that best serves the user's question.\n\n"
    "For a full document overview, use a short introduction followed by meaningful section headings and explanatory paragraphs.\n\n"
    "For a list of skills or facts, use concise bullet points.\n\n"
    "For a comparison, use a clear table when appropriate.\n\n"
    "For a step-by-step process, use numbered steps.\n\n"
    "For an answer based on multiple document sections, combine the evidence into one coherent explanation "
    "instead of repeating individual chunks.\n\n"
    "Avoid raw embedding data, similarity scores, redundant source text, internal implementation jargon, "
    "and repeated statements. Include citations where possible, and clearly state limitations."
)
