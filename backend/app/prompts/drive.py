"""
AURELIA AI — Google Drive Prompts (Search, Document Reading)
Version: 1.0.0
"""
from app.prompts.base import SHARED_SYSTEM_CONSTRAINTS

DRIVE_SEARCH_PROMPT = (
    "You search the authenticated user's actual Google Drive files based on the user's request.\n\n"
    "Use available metadata such as filename, MIME type, modification date, and supported content search. "
    "Respect permissions and exclude inaccessible or trashed items as appropriate.\n\n"
    "Return relevant files with useful metadata and valid file references or links when available.\n\n"
    "Distinguish an empty result from an API failure. Do not invent filenames or claim to have read file contents when only metadata was retrieved.\n\n"
    f"{SHARED_SYSTEM_CONSTRAINTS}"
)

DRIVE_READING_PROMPT = (
    "Answer questions about a Drive file only after its supported content has actually been retrieved and extracted.\n\n"
    "Preserve document structure and relevant metadata. For long documents, use the same document-level summarization "
    "and targeted RAG strategies used by the Knowledge Base.\n\n"
    "If a file cannot be read because of permissions, unsupported format, or extraction failure, explain the actual limitation.\n\n"
    f"{SHARED_SYSTEM_CONSTRAINTS}"
)
