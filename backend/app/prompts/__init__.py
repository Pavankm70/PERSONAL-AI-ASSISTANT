from app.prompts.base import PROMPT_VERSION, SHARED_SYSTEM_CONSTRAINTS, SHARED_OUTPUT_RULES
from app.prompts.assistant import AURELIA_SYSTEM_PROMPT
from app.prompts.document_summary import DOCUMENT_SUMMARY_PROMPT
from app.prompts.rag import SPECIFIC_RAG_PROMPT
from app.prompts.response_formatting import RAG_OUTPUT_FORMATTING_PROMPT
from app.prompts.routing import INTENT_ROUTING_PROMPT
from app.prompts.calendar import (
    CALENDAR_DATE_RESOLUTION_PROMPT,
    CALENDAR_EVENT_CREATION_PROMPT,
    CALENDAR_AVAILABILITY_PROMPT,
    CALENDAR_MUTATION_PROMPT
)
from app.prompts.gmail import (
    GMAIL_SEARCH_PROMPT,
    GMAIL_SUMMARY_PROMPT,
    GMAIL_DRAFT_PROMPT,
    GMAIL_SENDING_PROMPT
)
from app.prompts.drive import DRIVE_SEARCH_PROMPT, DRIVE_READING_PROMPT
from app.prompts.web_search import WEB_SEARCH_PROMPT
from app.prompts.weather import WEATHER_PROMPT
from app.prompts.study_planner import STUDY_PLANNER_PROMPT
from app.prompts.memory import CONVERSATION_MEMORY_PROMPT
from app.prompts.general import GENERAL_QA_PROMPT, TOOL_ERROR_PROMPT
from app.prompts.registry import PROMPT_REGISTRY, get_tool_prompt_entry, ToolPromptEntry

__all__ = [
    "PROMPT_VERSION",
    "SHARED_SYSTEM_CONSTRAINTS",
    "SHARED_OUTPUT_RULES",
    "AURELIA_SYSTEM_PROMPT",
    "DOCUMENT_SUMMARY_PROMPT",
    "SPECIFIC_RAG_PROMPT",
    "RAG_OUTPUT_FORMATTING_PROMPT",
    "INTENT_ROUTING_PROMPT",
    "CALENDAR_DATE_RESOLUTION_PROMPT",
    "CALENDAR_EVENT_CREATION_PROMPT",
    "CALENDAR_AVAILABILITY_PROMPT",
    "CALENDAR_MUTATION_PROMPT",
    "GMAIL_SEARCH_PROMPT",
    "GMAIL_SUMMARY_PROMPT",
    "GMAIL_DRAFT_PROMPT",
    "GMAIL_SENDING_PROMPT",
    "DRIVE_SEARCH_PROMPT",
    "DRIVE_READING_PROMPT",
    "WEB_SEARCH_PROMPT",
    "WEATHER_PROMPT",
    "STUDY_PLANNER_PROMPT",
    "CONVERSATION_MEMORY_PROMPT",
    "GENERAL_QA_PROMPT",
    "TOOL_ERROR_PROMPT",
    "PROMPT_REGISTRY",
    "get_tool_prompt_entry",
    "ToolPromptEntry"
]
