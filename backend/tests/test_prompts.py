import pytest
from app.prompts import (
    PROMPT_VERSION,
    AURELIA_SYSTEM_PROMPT,
    INTENT_ROUTING_PROMPT,
    SPECIFIC_RAG_PROMPT,
    DOCUMENT_SUMMARY_PROMPT,
    RAG_OUTPUT_FORMATTING_PROMPT,
    CALENDAR_DATE_RESOLUTION_PROMPT,
    CALENDAR_EVENT_CREATION_PROMPT,
    CALENDAR_AVAILABILITY_PROMPT,
    CALENDAR_MUTATION_PROMPT,
    GMAIL_SEARCH_PROMPT,
    GMAIL_SUMMARY_PROMPT,
    GMAIL_DRAFT_PROMPT,
    GMAIL_SENDING_PROMPT,
    DRIVE_SEARCH_PROMPT,
    DRIVE_READING_PROMPT,
    WEB_SEARCH_PROMPT,
    WEATHER_PROMPT,
    STUDY_PLANNER_PROMPT,
    CONVERSATION_MEMORY_PROMPT,
    GENERAL_QA_PROMPT,
    TOOL_ERROR_PROMPT,
    PROMPT_REGISTRY,
    get_tool_prompt_entry
)

def test_prompt_library_integrity():
    prompts = [
        AURELIA_SYSTEM_PROMPT,
        INTENT_ROUTING_PROMPT,
        SPECIFIC_RAG_PROMPT,
        DOCUMENT_SUMMARY_PROMPT,
        RAG_OUTPUT_FORMATTING_PROMPT,
        CALENDAR_DATE_RESOLUTION_PROMPT,
        CALENDAR_EVENT_CREATION_PROMPT,
        CALENDAR_AVAILABILITY_PROMPT,
        CALENDAR_MUTATION_PROMPT,
        GMAIL_SEARCH_PROMPT,
        GMAIL_SUMMARY_PROMPT,
        GMAIL_DRAFT_PROMPT,
        GMAIL_SENDING_PROMPT,
        DRIVE_SEARCH_PROMPT,
        DRIVE_READING_PROMPT,
        WEB_SEARCH_PROMPT,
        WEATHER_PROMPT,
        STUDY_PLANNER_PROMPT,
        CONVERSATION_MEMORY_PROMPT,
        GENERAL_QA_PROMPT,
        TOOL_ERROR_PROMPT
    ]
    for p in prompts:
        assert isinstance(p, str)
        assert len(p.strip()) > 50

def test_prompt_registry_completeness():
    required_tools = [
        "intent_router",
        "rag_knowledge_lookup",
        "document_summary",
        "calendar_propose_event",
        "calendar_events_retrieval",
        "calendar_delete_event",
        "gmail_priority_messages",
        "gmail_create_draft",
        "drive_search_files",
        "web_search_intelligence",
        "weather_lookup",
        "study_planner"
    ]
    for tool_name in required_tools:
        assert tool_name in PROMPT_REGISTRY
        entry = PROMPT_REGISTRY[tool_name]
        assert entry.purpose != ""
        assert entry.system_prompt != ""
        assert isinstance(entry.input_schema, dict)
        assert isinstance(entry.output_schema, dict)
        assert entry.backend_handler != ""
        assert entry.failure_behavior != ""

def test_prompt_registry_fallback():
    entry = get_tool_prompt_entry("non_existent_tool_xyz")
    assert entry.tool_name == "general_qa"
    assert entry.system_prompt == GENERAL_QA_PROMPT
