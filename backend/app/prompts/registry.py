"""
AURELIA AI — Central Prompt and Tool Contract Registry
Maps every AI tool and workflow to its purpose, system prompt, input schema,
backend handler, output schema, failure behavior, and test cases.
Version: 1.0.0
"""
from typing import Dict, Any, List
from dataclasses import dataclass, field

from app.prompts.assistant import AURELIA_SYSTEM_PROMPT
from app.prompts.document_summary import DOCUMENT_SUMMARY_PROMPT
from app.prompts.rag import SPECIFIC_RAG_PROMPT
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

@dataclass
class ToolPromptEntry:
    tool_name: str
    purpose: str
    system_prompt: str
    input_schema: Dict[str, Any]
    backend_handler: str
    output_schema: Dict[str, Any]
    failure_behavior: str
    test_cases: List[str] = field(default_factory=list)

PROMPT_REGISTRY: Dict[str, ToolPromptEntry] = {
    "intent_router": ToolPromptEntry(
        tool_name="intent_router",
        purpose="Classifies query intent and extracts typed parameters into validated tool schemas.",
        system_prompt=INTENT_ROUTING_PROMPT,
        input_schema={"query": "str", "conversation_history": "Optional[List[Dict]]"},
        backend_handler="app.agent.graph.classify_intent",
        output_schema={"tool": "str", "args": "Dict[str, Any]", "confidence": "float"},
        failure_behavior="Falls back to deterministic rule-based/heuristic classifier without throwing.",
        test_cases=["classify_weather_intent", "classify_email_draft_intent", "classify_doc_summary_intent"]
    ),
    "rag_knowledge_lookup": ToolPromptEntry(
        tool_name="rag_knowledge_lookup",
        purpose="Retrieves evidence from user's indexed documents for specific targeted questions.",
        system_prompt=SPECIFIC_RAG_PROMPT,
        input_schema={"query": "str", "user_id": "str", "top_k": "int"},
        backend_handler="app.rag.retrieval.retrieve_knowledge",
        output_schema={"sources": "List[Dict]", "timetableMatches": "List[Dict]"},
        failure_behavior="Returns empty sources list with honest lack of evidence explanation.",
        test_cases=["test_retrieval_relevance_threshold_filters_noise", "test_rag_citation_extraction"]
    ),
    "document_summary": ToolPromptEntry(
        tool_name="document_summary",
        purpose="Generates complete, structured overviews of entire documents or resumes.",
        system_prompt=DOCUMENT_SUMMARY_PROMPT,
        input_schema={"document_id": "Optional[str]", "document_name": "Optional[str]", "user_id": "str"},
        backend_handler="app.rag.retrieval.summarize_document",
        output_schema={"summary": "str", "documentTitle": "str", "pageCount": "int", "sections": "List[str]"},
        failure_behavior="Informs user that document could not be read or has no extractable text.",
        test_cases=["test_resume_document_summary", "test_missing_doc_handling"]
    ),
    "calendar_propose_event": ToolPromptEntry(
        tool_name="calendar_propose_event",
        purpose="Normalizes natural language dates, checks conflicts, and returns a confirmation proposal.",
        system_prompt=CALENDAR_DATE_RESOLUTION_PROMPT,
        input_schema={"query": "str", "title": "Optional[str]", "timezone": "Optional[str]"},
        backend_handler="app.services.google_services.calendar_service.prepare_event_proposal",
        output_schema={"previewEvent": "Dict", "confirmationToken": "str", "hasConflict": "bool"},
        failure_behavior="Returns error details if natural date cannot be resolved or calendar service fails.",
        test_cases=["test_calendar_preview_generates_token", "test_natural_language_tomorrow_parsing"]
    ),
    "calendar_events_retrieval": ToolPromptEntry(
        tool_name="calendar_events_retrieval",
        purpose="Lists actual events from Google Calendar within a requested date window.",
        system_prompt=CALENDAR_AVAILABILITY_PROMPT,
        input_schema={"user_id": "str", "time_min": "Optional[str]", "time_max": "Optional[str]"},
        backend_handler="app.services.google_services.calendar_service.list_events",
        output_schema={"events": "List[Dict]", "timeZone": "str", "isLive": "bool"},
        failure_behavior="Returns clear disconnected notice if user hasn't authorized Google Calendar.",
        test_cases=["test_calendar_events_listing", "test_unconnected_calendar_status"]
    ),
    "calendar_delete_event": ToolPromptEntry(
        tool_name="calendar_delete_event",
        purpose="Deletes an existing Google Calendar event with explicit authentication.",
        system_prompt=CALENDAR_MUTATION_PROMPT,
        input_schema={"event_id": "str", "user_id": "str"},
        backend_handler="app.services.google_services.calendar_service.delete_event",
        output_schema={"status": "str", "event_id": "str"},
        failure_behavior="Returns HTTP 400 or disconnected status without claiming success.",
        test_cases=["test_delete_calendar_event_endpoint_mock_mode"]
    ),
    "gmail_priority_messages": ToolPromptEntry(
        tool_name="gmail_priority_messages",
        purpose="Searches and fetches real Gmail messages matching query criteria.",
        system_prompt=GMAIL_SEARCH_PROMPT,
        input_schema={"user_id": "str", "query": "str", "max_results": "int"},
        backend_handler="app.services.google_services.gmail_service.list_messages",
        output_schema={"messages": "List[Dict]", "isLive": "bool"},
        failure_behavior="Returns disconnected notice or empty results without inventing emails.",
        test_cases=["test_gmail_message_search", "test_unconnected_gmail_status"]
    ),
    "gmail_create_draft": ToolPromptEntry(
        tool_name="gmail_create_draft",
        purpose="Generates a validated email draft with recipient, subject, and body.",
        system_prompt=GMAIL_DRAFT_PROMPT,
        input_schema={"to": "str", "subject": "str", "body": "str"},
        backend_handler="app.services.google_services.gmail_service.create_draft",
        output_schema={"draftId": "str", "to": "str", "subject": "str", "body": "str"},
        failure_behavior="Returns validation error if recipient address is invalid.",
        test_cases=["test_gmail_draft_dynamic_parameters"]
    ),
    "drive_search_files": ToolPromptEntry(
        tool_name="drive_search_files",
        purpose="Searches Google Drive files accessible to the authenticated user.",
        system_prompt=DRIVE_SEARCH_PROMPT,
        input_schema={"user_id": "str", "query": "str"},
        backend_handler="app.services.google_services.drive_service.search_files",
        output_schema={"files": "List[Dict]", "isLive": "bool"},
        failure_behavior="Returns disconnected message without returning fabricated files.",
        test_cases=["test_drive_search_live_or_disconnected"]
    ),
    "web_search_intelligence": ToolPromptEntry(
        tool_name="web_search_intelligence",
        purpose="Performs live internet search using Tavily API.",
        system_prompt=WEB_SEARCH_PROMPT,
        input_schema={"query": "str", "max_results": "int"},
        backend_handler="app.services.web_search_service.search",
        output_schema={"status": "str", "results": "List[Dict]", "query": "str"},
        failure_behavior="Returns structured unconfigured error if WEB_SEARCH_API_KEY is missing.",
        test_cases=["test_web_search_unconfigured_status"]
    ),
    "weather_lookup": ToolPromptEntry(
        tool_name="weather_lookup",
        purpose="Retrieves live meteorological forecast telemetry via Open-Meteo.",
        system_prompt=WEATHER_PROMPT,
        input_schema={"city": "str"},
        backend_handler="app.services.weather_service.get_weather",
        output_schema={"temperatureC": "float", "condition": "str", "location": "str"},
        failure_behavior="Returns structured error if geocoding fails.",
        test_cases=["test_weather_service_clean_fallback"]
    ),
    "study_planner": ToolPromptEntry(
        tool_name="study_planner",
        purpose="Allocates conflict-checked smart study slots based on plan tasks and calendar.",
        system_prompt=STUDY_PLANNER_PROMPT,
        input_schema={"plan_id": "str", "user_id": "str"},
        backend_handler="app.api.routes.plans.propose_study_slots",
        output_schema={"proposedStudyBlocks": "List[Dict]", "calendarConnected": "bool"},
        failure_behavior="Estimates slots without calendar verification if calendar is unlinked.",
        test_cases=["test_smart_study_slots_proposal_and_application"]
    )
}

def get_tool_prompt_entry(tool_name: str) -> ToolPromptEntry:
    return PROMPT_REGISTRY.get(tool_name, ToolPromptEntry(
        tool_name="general_qa",
        purpose="General conversational AI responses.",
        system_prompt=GENERAL_QA_PROMPT,
        input_schema={"query": "str"},
        backend_handler="app.agent.graph.call_gemini_api",
        output_schema={"content": "str"},
        failure_behavior="Returns safe model reply or polite offline message."
    ))
