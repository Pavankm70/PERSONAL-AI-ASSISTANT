import uuid
import re
import json
import zoneinfo
from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
import httpx

from app.core.config import settings
from app.db.models import User, Message, ToolExecutionLog, Conversation, Plan, PlanTask, Timetable, TimetablePeriod, TimetableEntry, AcademicEvent
from app.agent.tool_registry import tool_registry, parse_period_query_details
from app.services.date_parser import (
    parse_natural_datetime,
    parse_natural_time_intervals,
    parse_leave_request,
    parse_explicit_calendar_date,
    get_user_tz,
    get_user_current_date,
    get_user_today_bounds,
    get_user_week_bounds,
    get_user_month_bounds
)
from app.services.google_services.gmail_service import google_gmail_service
from app.services.google_services.calendar_service import google_calendar_service
from app.services.capabilities import is_capability_enabled
from app.rag.retrieval import (
    is_document_summary_query,
    summarize_document,
    retrieve_knowledge,
    format_grounded_rag_response,
    format_page_citation
)

from app.prompts import (
    PROMPT_VERSION,
    AURELIA_SYSTEM_PROMPT,
    INTENT_ROUTING_PROMPT,
    SPECIFIC_RAG_PROMPT,
    DOCUMENT_SUMMARY_PROMPT,
    CALENDAR_DATE_RESOLUTION_PROMPT,
    GMAIL_DRAFT_PROMPT,
    WEB_SEARCH_PROMPT,
    WEATHER_PROMPT,
    STUDY_PLANNER_PROMPT,
    GENERAL_QA_PROMPT
)

from app.services.gemini_client import call_gemini_api, GeminiCallResult
from app.services.study_plan_generator import (
    generate_study_plan_roadmap,
    calculate_plan_dates,
    parse_plan_duration
)

async def classify_intent_with_gemini(query: str, history_context: str = "", user_tz: str = "UTC") -> Optional[Dict[str, Any]]:
    """
    Uses Gemini to classify user intent and extract structured tool arguments.
    Injects user runtime timezone and local datetime so Gemini resolves dates like 'today' accurately.
    """
    if not settings.GEMINI_API_KEY:
        return None

    try:
        tz = zoneinfo.ZoneInfo(user_tz)
    except Exception:
        tz = timezone.utc
    now_local = datetime.now(tz)

    routing_instructions = (
        f"{INTENT_ROUTING_PROMPT}\n\n"
        f"Current Runtime Context:\n"
        f"- User Timezone: {user_tz}\n"
        f"- Current Local Date/Time: {now_local.strftime('%Y-%m-%d %H:%M (%A)')}\n\n"
        "Return ONLY a valid JSON object with 'tool' and 'args' fields without markdown fencing."
    )

    prompt = f"{history_context}User Query: {query}\nJSON Response:"
    gemini_res = await call_gemini_api(prompt, routing_instructions)
    if not gemini_res.success or not gemini_res.text:
        return None
    resp = gemini_res.text

    try:
        clean_json = resp.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        if clean_json.startswith("```"):
            clean_json = clean_json[3:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
        clean_json = clean_json.strip()
        parsed = json.loads(clean_json)
        if "tool" in parsed and "args" in parsed:
            return parsed
    except Exception:
        pass
    return None

def preserve_acronym_title(text: str) -> str:
    """Preserves academic acronyms like DL, ML, AI, DSA, OS while title-casing other words."""
    words = text.split()
    out = []
    for w in words:
        if len(w) <= 3 and w.isupper():
            out.append(w)
        elif w.upper() in ["DL", "ML", "AI", "DSA", "OS", "DB", "OOP", "CS"]:
            out.append(w.upper())
        else:
            out.append(w.capitalize())
    return " ".join(out)

def extract_calendar_event_title(query: str) -> str:
    """
    Deterministically extracts the event title from natural language scheduling queries.
    Handles 'Today I have quiz at 10 PM deep learning so mark in Google Calendar as event',
    'Add DL quiz to my calendar today at 10 PM', 'Schedule team sync tomorrow at 3 PM', etc.
    """
    lower = query.lower()
    event_types_regex = r'(?:quiz|exam|test|meeting|class|interview|lecture|call|appointment|session|webinar|workshop|presentation|sync)'

    # 1. "Add <title> to (my|the|google)? calendar"
    m = re.search(r'\badd\s+(?:a\s+|an\s+)?([a-zA-Z0-9\s\+&_-]+?)\s+to\s+(?:(?:my|the|google)\s+)?calendar\b', query, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        clean = re.sub(r'\b(?:today|tomorrow|yesterday|at\s+\d+|at\s+\d+:\d+|\d+\s*(?:am|pm)|for\s+\d+.*)\b', '', raw, flags=re.IGNORECASE).strip()
        if clean:
            return preserve_acronym_title(clean)

    # 2. "Put <title> on (my|the|google)? calendar"
    m = re.search(r'\bput\s+(?:a\s+|an\s+)?([a-zA-Z0-9\s\+&_-]+?)\s+on\s+(?:(?:my|the|google)\s+)?calendar\b', query, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        clean = re.sub(r'\b(?:today|tomorrow|yesterday|at\s+\d+|at\s+\d+:\d+|\d+\s*(?:am|pm)|for\s+\d+.*)\b', '', raw, flags=re.IGNORECASE).strip()
        if clean:
            return preserve_acronym_title(clean)

    # 3. "have [a/an] <event_type> at <time> <subject> so mark in calendar"
    # Example: "Today I have quiz at 10 PM deep learning so mark in Google Calendar as event"
    m = re.search(rf'\bhave\s+(?:a\s+|an\s+)?({event_types_regex})\b(?:.+?\bat\s+[0-9:\sapm]+)?\s+([a-zA-Z0-9\s\+&_-]+?)(?:\s+(?:so|to|and|please|mark|add|put|as\s+event)\b|$)', query, re.IGNORECASE)
    if m:
        ev_type = m.group(1).strip()
        subject = m.group(2).strip()
        subject = re.sub(r'\b(?:today|tomorrow|yesterday|at\s+\d+|at\s+\d+:\d+|\d+\s*(?:am|pm)|in\s+google\s+calendar|in\s+calendar|as\s+event|so\s+mark)\b', '', subject, flags=re.IGNORECASE).strip()
        if subject and ev_type.lower() not in subject.lower():
            return f"{preserve_acronym_title(subject)} {ev_type.title()}"
        elif subject:
            return preserve_acronym_title(subject)
        else:
            return ev_type.title()

    # 4. "have [a/an] <subject> <event_type>" e.g. "have a deep learning quiz"
    m = re.search(rf'\bhave\s+(?:a\s+|an\s+)?([a-zA-Z0-9\s\+&_-]+?\s+{event_types_regex})\b', query, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        clean = re.sub(r'\b(?:today|tomorrow|yesterday|at\s+\d+|\d+\s*(?:am|pm))\b', '', raw, flags=re.IGNORECASE).strip()
        if clean:
            return preserve_acronym_title(clean)

    # 5. "mark <title> in calendar" or "mark in calendar as <title>"
    m = re.search(r'\bmark\s+(?:in\s+(?:google\s+|my\s+)?calendar\s+as\s+)?(?:a\s+|an\s+)?([a-zA-Z0-9\s\+&_-]+?)(?:\s+(?:in|on|at|as\s+event)\b|$)', query, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        if raw.lower() not in ["event", "meeting", "calendar", "google calendar"]:
            return preserve_acronym_title(raw)

    # 6. "schedule/book/create <title>"
    m = re.search(r'\b(?:schedule|book|create\s+an?\s+event\s+for|create\s+event\s+for|set\s+up\s+a\s+|set\s+a\s+)\s*([a-zA-Z0-9\s\+&_-]+?)(?:\s+(?:today|tomorrow|yesterday|at|for|on|from)\b|$)', query, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        if raw and raw.lower() not in ["event", "meeting", "session", "calendar", "an event"]:
            return preserve_acronym_title(raw)

    # 7. Check for standalone "<subject> <event_type>" e.g. "deep learning quiz"
    m = re.search(rf'\b([a-zA-Z0-9\+&_-]+(?:\s+[a-zA-Z0-9\+&_-]+)?\s+{event_types_regex})\b', query, re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        cand_clean = re.sub(r'\b(?:have|a|an|the|my|in|at|on|so|today|tomorrow)\b', '', cand, flags=re.IGNORECASE).strip()
        if cand_clean:
            return preserve_acronym_title(cand_clean)

    return "Personal Study Session"

def is_calendar_create_intent(query: str) -> bool:
    """Identifies requests to add, create, schedule, or mark an event on Google Calendar."""
    lower = query.lower()

    # Explicit calendar targets
    if re.search(r'\b(?:add|mark|put|record|insert)\b.*?\b(?:in|on|to)\s+(?:(?:my|the|google)\s+)?calendar\b', lower):
        return True
    if re.search(r'\bmark\s+(?:in|on)\s+(?:google\s+|my\s+)?calendar\b', lower):
        return True
    if re.search(r'\b(?:add|put)\s+.*?\b(?:to|on)\s+(?:(?:my|the|google)\s+)?calendar\b', lower):
        return True
    if re.search(r'\b(?:as\s+event|as\s+an\s+event|calendar\s+event)\b', lower) and any(w in lower for w in ['mark', 'add', 'put', 'set', 'create', 'have', 'schedule']):
        return True

    # Strong scheduling phrases
    if any(w in lower for w in [
        'schedule a', 'schedule an', 'schedule the', 'book a meeting', 'book an event',
        'create event', 'create an event', 'create a calendar event', 'set a meeting',
        'set up a meeting', 'add to calendar', 'put on my calendar', 'mark in calendar'
    ]):
        return True

    # Combinatorial: Verb + Noun + Context
    creation_verbs = ['add', 'schedule', 'book', 'set up', 'create', 'mark', 'put']
    event_nouns = ['event', 'quiz', 'meeting', 'appointment', 'reminder', 'session', 'exam', 'sync', 'interview']
    temporal_clues = ['calendar', 'at', 'pm', 'am', 'today', 'tomorrow']

    has_verb = any(v in lower for v in creation_verbs)
    has_noun = any(n in lower for n in event_nouns)
    has_time = any(t in lower for t in temporal_clues)
    is_view = any(vw in lower for vw in ['show', 'list', 'view', 'what is on', 'what do i have', 'check my', 'see my'])

    if has_verb and has_noun and has_time and not is_view:
        return True

    return False

def is_calendar_view_intent(query: str) -> bool:
    """Identifies strictly read-only queries to inspect or list existing calendar events, schedules, or study sessions."""
    lower = query.lower()
    if is_calendar_create_intent(query):
        return False

    viewing_patterns = [
        r'\b(?:show|list|view|check|get|display|see)\s+(?:my\s+|the\s+)?(?:calendar|events|meetings|agenda|schedule|study tasks|google calendar events)\b',
        r'\bwhat(?:\'s|\s+is)\s+on\s+(?:my\s+|the\s+)?(?:calendar|schedule)\b',
        r'\bwhat\s+do\s+i\s+have\s+(?:planned|scheduled|on)\b',
        r'\bwhat\s+(?:meetings|events|classes|quizzes|exams)\b',
        r'\bmy\s+schedule\b',
        r'\bagenda\s+(?:for\s+)?(?:today|tomorrow|this week|this month)\b',
        r'\bevents\s+(?:for|on|in|this)\b',
        r'\b(?:do\s+i\s+have\s+any\s+events|events\s+on\s+[a-zA-Z]+|\bon\s+[a-zA-Z]+\s+\d{1,2}\b)',
        r'\b(?:next\s+(?:event|three\s+events|3\s+events|task|meeting|quiz|exam)|when\s+is\s+my\s+next)\b',
        r'\b(?:free\s+time|am\s+i\s+free|any\s+free\s+time)\b',
        r'\bhow\s+many\s+study\s+sessions\b',
    ]
    return any(re.search(p, lower) for p in viewing_patterns)


def parse_hours(text: str) -> Optional[float]:
    num_map = {"one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0, "six": 6.0}
    m = re.search(r'\b(\d+(?:\.\d+)?)\s*(?:hour|hr)s?\b', text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    for word, val in num_map.items():
        if re.search(rf'\b{word}\s*(?:hour|hr)s?\b', text, re.IGNORECASE):
            return val
    return None

def is_document_inventory_query(query: str) -> bool:
    """
    Detects whether a query seeks to inspect the inventory, list, count, or metadata of uploaded documents.
    """
    lower = query.lower().strip()
    if "drive" in lower:
        return False
    if any(w in lower for w in ["summarize", "what does the document say", "what does this document say", "explain the", "why does"]):
        return False
    inventory_patterns = [
        r'\b(?:what|which|list|show|how\s+many|find|display|get)\s+(?:all\s+)?(?:my\s+)?(?:uploaded\s+)?(?:documents|files|pdfs|papers|notes|reports)\b',
        r'\blist\s+(?:all\s+)?(?:my\s+)?(?:uploaded\s+)?documents\b',
        r'\bhow\s+many\s+documents\b',
        r'\bdo\s+i\s+have\s+(?:any\s+)?(?:document|pdf|file|notes|paper)\b',
        r'\bdocuments?\s+(?:uploaded|stored|available|failed|status|processed|recently)\b',
        r'\bprocessing\s+status\s+of\s+(?:my\s+)?documents\b',
        r'\bis\s+(?:a|the|my)?\s*.*?\b(?:uploaded|already\s+uploaded|in\s+knowledge)\b',
        r'\bwhich\s+documents\s+are\s+related\b',
        r'\bwhich\s+documents\s+contain\b',
        r'\bfind\s+(?:my\s+)?(?:project\s+)?(?:documentation|docs)\b',
    ]
    return any(re.search(p, lower) for p in inventory_patterns)

def heuristic_classify_intent(query: str, user_tz: str = "UTC") -> Dict[str, Any]:
    """
    Deterministic rule-based and regex intent classifier and argument extractor.
    Operates when Gemini is offline, unconfigured, or as an instant primary router.
    """
    lower = query.lower()

    # 0. Greetings, Bot Identity & General Conversational Queries
    greeting_patterns = [
        r'\b(?:hi|hello|hey|good\s+morning|good\s+afternoon|good\s+evening|howdy|greetings)\b',
        r'\bwho\s+are\s+you\b',
        r'\bwhat\s+can\s+you\s+do\b',
        r'\b(?:help\s+me|what\s+are\s+your\s+capabilities|how\s+does\s+this\s+work)\b',
        r'\b(?:thank\s+you|thanks|goodbye|bye)\b'
    ]
    if any(re.search(p, lower) for p in greeting_patterns) and not any(w in lower for w in ["meeting", "calendar", "plan", "email", "draft", "document", "pdf", "weather", "search"]):
        return {"tool": "general_qa", "args": {"query": query}}

    # 1. Multi-service requests (e.g., Check calendar AND email, prepare study plan)
    has_calendar_keyword = any(w in lower for w in ["calendar", "meeting", "meetings", "schedule"])
    has_email_keyword = any(w in lower for w in ["email", "emails", "gmail", "inbox", "mail"])
    has_plan_keyword = any(w in lower for w in ["study plan", "study schedule", "around my meetings", "around meetings", "prepare a study"])
    if (has_calendar_keyword and has_email_keyword) or (has_plan_keyword and (has_calendar_keyword or has_email_keyword)):
        return {
            "tool": "multi_service_planner",
            "args": {
                "include_calendar": True,
                "include_gmail": True,
                "target_date": "tomorrow" if "tomorrow" in lower else "today",
                "goal": "study_schedule"
            }
        }

    # 2. Calendar Event Deletion / Cancellation Intent (must be before leave/sickness so "Delete doctor appointment" cancels appointment)
    if (any(w in lower for w in ["cancel", "delete", "remove"]) and
        any(w in lower for w in ["meeting", "event", "appointment", "class", "session", "calendar entry", "doctor", "sync", "quiz", "exam", "test"]) and
        not (re.search(r'\b(?:study\s+)?plan\b', lower) and not any(w in lower for w in ["event", "meeting", "appointment", "quiz", "exam", "test"]))
    ):
        confirmed = any(w in lower for w in ["confirm", "permanently", "yes delete", "proceed", "yes cancel"])
        title_match = re.search(r'(?:cancel|delete|remove)\s+(?:the\s+|my\s+)?([a-zA-Z0-9\s]+?)(?:\s+event|\s+meeting|\s+tomorrow|\s+today|\s+on|\s+at|$)', query, re.IGNORECASE)
        ev_title = title_match.group(1).strip() if title_match else ""
        return {
            "tool": "calendar_delete_event",
            "args": {"event_title": ev_title, "query": query, "confirmed": confirmed}
        }

    # 2b. Personal Leave / Sickness / Holiday intent
    leave_info = parse_leave_request(query, user_tz_str=user_tz)
    if leave_info:
        return {
            "tool": "calendar_mark_leave",
            "args": leave_info
        }

    # 2c. Plan Management — Delete Plan Intent (Example D: "I don't like this plan. Delete it.")
    if re.search(r'\b(?:delete|remove|cancel|discard)\s+(?:my\s+|this\s+|the\s+)?(?:study\s+)?plan\b', lower) or (
        "delete" in lower and "plan" in lower and not any(k in lower for k in ["event", "email", "doc", "task", "meeting"])
    ):
        confirmed = any(w in lower for w in ["confirm", "permanently", "yes delete", "proceed"])
        return {
            "tool": "plan_delete",
            "args": {"confirmed": confirmed, "query": query}
        }


    # 2c. Plan Management — Complete Task Intent (Example C: "I completed today's Java task.")
    if re.search(r'\b(?:complete|completed|finish|finished|done with|marked complete)\b', lower) and (
        any(w in lower for w in ["task", "session", "lesson", "module", "study", "java", "dsa", "today"])
    ):
        term = ""
        if "java" in lower:
            term = "java"
        elif "dsa" in lower:
            term = "dsa"
        elif "today" in lower:
            term = "today"
        else:
            m = re.search(r'(?:completed|finished|done with)\s+(?:today\'s\s+|the\s+|my\s+)?([a-zA-Z0-9\s]+?)(?:\s+task|\s+session|$)', lower)
            if m:
                term = m.group(1).strip()
        return {
            "tool": "plan_complete_task",
            "args": {"task_title_search": term or "today", "completed": True}
        }

    # 2d. Plan Management — Reschedule / Move Task Intent (Example E: "Move my Java study session to tomorrow at 4 PM.")
    if re.search(r'\b(?:move|reschedule|shift|postpone)\s+(?:my\s+)?([a-zA-Z0-9\s]+?)\s+(?:to|at|for|until)\b', lower) and (
        any(w in lower for w in ["study", "session", "java", "dsa", "task"])
    ):
        m = re.search(r'\b(?:move|reschedule|shift|postpone)\s+(?:my\s+)?([a-zA-Z0-9\s]+?)\s+(?:to|at|for|until)\b', lower)
        target_subject = m.group(1).replace("study session", "").replace("session", "").strip() if m else "study session"
        return {
            "tool": "plan_reschedule_task",
            "args": {"task_title_search": target_subject or "study", "query": query}
        }

    # 2d-2. Calendar Event Reschedule / Move Intent
    if re.search(r'\b(?:move|reschedule|shift|postpone)\s+(?:my\s+)?([a-zA-Z0-9\s]+?)\s+(?:to|at|for|until)\b', lower) and (
        any(w in lower for w in ["meeting", "appointment", "call", "sync", "conference", "doctor", "event", "quiz", "class", "exam", "session"])
    ):
        m = re.search(r'\b(?:move|reschedule|shift|postpone)\s+(?:my\s+)?([a-zA-Z0-9\s]+?)\s+(?:to|at|for|until)\b', lower)
        target = m.group(1).strip() if m else "meeting"
        return {
            "tool": "calendar_update_event",
            "args": {"event_title": target, "query": query}
        }

    # 2d-3. Plan Management — Calendar Sync for Study Sessions Intent
    if re.search(r'\b(?:add|sync|push|put)\s+(?:the\s+)?(?:selected\s+)?(?:study\s+)?(?:sessions?|blocks?|tasks?|plan)\s+(?:in|to|with)\s+(?:google\s+)?calendar\b', lower) or (
        any(w in lower for w in ["add sessions to calendar", "sync plan to calendar", "sync my plan with calendar", "add study sessions to google calendar", "add selected study sessions to google calendar"])
    ):
        confirmed = any(w in lower for w in ["confirm", "proceed", "yes sync", "yes add", "permanently"])
        return {
            "tool": "plan_sync_calendar",
            "args": {"confirmed": confirmed, "query": query}
        }

    # 2d-4. Plan Management — Generate / Propose Schedule Intent
    if re.search(r'\b(?:generate|propose|suggest)\s+(?:a\s+)?(?:study\s+)?schedule\b', lower) or (
        re.search(r'\b(?:show\s+my\s+proposed\s+study\s+times|which\s+study\s+sessions\s+conflict)\b', lower)
    ) or (
        re.search(r'\bshow\s+(?:my\s+)?(?:study\s+)?schedule\s+(?:for\s+)?(?:the\s+)?(?:next\s+)?([0-9]+|six|three|two|one)?\s*(?:months?|weeks?|days?)?\b', lower)
    ) or (
        "schedule" in lower and "plan" in lower and any(w in lower for w in ["generate", "propose", "show", "smart slots", "slots", "times", "for my", "next six months", "next 6 months"]) and not any(w in lower for w in ["add", "sync", "put", "calendar as event"])
    ):
        m_title = re.search(r'(?:schedule\s+for\s+(?:my\s+)?)([a-zA-Z0-9\s]+?)(?:\s+plan|\.|\,|$)', query, re.IGNORECASE)
        target_plan = m_title.group(1).strip() if m_title else ""
        return {
            "tool": "plan_propose_schedule",
            "args": {"plan_title": target_plan, "query": query}
        }

    # 2d-5. Plan Management — Show Specific Week Intent ("Show me week three of my Java plan")
    week_query_match = re.search(r'\b(?:show|view|get|display)\s+(?:me\s+)?week\s+([0-9]+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b', lower)
    if week_query_match:
        w_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
        raw_w = week_query_match.group(1).lower()
        w_num = w_words.get(raw_w, int(raw_w) if raw_w.isdigit() else 1)
        m_subj = re.search(r'(?:of|for|in)\s+(?:my\s+)?([a-zA-Z0-9\s]+?)(?:\s+plan|\.|\,|$)', query, re.IGNORECASE)
        target_plan = m_subj.group(1).strip() if m_subj else ""
        return {
            "tool": "plan_get",
            "args": {"plan_title": target_plan, "week_number": w_num, "query": query}
        }

    # 2d-6. Plan Management — What to Study Today / Tomorrow Intent ("What should I study tomorrow?")
    if re.search(r'\bwhat\s+(?:should\s+i|to)\s+study\s+(?:today|tomorrow)\b', lower) or (
        "what should i study" in lower or "what to study" in lower
    ):
        target_day = "tomorrow" if "tomorrow" in lower else "today"
        return {
            "tool": "plan_get",
            "args": {"daily_study_query": True, "target_date": target_day, "query": query}
        }

    # 2d-7. Plan Management — Reschedule Unfinished Tasks Intent ("Reschedule my unfinished tasks")
    if re.search(r'\breschedule\s+(?:my\s+)?(?:unfinished|pending|missed|remaining)\s+(?:study\s+)?tasks?\b', lower):
        return {
            "tool": "plan_reschedule_task",
            "args": {"reschedule_all_pending": True, "query": query}
        }

    # 2d-8. Plan Management — Plan Status / Pending Tasks / Progress
    if re.search(r'\b(?:what|which)\s+tasks\s+(?:are\s+)?(?:pending|remaining|left|open)\b', lower) or (
        re.search(r'\bhow\s+much\s+(?:of\s+my\s+.*?\s+)?plan\s+(?:have\s+i\s+completed|is\s+done|is\s+complete)\b', lower)
    ) or (
        any(w in lower for w in ["pending tasks", "tasks pending", "how much of my project plan", "plan progress"])
    ):
        m_plan = re.search(r'(?:in|for|of)\s+(?:my\s+)?([a-zA-Z0-9\s]+?)\s+plan\b', lower)
        plan_title = m_plan.group(1).strip() if m_plan else ""
        return {
            "tool": "plan_get",
            "args": {"plan_title": plan_title, "query": query}
        }

    # 2e. Plan Management — Create Study Plan Intent (Supports 1 Day to 6 Months)
    if re.search(r'\b(?:create|make|generate|build|prepare|design|set up)\s+(?:a\s+|an\s+)?([0-9]+[\s-]*day|[0-9]+[\s-]*week|semester|[a-zA-Z0-9\s]+)?\s*(?:study\s+plan|roadmap|plan)\b', lower) or (
        ("create" in lower or "make" in lower or "generate" in lower or "help me plan" in lower) and ("study plan" in lower or "study week" in lower or ("plan" in lower and any(w in lower for w in ["dsa", "java", "python", "hours", "days", "30-day", "30 day", "month", "months", "machine learning", "full stack"])))
    ) or "plan my study week" in lower:
        word_num_map = {
            "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
            "thirty": "30", "sixty": "60", "ninety": "90"
        }
        if "30-day" in lower:
            period = "30-Day"
        elif "study week" in lower or "my week" in lower or "this week" in lower:
            period = "7 Days"
        else:
            period_match = re.search(r'(\d+|one|two|three|four|five|six|seven|thirty|sixty|ninety)[\s-]*(day|week|month)s?', lower)
            if period_match:
                raw_val = period_match.group(1).lower()
                val = word_num_map.get(raw_val, raw_val)
                unit = period_match.group(2).lower()
                period = f"{val} {unit.title() if int(val) == 1 else unit.title() + 's'}"
            else:
                period = "30 Days"

        subject = "Academic Study"
        if "machine learning" in lower or "ml" in lower or "deep learning" in lower:
            subject = "Machine Learning"
        elif "spring" in lower:
            subject = "Java and Spring Boot"
        elif "full stack" in lower or "full-stack" in lower or "web dev" in lower:
            subject = "Full-Stack Web Development"
        elif "java" in lower and "dsa" in lower:
            subject = "Java and DSA"
        elif "java" in lower:
            subject = "Java Programming"
        elif "dsa" in lower or "data structures" in lower:
            subject = "DSA"
        elif "python" in lower:
            subject = "Python Programming"
        else:
            subj_match = re.search(r'(?:plan\s+for|study\s+plan\s+for|(?:day|week|month)s?\s+)([a-zA-Z0-9\s\+]+?)(?:\s+study\s+plan|\s+roadmap|\.|\,|$)', query, re.IGNORECASE)
            if subj_match and subj_match.group(1).strip() and not any(w in subj_match.group(1).lower() for w in ["create", "make", "generate"]):
                subject = subj_match.group(1).strip()

        hours = parse_hours(query) or 3.0
        suffix = "Study Plan" if "study plan" in lower else "Roadmap"
        title = f"{period} {subject} {suffix}".strip()
        dur_days = parse_plan_duration(period)
        return {
            "tool": "plan_create",
            "args": {
                "title": title,
                "period": period,
                "duration_days": dur_days,
                "daily_hours": hours,
                "subject": subject,
                "query": query
            }
        }

    # 2f. Plan Management — Change / Update Study Hours Intent (Example B: "I can only study two hours daily now. Update my plan.")
    hours_found = parse_hours(query)
    is_update_request = any(w in lower for w in ["update", "change", "modify", "only study", "can only", "now study", "adjust"])
    if (hours_found is not None and is_update_request) or (
        any(w in lower for w in ["update my plan", "change my plan", "modify my plan"])
    ):
        return {
            "tool": "plan_update",
            "args": {"daily_hours": hours_found or 2.0, "query": query}
        }

    # 2g. Plan Management — Add Task Intent
    if re.search(r'\b(?:add|append|create)\s+(?:a\s+)?(?:new\s+)?task\b', lower) or (
        "add" in lower and "task" in lower and any(w in lower for w in ["plan", "study", "schedule"])
    ):
        dur = 45
        m_dur = re.search(r'(\d+)\s*(?:min|minute)s?', lower)
        if m_dur:
            dur = int(m_dur.group(1))
        h_dur = parse_hours(query)
        if h_dur:
            dur = int(h_dur * 60)
        t_match = re.search(r'(?:task|called|named|titled)\s+[\'"]?([a-zA-Z0-9\s:-]+?)[\'"]?(?:\s+for|\s+to|\s+with|\s+in|$)', query, re.IGNORECASE)
        task_title = t_match.group(1).strip() if t_match else "New Study Task"
        return {
            "tool": "plan_add_task",
            "args": {"title": task_title, "duration_minutes": dur, "query": query}
        }

    # 2h. Plan Management — Delete Task Intent
    if re.search(r'\b(?:delete|remove)\s+(?:the\s+|this\s+|my\s+)?task\b', lower) or (
        ("delete" in lower or "remove" in lower) and "task" in lower and not any(w in lower for w in ["plan", "event", "meeting"])
    ):
        t_match = re.search(r'(?:task|called|named|titled)\s+[\'"]?([a-zA-Z0-9\s:-]+?)[\'"]?(?:\s+from|\s+in|\s+of|$)', query, re.IGNORECASE)
        task_title = t_match.group(1).strip() if t_match else "study"
        return {
            "tool": "plan_delete_task",
            "args": {"task_title_search": task_title, "query": query}
        }

    # 2i. Plan Management — List Plans Intent
    if re.search(r'\b(?:show|list|view|get|see)\s+(?:my\s+)?(?:saved\s+)?(?:study\s+)?plans\b', lower) or (
        any(w in lower for w in ["my plans", "study plans", "list plans", "show plans", "saved plans", "view my plan"]) and not any(w in lower for w in ["create", "delete", "remove", "schedule for", "add to"])
    ):
        return {
            "tool": "plan_list",
            "args": {}
        }

    # 3a. Document Inventory & Metadata Discovery Intent (Knowledge Base)
    if is_document_inventory_query(query):
        return {
            "tool": "document_inventory",
            "args": {"query": query}
        }

    # 3b. Document-level summary intent (Knowledge Base)
    if is_document_summary_query(query):
        return {
            "tool": "document_summary",
            "args": {"document_query": query}
        }

    # 4. Gmail Send Message Intent (Explicit action or confirmation)
    if re.search(r'\bsend\s+(?:this\s+|the\s+)?(?:email|draft|message)\b', lower) or lower.startswith("send this email") or "send an email" in lower:
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', query)
        recipient = email_match.group(0) if email_match else None
        subject_match = re.search(r'(?:about|regarding|subject[:\s]+)([^.\n]+)', query, re.IGNORECASE)
        subject = subject_match.group(1).strip().capitalize() if subject_match else None
        return {
            "tool": "gmail_send_message",
            "args": {"query": query, "to": recipient, "subject": subject}
        }

    # 5. Gmail Create Draft Intent
    if any(w in lower for w in ["draft an email", "draft email", "compose an email", "compose email", "write an email"]):
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', query)
        recipient = email_match.group(0) if email_match else "recipient@university.edu"

        subject = "Academic Update"
        subject_match = re.search(r'(?:about|regarding|subject[:\s]+)([^.\n]+)', query, re.IGNORECASE)
        if subject_match:
            subject = subject_match.group(1).strip().capitalize()
        elif "sick" in lower or "fever" in lower or "ill" in lower or "cannot attend" in lower:
            subject = "Absence Notification: Medical Leave"

        return {
            "tool": "gmail_create_draft",
            "args": {"to": recipient, "subject": subject, "query": query}
        }

    # 6. Gmail Search & Summarize Intent
    if any(w in lower for w in ["email", "emails", "gmail", "inbox", "mail"]):
        is_summary = any(w in lower for w in ["summarize", "summary", "extract", "tasks", "deadlines", "latest", "recent"])
        extract_deadlines = any(w in lower for w in ["deadline", "deadlines", "task", "tasks", "assignment", "due"])
        search_q = query.replace("find", "").replace("search", "").replace("emails", "").replace("inbox", "").replace("about", "").replace("the", "").strip()
        if is_summary or extract_deadlines or "professor" in lower:
            return {
                "tool": "gmail_search_and_summarize",
                "args": {"query": search_q or "academic", "extract_deadlines": extract_deadlines}
            }
        return {"tool": "gmail_priority_messages", "args": {"query": search_q}}

    # 7. Drive Search & Read Intent
    if "drive" in lower or "google drive" in lower:
        search_term = query.replace("find", "").replace("search", "").replace("in drive", "").replace("google drive", "").replace("the", "").replace("pdf", "").replace("document", "").replace("what is in my", "").replace("what files are in", "").replace("list my", "").replace("files", "").strip()
        read_content = any(w in lower for w in ["summarize", "read", "content", "contains", "about", "what does", "architecture", "extract"])
        if any(w in lower for w in ["spreadsheet", "spreadsheets", "sheets", "excel", "csv", "xlsx"]):
            search_term = "spreadsheet"
        return {
            "tool": "drive_search_and_read",
            "args": {"query": search_term if search_term else None, "read_content": read_content}
        }

    # 8. Calendar Event Creation / Scheduling Intent
    if is_calendar_create_intent(query):
        # Check for multiple intervals like '7 AM to 9 AM and 6 PM to 8 PM'
        intervals = parse_natural_time_intervals(query, user_tz_str=user_tz)
        if len(intervals) >= 2:
            return {
                "tool": "calendar_propose_event",
                "args": {
                    "title": extract_calendar_event_title(query),
                    "intervals": [m[2] for m in intervals],
                    "start_time": intervals[0][0].isoformat(),
                    "duration_mins": intervals[0][2]["durationMinutes"],
                    "location": ""
                }
            }

        start_dt, end_dt, meta = parse_natural_datetime(query, user_tz_str=user_tz)
        title = extract_calendar_event_title(query)
        return {
            "tool": "calendar_propose_event",
            "args": {
                "title": title,
                "start_time": start_dt.isoformat(),
                "duration_mins": meta.get("durationMinutes", 60),
                "location": ""
            }
        }

    # 9. Timetable Intent
    tt_keywords = [
        "class", "classes", "timetable", "lecture", "lectures", "hall", "room", "msc",
        "free between", "free period", "free periods", "free slot", "free slots", "after lunch",
        "overlapping", "overlap", "clash", "conflict", "double booked", "laboratory", "lab session",
        "who teaches", "which faculty", "which teacher", "next class", "last class", "final class",
        "next lab", "next java", "next python", "next dbms", "monday timetable", "tuesday timetable",
        "wednesday timetable", "thursday timetable", "friday timetable", "saturday timetable",
        "sunday timetable", "tomorrow's classes", "classes tomorrow", "classes today"
    ]
    is_tt_query = any(w in lower for w in tt_keywords) or (
        "am i free" in lower and "between" in lower
    ) or (
        "between" in lower and any(w in lower for w in ["am", "pm", "10", "11", "12", "1", "2", "3", "4", "5"])
    ) or (
        ("period" in lower or "periods" in lower) and any(d in lower for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "today", "tomorrow"])
    )

    if is_tt_query:
        user_curr_d = get_user_current_date(user_tz or "UTC").strftime("%A")
        details = parse_period_query_details(lower, user_curr_day=user_curr_d)
        intent = details.get("intent")
        target_day = details.get("day")
        if intent == "PERIOD_SINGLE":
            return {"tool": "get_timetable_period", "args": {"day": target_day or user_curr_d, "period_number": details["period_number"]}}
        elif intent in ("PERIODS_MULTIPLE", "PERIODS_RANGE"):
            return {"tool": "get_timetable_periods", "args": {"day": target_day or user_curr_d, "period_numbers": details["period_numbers"]}}
        elif intent == "AT_TIME":
            return {"tool": "get_timetable_period_by_time", "args": {"day": target_day or user_curr_d, "time": details["time"]}}
        elif intent == "BETWEEN_TIMES":
            return {"tool": "get_timetable_between_times", "args": {"day": target_day, "start_time": details["start_time"], "end_time": details["end_time"]}}
        elif intent == "FULL_TIMETABLE":
            return {"tool": "get_full_timetable", "args": {}}
        elif intent == "NEXT_LAB":
            return {"tool": "get_next_class", "args": {"is_lab": True}}
        elif intent == "NEXT_CLASS":
            return {"tool": "get_next_class", "args": {"subject": details.get("subject")}}
        elif intent == "DAY_SCHEDULE" and target_day:
            return {"tool": "get_timetable_for_day", "args": {"day": target_day}}
        else:
            return {"tool": "search_timetable", "args": {"query": query}}

    # 12. Unified Calendar & Schedule Viewing Intent (strictly read-only)
    calendar_keywords = [
        "what is on my calendar", "what do i have scheduled", "what do i have tomorrow",
        "what do i have planned", "what is scheduled", "my schedule this week", "events this month",
        "do i have any free time", "am i free", "what study tasks do i have",
        "upcoming study sessions", "next scheduled task", "study sessions are synchronized",
        "schedule for tomorrow", "schedule for today", "show my schedule",
        "synchronized with", "synced with", "are my study sessions", "are study sessions",
        "sync status", "study tasks do i have", "tasks do i have", "next event", "next three events",
        "next 3 events", "next quiz", "next exam", "next meeting", "free time tomorrow", "free at 6",
        "google calendar events", "study tasks for today", "events on november", "planned tomorrow"
    ]
    if is_calendar_view_intent(query) or any(k in lower for k in calendar_keywords):
        time_min, time_max = None, None
        explicit_d = parse_explicit_calendar_date(query)
        if explicit_d:
            time_min = datetime.combine(explicit_d, time(0, 0, 0)).isoformat()
            time_max = datetime.combine(explicit_d, time(23, 59, 59)).isoformat()
        elif "tomorrow" in lower:
            start_dt, _, _ = parse_natural_datetime("tomorrow", user_tz_str=user_tz)
            time_min = start_dt.replace(hour=0, minute=0, second=0).isoformat()
            time_max = start_dt.replace(hour=23, minute=59, second=59).isoformat()
        elif "today" in lower:
            start_dt, _, _ = parse_natural_datetime("today", user_tz_str=user_tz)
            time_min = start_dt.replace(hour=0, minute=0, second=0).isoformat()
            time_max = start_dt.replace(hour=23, minute=59, second=59).isoformat()
        elif "week" in lower:
            _, _, time_min, time_max = get_user_week_bounds(user_tz)
        elif "month" in lower:
            _, _, time_min, time_max = get_user_month_bounds(user_tz)

        return {"tool": "calendar_events_retrieval", "args": {"time_min": time_min, "time_max": time_max, "query": query}}

    # 13. Weather Intent
    weather_match = re.search(r'(?:weather|temperature|forecast|climate)\s+(?:in|for|at)?\s*([a-zA-Z\s]+)', lower)
    if any(w in lower for w in ["weather", "temperature", "forecast", "climate"]):
        city = "Bengaluru"
        if weather_match and weather_match.group(1).strip():
            city = weather_match.group(1).replace("today", "").replace("tomorrow", "").replace("currently", "").strip()
        return {"tool": "weather_lookup", "args": {"city": city or "Bengaluru"}}

    # 12. Web Search Intent
    if any(w in lower for w in ["web search", "search the web", "search internet", "browse the web"]):
        web_q = query.replace("search the web for", "").replace("search the web", "").strip()
        return {"tool": "web_search_intelligence", "args": {"query": web_q or query}}

    # 13. Knowledge Base RAG Intent (Syllabus, Notes, Textbooks, Units, Modules, Topics)
    if any(w in lower for w in [
        "notes", "syllabus", "uploaded", "paper", "document", "pdf", "what does the text say",
        "my resume", "resume", "unit", "chapter", "module", "topic", "topics", "covered in",
        "textbook", "curriculum", "coursework", "subject", "concept", "explain", "describe",
        "what is", "what are", "inheritance", "normalization", "database", "database design"
    ]):
        return {"tool": "rag_knowledge_lookup", "args": {"query": query}}

    # Default fallback: Knowledge Base RAG
    return {"tool": "rag_knowledge_lookup", "args": {"query": query}}

class AureliaAgent:
    """
    Main conversational agent orchestrator for Aurelia AI.
    Executes typed tools, loads persistent conversation memory, enforces tenant isolation,
    checks website-level Google capabilities, and synthesizes grounded answers using Gemini.
    """
    async def run(self, user_id: str, query: str, conversation_id: str, db: Session) -> Dict[str, Any]:
        start_time = datetime.now()
        tool_executions = []
        citations = []
        suggested_action = None
        response_content = ""

        # Fetch user timezone
        user_record = db.query(User).filter_by(id=user_id).first()
        user_tz = getattr(user_record, "timezone", "UTC") or "UTC"

        # Load recent conversation history (excluding the current user message just inserted)
        history_msgs = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(6)
            .all()
        )
        history_context = ""
        prior_msgs = [m for m in history_msgs if not (m.role == "user" and m.content.strip() == query.strip())]
        if prior_msgs:
            history_lines = []
            for m in reversed(prior_msgs[:4]):
                history_lines.append(f"{m.role.upper()}: {m.content[:250]}")
            history_context = "[Recent Conversation Context]\n" + "\n".join(history_lines) + "\n\n"

        # Step 1: Intent Classification
        classified = await classify_intent_with_gemini(query, history_context, user_tz=user_tz)
        if not classified:
            classified = heuristic_classify_intent(query, user_tz=user_tz)

        # Context-Aware Follow-up Resolution for Timetable Queries (e.g. "Which room?", "Who teaches it?", "What time?")
        lower_q = query.lower().strip()
        is_followup = any(re.match(rf'^{pattern}\b', lower_q) for pattern in [
            "which room", "what room", "where is my", "where is the", "where is it", "where",
            "who teaches", "who is the faculty", "who is the instructor", "who is teaching",
            "who teaches it", "who is the teacher", "what time", "when is it"
        ]) or lower_q in ["which room?", "where?", "where is it?", "who teaches it?", "who is the teacher?", "what time?"]

        if is_followup:
            user_courses = db.query(TimetablePeriod.subject_name, TimetablePeriod.subject_code).filter(TimetablePeriod.user_id == user_id).all()
            if not user_courses:
                user_courses = db.query(TimetableEntry.course_name, TimetableEntry.course_code).filter(TimetableEntry.user_id == user_id).all()
            found_subject = None
            if prior_msgs:
                for c_name, c_code in user_courses:
                    for pm in prior_msgs[:4]:
                        c_clean = (c_name or "").lower()
                        pm_clean = pm.content.lower()
                        if (c_clean and c_clean in pm_clean) or (c_code and c_code.lower() in pm_clean) or (c_clean and len(c_clean.split()) > 0 and len(c_clean.split()[0]) >= 3 and c_clean.split()[0] in pm_clean):
                            found_subject = c_name
                            break
                    if found_subject:
                        break
            if not found_subject and len(user_courses) == 1:
                found_subject = user_courses[0][0]

            if found_subject:
                follow_t = "room" if any(w in lower_q for w in ["room", "where"]) else ("faculty" if any(w in lower_q for w in ["who", "teach", "faculty", "instructor"]) else "time")
                classified = {
                    "tool": "search_timetable",
                    "args": {
                        "query": query,
                        "subject": found_subject,
                        "followup_type": follow_t
                    }
                }

        selected_tool = classified.get("tool", "rag_knowledge_lookup")
        tool_args = classified.get("args", {})

        # Step 2: Tool Execution Pathways

        # --- PATH 0A: PLAN CREATE ---
        if selected_tool == "plan_create":
            subject = tool_args.get("subject")
            title_context = (tool_args.get("title", "") + " " + query).lower()
            if not subject or subject == "Academic":
                if "java" in title_context and "dsa" in title_context:
                    subject = "Java and DSA"
                elif "java" in title_context:
                    subject = "Java"
                elif "dsa" in title_context:
                    subject = "DSA"
                elif "machine learning" in title_context or "ml" in title_context:
                    subject = "Machine Learning"
                else:
                    subject = "Academic Study"

            period = tool_args.get("period", "30 Days")
            daily_hours = tool_args.get("daily_hours", 3.0)
            if isinstance(daily_hours, str):
                try:
                    daily_hours = float(re.search(r'[\d\.]+', daily_hours).group(0))
                except Exception:
                    daily_hours = 3.0
            daily_hours = float(daily_hours) if daily_hours else 3.0
            target_mins = int(daily_hours * 60)

            explicit_tasks = tool_args.get("tasks")
            if explicit_tasks and isinstance(explicit_tasks, list) and len(explicit_tasks) > 0:
                tasks_data = []
                for idx, t in enumerate(explicit_tasks):
                    if isinstance(t, dict):
                        tasks_data.append({
                            "title": t.get("title", "Study Task"),
                            "durationMinutes": int(t.get("durationMinutes", t.get("duration_minutes", target_mins))),
                            "priority": t.get("priority", "high"),
                            "completed": bool(t.get("completed", False)),
                            "monthNumber": t.get("monthNumber", 1),
                            "weekNumber": t.get("weekNumber", 1),
                            "dayNumber": t.get("dayNumber", idx + 1),
                            "taskOrder": t.get("taskOrder", idx + 1),
                            "taskType": t.get("taskType", "daily"),
                            "dayLabel": t.get("dayLabel", f"Day {idx + 1}"),
                            "weekLabel": t.get("weekLabel", "Week 1"),
                            "monthLabel": t.get("monthLabel", "Month 1"),
                            "milestoneGroup": t.get("milestoneGroup", f"Milestone: {subject}")
                        })
                plan_title = tool_args.get("title") or f"{period} {subject} Study Plan".strip()
                goals = tool_args.get("goals") or [
                    f"Master core competencies in {subject}",
                    f"Maintain consistent {daily_hours:g}-hour daily study sessions",
                    f"Complete all structured milestones within {period}"
                ]
                duration_days = parse_plan_duration(period)
                start_d, end_d, _ = calculate_plan_dates(duration_text=period, user_tz_str=user_tz)
            else:
                # Full-duration AI roadmap generation supporting 1 day up to 6 months
                roadmap_res = await generate_study_plan_roadmap(
                    subject=subject,
                    duration_text=period,
                    daily_hours=daily_hours,
                    user_tz_str=user_tz
                )
                tasks_data = roadmap_res.get("tasks", [])
                plan_title = tool_args.get("title") or roadmap_res.get("title") or f"{period} {subject} Roadmap".strip()
                goals = tool_args.get("goals") or roadmap_res.get("goals", [])
                duration_days = roadmap_res.get("durationDays", 30)
                start_d = date.fromisoformat(roadmap_res["startDate"])
                end_d = date.fromisoformat(roadmap_res["endDate"])

            study_blocks = [
                {"day": "Monday", "startTime": "09:00 AM", "endTime": f"{9 + int(daily_hours):02d}:00 AM", "focus": f"{subject} Focus Block 1"},
                {"day": "Wednesday", "startTime": "09:00 AM", "endTime": f"{9 + int(daily_hours):02d}:00 AM", "focus": f"{subject} Focus Block 2"},
                {"day": "Friday", "startTime": "09:00 AM", "endTime": f"{9 + int(daily_hours):02d}:00 AM", "focus": f"{subject} Focus Block 3"},
            ]

            res = await tool_registry.execute(
                "plan_create",
                user_id=user_id,
                db=db,
                title=plan_title,
                period=period,
                subject=subject,
                learning_goal=f"Master {subject} in {duration_days} days",
                start_date=start_d.isoformat(),
                end_date=end_d.isoformat(),
                duration_days=duration_days,
                daily_hours_target=daily_hours,
                goals=goals,
                tasks=tasks_data,
                suggested_study_blocks=study_blocks
            )

            created_plan = res.get("plan", {})
            total_tasks_count = len(tasks_data)

            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "StudyPlanCreator",
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Created and persisted '{plan_title}' with {total_tasks_count} tasks across {duration_days} days."
            })

            sample_tasks = created_plan.get("tasks", [])[:5]
            task_list_str = "\n".join([f"• **{t['title']}** ({t['durationMinutes']} mins, {t.get('dayLabel', 'Day ' + str(t.get('dayNumber', i+1)))})" for i, t in enumerate(sample_tasks)])
            if len(created_plan.get("tasks", [])) > 5:
                task_list_str += f"\n• *...and {len(created_plan.get('tasks', [])) - 5} more structured daily tasks spanning your {period} roadmap.*"

            response_content = (
                f"I have created and saved your complete **{plan_title}** ({period}) to your Planning Workspace!\n\n"
                f"• **Duration:** {duration_days} days ({start_d.isoformat()} to {end_d.isoformat()})\n"
                f"• **Daily Study Allocation:** {daily_hours:g} hours daily\n"
                f"• **Roadmap Tasks:** {total_tasks_count} actionable daily & milestone tasks\n\n"
                f"**Initial Roadmap Progression:**\n{task_list_str}\n\n"
                f"Your plan is persistently stored in your database and is immediately visible on your **Plan** page with complete month, week, and day breakdown."
            )

        # --- PATH 0B: PLAN UPDATE (Change hours, etc.) ---
        elif selected_tool == "plan_update":
            daily_hours = tool_args.get("daily_hours", 2.0)
            if isinstance(daily_hours, str):
                try:
                    daily_hours = float(re.search(r'[\d\.]+', daily_hours).group(0))
                except Exception:
                    daily_hours = 2.0
            daily_hours = float(daily_hours) if daily_hours else 2.0
            res = await tool_registry.execute(
                "plan_update",
                user_id=user_id,
                db=db,
                daily_hours=daily_hours
            )
            if res.get("status") == "success":
                tool_executions.append({
                    "id": str(uuid.uuid4()),
                    "toolName": "StudyPlanUpdater",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resultSummary": f"Updated plan '{res.get('title')}' to {daily_hours}h daily."
                })
                response_content = (
                    f"I've updated your study plan '**{res.get('title')}**'.\n\n"
                    f"• **Daily Study Commitment:** Adjusted to **{daily_hours:g} hours daily** ({int(daily_hours*60)} minutes per session).\n"
                    f"• **Preserved History:** All your completed tasks and schedule progress remain intact.\n"
                    f"• **Updated Sessions:** {res.get('updatedTaskCount')} pending study sessions have been rescheduled to match your new {daily_hours:g}-hour daily availability.\n\n"
                    f"Your Plan page has been updated with these changes."
                )
            else:
                response_content = res.get("message", "No active study plan was found to update.")

        # --- PATH 0C: PLAN COMPLETE TASK ---
        elif selected_tool == "plan_complete_task":
            search_term = tool_args.get("task_title_search", "")
            res = await tool_registry.execute(
                "plan_update_task",
                user_id=user_id,
                db=db,
                task_title_search=search_term,
                completed=True
            )
            if res.get("status") == "success":
                tool_executions.append({
                    "id": str(uuid.uuid4()),
                    "toolName": "PlanTaskCompletion",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resultSummary": f"Marked '{res.get('title')}' as completed."
                })
                response_content = (
                    f"🎉 Great job! I have marked '**{res.get('title')}**' as **completed** in your study plan.\n\n"
                    f"Your updated completion progress is immediately reflected on your **Plan** page."
                )
            else:
                response_content = f"I could not locate an uncompleted task matching *\"{search_term}\"* in your saved study plan. Please verify the task title on your Plan page."

        # --- PATH 0D: PLAN DELETE (Destructive action with confirmation) ---
        elif selected_tool == "plan_delete":
            confirmed = tool_args.get("confirmed", False) or tool_args.get("confirmation_confirmed", False)
            target_title = tool_args.get("title") or tool_args.get("plan_title")
            active_plan = None
            if target_title:
                active_plan = db.query(Plan).filter(Plan.user_id == user_id, Plan.title.ilike(f"%{target_title.strip()}%")).first()
            if not active_plan:
                active_plan = db.query(Plan).filter(Plan.user_id == user_id).order_by(Plan.updated_at.desc()).first()
            if not active_plan:
                response_content = "You do not have any saved study plans in your workspace to delete."
            elif not confirmed:
                tasks = db.query(PlanTask).filter(PlanTask.plan_id == active_plan.id).all()
                suggested_action = {
                    "id": str(uuid.uuid4()),
                    "actionType": "delete_plan",
                    "title": f"Delete Study Plan: {active_plan.title}",
                    "details": {
                        "planId": active_plan.id,
                        "planTitle": active_plan.title,
                        "taskCount": f"{len(tasks)} associated tasks",
                        "calendar": "Google Calendar events will NOT be deleted",
                        "warning": "This will permanently remove the study plan and its associated tasks from your database."
                    },
                    "status": "pending"
                }
                tool_executions.append({
                    "id": str(uuid.uuid4()),
                    "toolName": "PlanDeletionGuard",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resultSummary": f"Awaiting user confirmation to delete plan '{active_plan.title}'."
                })
                response_content = (
                    f"⚠️ **Destructive Action Confirmation Required**\n\n"
                    f"Are you sure you want to permanently delete your study plan '**{active_plan.title}**'?\n\n"
                    f"• **Associated Tasks:** {len(tasks)} tasks will be removed from your database.\n"
                    f"• **Calendar Safety:** Google Calendar events and independent calendar commitments will **NOT** be deleted.\n\n"
                    f"Please click **Confirm & Commit Action** below to permanently delete this plan."
                )
            else:
                del_res = await tool_registry.execute("plan_delete", user_id=user_id, db=db, plan_id=active_plan.id)
                tool_executions.append({
                    "id": str(uuid.uuid4()),
                    "toolName": "StudyPlanDeletion",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resultSummary": f"Deleted study plan '{active_plan.title}'."
                })
                remaining_count = db.query(Plan).filter(Plan.user_id == user_id).count()
                empty_note = " You currently have no study plans remaining." if remaining_count == 0 else ""
                response_content = f"🗑️ The study plan '**{active_plan.title}**' and its associated tasks have been permanently deleted.{empty_note}"

        # --- PATH 0E: PLAN RESCHEDULE TASK ---
        elif selected_tool == "plan_reschedule_task":
            reschedule_all = tool_args.get("reschedule_all_pending", False)
            if reschedule_all:
                active_plan = db.query(Plan).filter(Plan.user_id == user_id).order_by(Plan.updated_at.desc()).first()
                if not active_plan:
                    response_content = "You do not have an active study plan with unfinished tasks to reschedule."
                else:
                    pending_tasks = db.query(PlanTask).filter(
                        PlanTask.plan_id == active_plan.id,
                        PlanTask.completed == False
                    ).order_by(PlanTask.task_order, PlanTask.created_at).all()

                    if not pending_tasks:
                        response_content = f"🎉 All tasks in '**{active_plan.title}**' are already completed! Nothing to reschedule."
                    else:
                        now_l = datetime.now(timezone.utc).astimezone(zoneinfo.ZoneInfo(user_tz))
                        next_d = now_l.date() + timedelta(days=1)
                        rescheduled_count = 0
                        for pt in pending_tasks:
                            pt.scheduled_date = next_d.isoformat()
                            if not pt.start_time:
                                pt.start_time = "09:00 AM"
                            next_d += timedelta(days=1)
                            rescheduled_count += 1
                        db.commit()

                        tool_executions.append({
                            "id": str(uuid.uuid4()),
                            "toolName": "PlanTaskBatchRescheduler",
                            "status": "success",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "resultSummary": f"Rescheduled {rescheduled_count} unfinished tasks starting tomorrow."
                        })
                        response_content = (
                            f"📅 I have rescheduled **{rescheduled_count} unfinished tasks** in your '**{active_plan.title}**'.\n\n"
                            f"They have been cleanly sequenced starting tomorrow on your Planning Workspace schedule."
                        )
            else:
                search_term = tool_args.get("task_title_search") or tool_args.get("title") or "study"
                time_query = tool_args.get("time_query") or query
                start_dt, end_dt, parsed_meta = parse_natural_datetime(time_query, user_tz_str=user_tz)

                target_date_str = start_dt.date().isoformat()
                target_time_str = start_dt.strftime("%I:%M %p")
                end_time_str = end_dt.strftime("%I:%M %p")

                res = await tool_registry.execute(
                    "plan_update_task",
                    user_id=user_id,
                    db=db,
                    task_title_search=search_term,
                    scheduled_date=target_date_str,
                    start_time=target_time_str,
                    end_time=end_time_str
                )

                if res.get("status") == "success":
                    tool_executions.append({
                        "id": str(uuid.uuid4()),
                        "toolName": "PlanTaskRescheduler",
                        "status": "success",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "resultSummary": f"Rescheduled '{res.get('title')}' to {start_dt.strftime('%b %d at %I:%M %p')}."
                    })
                    cal_sync_note = " Linked Google Calendar event has also been updated." if res.get("calendarSynced") else ""
                    response_content = (
                        f"📅 I've moved your study session '**{res.get('title')}**' to **{start_dt.strftime('%A, %B %d, %Y at %I:%M %p')}** ({res.get('durationMinutes')} mins).\n\n"
                        f"The update is saved in your study plan.{cal_sync_note}"
                    )
                else:
                    response_content = f"I could not locate a study session or task matching *\"{search_term}\"* in your active plan to reschedule."

        # --- PATH 0F: PLAN LIST ---
        elif selected_tool == "plan_list":
            res = await tool_registry.execute("plan_list", user_id=user_id, db=db)
            plans = res.get("plans", [])
            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "StudyPlanListing",
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Retrieved {len(plans)} plans."
            })
            if plans:
                lines = [f"• **{p['title']}** ({p['period']}) — {p['completedTasks']}/{p['taskCount']} milestones completed" for p in plans]
                response_content = "Here are your saved study plans:\n\n" + "\n".join(lines)
            else:
                response_content = "You do not have any saved study plans yet. Ask me to create one, or click Create Plan on the Plans page!"

        # --- PATH 0G: PLAN ADD TASK ---
        elif selected_tool == "plan_add_task":
            title = tool_args.get("title", "New Study Task")
            dur = tool_args.get("duration_minutes", 45)
            if isinstance(dur, str):
                try:
                    dur = int(re.search(r'\d+', dur).group(0))
                except Exception:
                    dur = 45
            dur = int(dur) if dur else 45
            res = await tool_registry.execute("plan_add_task", user_id=user_id, db=db, title=title, duration_minutes=dur)
            if res.get("status") == "success":
                tool_executions.append({
                    "id": str(uuid.uuid4()),
                    "toolName": "PlanTaskAddition",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resultSummary": f"Added task '{title}' ({dur} mins)."
                })
                response_content = f"✅ Added new task **{title}** ({dur} mins) to your active study plan. It is now visible on your **Plan** page."
            else:
                response_content = res.get("message", "Could not add task to plan.")

        # --- PATH 0H: PLAN DELETE TASK ---
        elif selected_tool == "plan_delete_task":
            search_term = tool_args.get("task_title_search", "")
            res = await tool_registry.execute("plan_delete_task", user_id=user_id, db=db, task_title_search=search_term)
            if res.get("status") == "success":
                tool_executions.append({
                    "id": str(uuid.uuid4()),
                    "toolName": "PlanTaskDeletion",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resultSummary": f"Deleted task '{res.get('title')}'."
                })
                response_content = f"🗑️ The task **\"{res.get('title')}\"** has been removed from your study plan."
            else:
                response_content = res.get("message", f"Could not find a task matching *\"{search_term}\"* to delete.")

        # --- PATH 0I: PLAN GET / STATUS (Progress, Pending Tasks, Roadmap Views) ---
        elif selected_tool == "plan_get":
            target_title = tool_args.get("plan_title", "")
            week_number = tool_args.get("week_number")
            daily_study_query = tool_args.get("daily_study_query", False)
            target_date_type = tool_args.get("target_date", "today")

            plan = None
            if target_title:
                plan = db.query(Plan).filter(Plan.user_id == user_id, Plan.title.ilike(f"%{target_title.strip()}%")).first()
            if not plan:
                plan = db.query(Plan).filter(Plan.user_id == user_id).order_by(Plan.updated_at.desc()).first()

            if not plan:
                response_content = "You do not have any saved study plans in your workspace. You can ask me to create one (for example, 'Create a 30-day DSA plan') or visit the **Plan** page!"
            else:
                tasks = db.query(PlanTask).filter(PlanTask.plan_id == plan.id).order_by(PlanTask.task_order, PlanTask.scheduled_date, PlanTask.created_at).all()
                total = len(tasks)
                completed = [t for t in tasks if t.completed]
                pending = [t for t in tasks if not t.completed]
                pct = int(round((len(completed) / total * 100))) if total > 0 else 0

                tool_executions.append({
                    "id": str(uuid.uuid4()),
                    "toolName": "StudyPlanProgressEvaluator",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resultSummary": f"Retrieved status for '{plan.title}': {len(completed)}/{total} completed ({pct}%)."
                })

                lower_q = query.lower()

                # Specific week view (e.g. "Show me week three of my Java plan")
                if week_number:
                    week_tasks = [t for t in tasks if t.week_number == week_number]
                    if week_tasks:
                        w_lines = [f"• {'✅' if t.completed else '◻️'} **{t.title}** ({t.duration_minutes}m) — {t.day_label or t.scheduled_date or 'Study Day'}" for t in week_tasks]
                        w_completed = sum(1 for t in week_tasks if t.completed)
                        response_content = (
                            f"📅 **{plan.title} — Week {week_number} Roadmap:**\n\n"
                            f"**Progress:** {w_completed}/{len(week_tasks)} tasks completed\n"
                            f"**Milestone Goal:** {week_tasks[0].milestone_group or 'Complete core week topics'}\n\n"
                            + "\n".join(w_lines) +
                            f"\n\nInspect the entire multi-month curriculum on your **Plan** page."
                        )
                    else:
                        response_content = f"Week {week_number} was not found in your **{plan.title}** (Total tasks: {total})."

                # What should I study today / tomorrow?
                elif daily_study_query:
                    now_l = datetime.now(timezone.utc).astimezone(zoneinfo.ZoneInfo(user_tz))
                    target_day_d = (now_l.date() + timedelta(days=1)) if target_date_type == "tomorrow" else now_l.date()
                    target_day_str = target_day_d.isoformat()
                    day_label_str = "tomorrow" if target_date_type == "tomorrow" else "today"

                    matching_tasks = [t for t in tasks if t.scheduled_date == target_day_str and not t.completed]
                    if not matching_tasks:
                        # Fallback to next pending task
                        matching_tasks = pending[:2] if pending else []

                    if matching_tasks:
                        t_bullets = [f"• **{t.title}** ({t.duration_minutes}m, priority: {t.priority}) — scheduled for {t.start_time or 'morning'}" for t in matching_tasks]
                        response_content = (
                            f"🎯 **What you should study {day_label_str} for '{plan.title}':**\n\n"
                            + "\n".join(t_bullets) +
                            f"\n\nDaily target: {plan.daily_hours_target or 2.0:g} hours. Mark tasks completed once finished!"
                        )
                    else:
                        response_content = f"🎉 You have no pending study sessions scheduled for {day_label_str} in **{plan.title}**! You're completely caught up."

                elif any(w in lower_q for w in ["pending", "remaining", "left", "todo"]):
                    if pending:
                        p_lines = [f"• **{t.title}** ({t.duration_minutes}m, {t.priority} priority)" for t in pending[:10]]
                        more_note = f"\n• *...and {len(pending) - 10} more pending tasks.*" if len(pending) > 10 else ""
                        response_content = (
                            f"Here are the **{len(pending)} pending tasks** in your '**{plan.title}**' ({pct}% complete):\n\n"
                            + "\n".join(p_lines) + more_note +
                            f"\n\nYou can mark any task complete by saying 'Mark [task] as completed'."
                        )
                    else:
                        response_content = f"🎉 All {total} tasks in your '**{plan.title}**' are completed (100%)! Great job!"

                elif any(w in lower_q for w in ["how much", "progress", "completion", "completed"]):
                    total_hours = sum(t.duration_minutes or 0 for t in tasks) / 60.0
                    comp_hours = sum(t.duration_minutes or 0 for t in completed) / 60.0
                    next_task_note = f"\n• **Next up:** {pending[0].title}" if pending else "\n• All tasks completed!"
                    response_content = (
                        f"📊 **Plan Progress for '{plan.title}'**:\n\n"
                        f"• **Completion:** {pct}%\n"
                        f"• **Study Time:** {comp_hours:.1f}h completed of {total_hours:.1f}h total planned\n"
                        f"• **Completed Milestones:** {len(completed)} of {total}\n"
                        f"• **Pending Milestones:** {len(pending)}{next_task_note}\n\n"
                        f"View detailed breakdown on your **Plan** page."
                    )
                else:
                    sample = tasks[:10]
                    t_lines = [f"• {'✅' if t.completed else '◻️'} **{t.title}** ({t.duration_minutes}m)" for t in sample]
                    more_note = f"\n• *...and {len(tasks) - 10} more tasks across your roadmap.*" if len(tasks) > 10 else ""
                    response_content = (
                        f"**{plan.title}** ({plan.period}) — {pct}% Complete ({len(completed)}/{total} tasks)\n\n"
                        + "\n".join(t_lines) + more_note
                    )

        # --- PATH 0J: PLAN PROPOSE SCHEDULE ---
        elif selected_tool == "plan_propose_schedule":
            target_title = tool_args.get("plan_title", "")
            plan = None
            if target_title:
                plan = db.query(Plan).filter(Plan.user_id == user_id, Plan.title.ilike(f"%{target_title.strip()}%")).first()
            if not plan:
                plan = db.query(Plan).filter(Plan.user_id == user_id).order_by(Plan.updated_at.desc()).first()

            if not plan:
                response_content = "You do not have any saved study plans in your workspace. Ask me to create one first, or click 'Create Plan' on the Plan page!"
            else:
                tasks = db.query(PlanTask).filter(PlanTask.plan_id == plan.id, PlanTask.completed == False).order_by(PlanTask.created_at).all()
                if not tasks:
                    tasks = db.query(PlanTask).filter(PlanTask.plan_id == plan.id).order_by(PlanTask.created_at).all()

                if not tasks:
                    response_content = f"Your study plan '**{plan.title}**' does not have any tasks to schedule. Please add tasks to the plan first."
                else:
                    from app.services.google_services.calendar_service import google_calendar_service
                    from app.db.models import OAuthAccount

                    try:
                        tz_obj = zoneinfo.ZoneInfo(user_tz)
                    except Exception:
                        tz_obj = zoneinfo.ZoneInfo("UTC")

                    now_utc = datetime.now(timezone.utc)
                    cal_oauth = db.query(OAuthAccount).filter(
                        OAuthAccount.user_id == user_id,
                        OAuthAccount.provider.in_(["calendar", "google_all", "google"])
                    ).first()

                    existing_events = []
                    cal_connected = False
                    time_max_days = min(max(plan.duration_days or 30, 30), 183)
                    if cal_oauth:
                        try:
                            c_res = await google_calendar_service.list_events(
                                user_id=user_id,
                                db=db,
                                time_min=now_utc.isoformat(),
                                time_max=(now_utc + timedelta(days=time_max_days)).isoformat()
                            )
                            existing_events = c_res.get("events", [])
                            cal_connected = True
                        except Exception:
                            pass

                    busy = []
                    for ev in existing_events:
                        s_str = ev.get("startTime") or ev.get("start", {}).get("dateTime")
                        e_str = ev.get("endTime") or ev.get("end", {}).get("dateTime")
                        if s_str and e_str and "T" in s_str:
                            try:
                                busy.append((
                                    datetime.fromisoformat(s_str.replace("Z", "+00:00")),
                                    datetime.fromisoformat(e_str.replace("Z", "+00:00"))
                                ))
                            except Exception:
                                pass

                    now_local = now_utc.astimezone(tz_obj)
                    default_cand_date = now_local.date() + timedelta(days=1)
                    proposed_sessions = []
                    blocks_data = []

                    for t in tasks:
                        dur = t.duration_minutes or 60
                        if t.scheduled_date:
                            try:
                                cand_date = date.fromisoformat(t.scheduled_date)
                            except Exception:
                                cand_date = default_cand_date
                        else:
                            cand_date = default_cand_date

                        s_dt = datetime(cand_date.year, cand_date.month, cand_date.day, 9, 0, 0, tzinfo=tz_obj)
                        e_dt = s_dt + timedelta(minutes=dur)

                        s_utc = s_dt.astimezone(timezone.utc)
                        e_utc = e_dt.astimezone(timezone.utc)
                        has_conf = any(s_utc < b_e and e_utc > b_s for b_s, b_e in busy) if cal_connected else False

                        date_label = cand_date.strftime("%A, %b %d")
                        time_label = f"{s_dt.strftime('%I:%M %p').lstrip('0')} – {e_dt.strftime('%I:%M %p').lstrip('0')}"

                        block_dict = {
                            "id": f"block_{len(blocks_data)+1}",
                            "taskId": t.id,
                            "taskTitle": t.title,
                            "focus": t.title,
                            "day": date_label,
                            "date": cand_date.isoformat(),
                            "startTime": s_dt.strftime("%I:%M %p").lstrip("0"),
                            "endTime": e_dt.strftime("%I:%M %p").lstrip("0"),
                            "startIso": s_dt.isoformat(),
                            "endIso": e_dt.isoformat(),
                            "timezone": user_tz,
                            "durationMinutes": dur,
                            "priority": t.priority,
                            "monthNumber": t.month_number,
                            "weekNumber": t.week_number,
                            "dayNumber": t.day_number,
                            "milestoneGroup": t.milestone_group,
                            "hasConflict": has_conf,
                            "conflictFree": not has_conf
                        }
                        blocks_data.append(block_dict)
                        if len(proposed_sessions) < 6:
                            proposed_sessions.append(
                                f"• **{t.title}**: {date_label} at {time_label} ({dur}m) — {'⚠️ Conflict' if has_conf else '✅ Available'}"
                            )
                        if not t.scheduled_date:
                            default_cand_date = cand_date + timedelta(days=1)

                    if len(blocks_data) > 6:
                        proposed_sessions.append(f"• *...and {len(blocks_data) - 6} more proposed study sessions spanning your {plan.period or 'roadmap'}.*")

                    plan.suggested_study_blocks = blocks_data
                    db.commit()

                    tool_executions.append({
                        "id": str(uuid.uuid4()),
                        "toolName": "StudyScheduleProposer",
                        "status": "success",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "resultSummary": f"Proposed {len(blocks_data)} study sessions for '{plan.title}'."
                    })

                    conf_count = sum(1 for b in blocks_data if b["hasConflict"])
                    cal_status_str = "Checked against your real Google Calendar." if cal_connected else "Calendar not connected (live conflict checking unavailable)."
                    response_content = (
                        f"📅 I've generated a proposed study schedule for '**{plan.title}**':\n\n"
                        + "\n".join(proposed_sessions) +
                        f"\n\n**Schedule Status:** {cal_status_str}"
                        + (f"\n⚠️ **Note:** {conf_count} session(s) overlap with existing calendar events." if conf_count else "\n✅ **All proposed intervals are free of conflicts.**") +
                        f"\n\nThese sessions are saved as proposals in your workspace and have **NOT** been added to Google Calendar. "
                        f"You can review them on the **Plan** page or say 'Add the selected study sessions to Google Calendar' to sync them."
                    )

        # --- PATH 0K: PLAN SYNC CALENDAR ---
        elif selected_tool == "plan_sync_calendar":
            confirmed = tool_args.get("confirmed", False)
            target_title = tool_args.get("plan_title", "")
            plan = None
            if target_title:
                plan = db.query(Plan).filter(Plan.user_id == user_id, Plan.title.ilike(f"%{target_title.strip()}%")).first()
            if not plan:
                plan = db.query(Plan).filter(Plan.user_id == user_id).order_by(Plan.updated_at.desc()).first()

            if not plan:
                response_content = "You do not have any saved study plans to synchronize."
            else:
                blocks = plan.suggested_study_blocks or []
                if not blocks:
                    response_content = (
                        f"Your study plan '**{plan.title}**' doesn't have any proposed study sessions yet. "
                        f"Ask me to 'Generate a schedule for my plan' first, review the proposed times, and then sync them."
                    )
                elif not confirmed:
                    suggested_action = {
                        "id": str(uuid.uuid4()),
                        "actionType": "sync_plan_calendar",
                        "title": f"Sync {len(blocks)} Study Sessions to Google Calendar ({plan.title})",
                        "details": {
                            "planId": plan.id,
                            "planTitle": plan.title,
                            "sessionCount": f"{len(blocks)} study sessions",
                            "dateRange": f"{blocks[0].get('day', '')} to {blocks[-1].get('day', '')}" if blocks else "Upcoming",
                            "timezone": user_tz,
                            "calendar": "Primary Google Calendar",
                            "studyBlocks": blocks,
                            "selectedBlockIds": [b["id"] for b in blocks],
                        },
                        "status": "pending"
                    }
                    tool_executions.append({
                        "id": str(uuid.uuid4()),
                        "toolName": "CalendarSyncConfirmationGuard",
                        "status": "success",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "resultSummary": f"Awaiting user confirmation to add {len(blocks)} sessions to Google Calendar."
                    })
                    response_content = (
                        f"⚠️ **Google Calendar Synchronization Confirmation**\n\n"
                        f"I have prepared **{len(blocks)} study sessions** from '**{plan.title}**' ready to sync with your Google Calendar.\n\n"
                        f"• **Plan:** {plan.title}\n"
                        f"• **Sessions:** {len(blocks)} scheduled blocks\n"
                        f"• **Calendar:** Primary Google Calendar\n"
                        f"• **Timezone:** {user_tz}\n\n"
                        f"Please click **Confirm & Commit Action** below to write these events to your Google Calendar."
                    )
                else:
                    from app.services.google_services.calendar_service import google_calendar_service
                    synced = 0
                    failed = 0
                    for b in blocks:
                        task_id = b.get("taskId")
                        task = db.query(PlanTask).filter(PlanTask.id == task_id).first() if task_id else None
                        if task and task.google_calendar_event_id:
                            continue
                        try:
                            cal_res = await google_calendar_service.create_event_direct(
                                user_id=user_id,
                                db=db,
                                title=b.get("taskTitle") or b.get("focus") or plan.title,
                                start_time=b.get("startIso"),
                                end_time=b.get("endIso"),
                                description=f"AURELIA Study Session: {plan.title}"
                            )
                            ev_id = cal_res.get("eventId")
                            if ev_id and task:
                                task.google_calendar_event_id = ev_id
                                db.commit()
                            synced += 1
                        except Exception:
                            failed += 1

                    tool_executions.append({
                        "id": str(uuid.uuid4()),
                        "toolName": "PlanCalendarSynchronizer",
                        "status": "success",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "resultSummary": f"Synced {synced} sessions to Google Calendar ({failed} failed)."
                    })
                    response_content = (
                        f"✅ Successfully synchronized **{synced} study sessions** from '**{plan.title}**' to your Google Calendar!"
                        + (f" ({failed} sessions failed to sync; you can retry them from the Plan page.)" if failed else "")
                    )

        # --- PATH 1: MULTI-SERVICE PLANNER ---
        elif selected_tool == "multi_service_planner":
            target_date_str = tool_args.get("target_date", "tomorrow")
            start_dt, _, _ = parse_natural_datetime(target_date_str, user_tz_str=user_tz)
            time_min = start_dt.replace(hour=0, minute=0, second=0).isoformat()
            time_max = start_dt.replace(hour=23, minute=59, second=59).isoformat()

            # Execute Calendar Tool
            cal_res = await tool_registry.execute(
                "calendar_events_retrieval",
                user_id=user_id,
                db=db,
                time_min=time_min,
                time_max=time_max
            )
            cal_events = cal_res.get("events", [])
            cal_live = cal_res.get("isLive", False)

            # Execute Gmail Tool
            gmail_res = await tool_registry.execute(
                "gmail_priority_messages",
                user_id=user_id,
                db=db,
                query="deadline OR assignment OR project OR exam OR sync"
            )
            emails = gmail_res.get("messages", [])
            gmail_live = gmail_res.get("isLive", False)

            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "CalendarEventRetrieval",
                "status": "success" if cal_live else cal_res.get("status", "failed"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Retrieved {len(cal_events)} scheduled events for {start_dt.strftime('%A, %b %d')}."
            })
            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "GmailMessageSearch",
                "status": "success" if gmail_live else gmail_res.get("status", "failed"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Scanned {len(emails)} priority emails for deadlines."
            })

            for ev in cal_events:
                citations.append({
                    "id": str(uuid.uuid4()),
                    "sourceType": "calendar",
                    "title": ev.get("title", "Event"),
                    "snippet": f"Time: {ev.get('startTime', 'TBD')} – {ev.get('endTime', 'TBD')} ({ev.get('location', 'Online')})"
                })
            for m in emails[:3]:
                citations.append({
                    "id": str(uuid.uuid4()),
                    "sourceType": "email",
                    "title": f"Email: {m.get('fromName', 'Sender')}",
                    "snippet": f"{m.get('subject', '')}: {m.get('snippet', '')[:120]}",
                    "url": m.get("gmailLink", "https://mail.google.com")
                })

            # Propose a study slot in open time (e.g., 6:00 PM – 8:00 PM)
            prop_res = await tool_registry.execute(
                "calendar_propose_event",
                user_id=user_id,
                db=db,
                title="Targeted Study Block (CS-702)",
                start_time=start_dt.replace(hour=18, minute=0, second=0).isoformat(),
                duration_mins=120,
                location="Quiet Focus Area"
            )

            if prop_res.get("previewEvent"):
                suggested_action = {
                    "id": str(uuid.uuid4()),
                    "actionType": "create_event",
                    "title": "Add Proposed Study Block to Calendar",
                    "confirmationToken": prop_res.get("confirmationToken"),  # top-level, NOT inside details
                    "details": {
                        "title": prop_res["previewEvent"]["title"],
                        "startTime": prop_res["previewEvent"]["startTime"],
                        "duration": "120 minutes (6:00 PM – 8:00 PM)",
                        "location": "Quiet Focus Area",
                        "conflicts": "None detected",
                    },
                    "status": "pending"
                }

            events_text = "\n".join([f"• **{e['title']}**: {e.get('startTime', '')[11:16]} – {e.get('endTime', '')[11:16]}" for e in cal_events]) or "No existing meetings scheduled."
            emails_text = "\n".join([f"• **{m.get('fromName')}**: {m.get('subject')} (Excerpt: {m.get('snippet', '')[:100]}...)" for m in emails[:3]]) or "No pending deadline emails found."

            if settings.GEMINI_API_KEY:
                user_prompt = (
                    f"{history_context}"
                    f"[Tomorrow's Calendar Events]\n{events_text}\n\n"
                    f"[Recent Email Deadlines & Tasks]\n{emails_text}\n\n"
                    f"[User Request]\n{query}\n\n"
                    "INSTRUCTIONS:\n"
                    "1. Present the existing calendar commitments clearly.\n"
                    "2. Detail the deadlines and academic tasks extracted from emails.\n"
                    "3. Propose a realistic, conflict-free study schedule built around existing meetings.\n"
                    "4. Inform the user that an event proposal has been created and can be confirmed with one click."
                )
                gemini_res = await call_gemini_api(user_prompt, AURELIA_SYSTEM_PROMPT)
                if gemini_res.success and gemini_res.text:
                    response_content = gemini_res.text
                else:
                    response_content = (
                        f"### Multi-Service Schedule Synthesis for Tomorrow\n\n"
                        f"**1. Existing Calendar Commitments:**\n{events_text}\n\n"
                        f"**2. Deadlines Identified in Emails:**\n{emails_text}\n\n"
                        f"**3. Proposed Study Plan:**\n"
                        f"• Focus Study Session from **6:00 PM to 8:00 PM** (avoids existing classes/meetings).\n\n"
                        f"Please review the proposed study session below and confirm to write it to your Google Calendar."
                    )
            else:
                response_content = (
                    f"### Multi-Service Schedule Synthesis for Tomorrow\n\n"
                    f"**1. Existing Calendar Commitments:**\n{events_text}\n\n"
                    f"**2. Deadlines Identified in Emails:**\n{emails_text}\n\n"
                    f"**3. Proposed Study Plan:**\n"
                    f"• Focus Study Session from **6:00 PM to 8:00 PM** (avoids existing classes/meetings).\n\n"
                    f"Please review the proposed study session below and confirm to write it to your Google Calendar."
                )

        # --- PATH 2: CALENDAR PERSONAL LEAVE / HOLIDAY ---
        elif selected_tool == "calendar_mark_leave":
            leave_info = tool_args
            target_date_str = leave_info.get("target_date")
            start_dt, _, _ = parse_natural_datetime(target_date_str or "tomorrow", user_tz_str=user_tz)
            date_display = leave_info.get("date_str") or start_dt.strftime("%A, %B %d, %Y")
            reason = leave_info.get("title") or "Personal Leave / Sick Day"

            # Check existing calendar events for that day
            t_min = start_dt.replace(hour=0, minute=0, second=0).isoformat()
            t_max = start_dt.replace(hour=23, minute=59, second=59).isoformat()
            cal_res = await tool_registry.execute(
                "calendar_events_retrieval",
                user_id=user_id,
                db=db,
                time_min=t_min,
                time_max=t_max
            )
            existing_events = cal_res.get("events", [])
            study_events = [e for e in existing_events if any(k in e.get("title", "").lower() for k in ["study", "prep", "reading", "focus", "homework"])]

            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "CalendarLeaveManager",
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Identified {len(existing_events)} total events and {len(study_events)} study sessions for {date_display}."
            })

            # Propose creating all-day personal leave event (is_all_day=True, hour=0 so date is exact)
            leave_prop = await tool_registry.execute(
                "calendar_propose_event",
                user_id=user_id,
                db=db,
                title=reason,
                start_time=start_dt.replace(hour=0, minute=0, second=0).isoformat(),
                is_all_day=True,
                location="Out of Office / Home Recovery"
            )

            suggested_action = {
                "id": str(uuid.uuid4()),
                "actionType": "create_event",
                "title": f"Confirm {reason} for {date_display}",
                "confirmationToken": leave_prop.get("confirmationToken"),  # top-level, NOT inside details
                "details": {
                    "title": reason,
                    "date": date_display,
                    "type": "All-Day Personal Leave",
                    "calendar": "Primary Google Calendar",
                    "isAllDay": True,
                    "location": "Out of Office / Home Recovery"
                },
                "status": "pending"
            }

            study_notice = ""
            if leave_info.get("remove_study_sessions"):
                if study_events:
                    study_notice = f"\n\nAs requested, I identified **{len(study_events)} study session(s)** on your schedule for {date_display} that can be cleared:\n" + "\n".join([f"• *{s['title']}* ({s.get('startTime', '')[11:16]} – {s.get('endTime', '')[11:16]})" for s in study_events])
                else:
                    study_notice = f"\n\nI checked your calendar and found **no existing study sessions** scheduled for {date_display} to remove."
            else:
                if study_events:
                    study_notice = f"\n\nYou have **{len(study_events)} study session(s)** scheduled for {date_display}. Would you like me to cancel them or reschedule them to later in the week?"

            response_content = (
                f"I'm sorry to hear you're unwell. I have prepared an all-day **{reason}** entry for **{date_display}** on your Google Calendar to mark your personal unavailability."
                f"{study_notice}\n\n"
                f"Please review the confirmation card below and click **Confirm** to record this leave on your calendar. Rest up and feel better soon!"
            )

        # --- PATH 3: CALENDAR EVENT PROPOSAL (Multi-interval or Single) ---
        elif selected_tool == "calendar_propose_event":
            intervals = parse_natural_time_intervals(query, user_tz_str=user_tz)
            if len(intervals) >= 2:
                # Multiple study intervals requested (e.g. 7-9 AM and 6-8 PM)
                prop_details = []
                conflict_found = False
                first_token = None
                for s_dt, e_dt, meta in intervals:
                    dur = meta["durationMinutes"]
                    time_label = f"Study Session ({s_dt.strftime('%I:%M %p').lstrip('0')} – {e_dt.strftime('%I:%M %p').lstrip('0')})"
                    p_res = await tool_registry.execute(
                        "calendar_propose_event",
                        user_id=user_id,
                        db=db,
                        title=time_label,
                        start_time=s_dt.isoformat(),
                        duration_mins=dur,
                        location="Quiet Focus Area"
                    )
                    if not first_token:
                        first_token = p_res.get("confirmationToken")
                    if p_res.get("hasConflict"):
                        conflict_found = True
                    prop_details.append(f"• **{time_label}**: {s_dt.strftime('%A, %b %d')} ({dur} mins) — {'⚠️ Conflict' if p_res.get('hasConflict') else '✅ Clear'}")

                tool_executions.append({
                    "id": str(uuid.uuid4()),
                    "toolName": "MultiIntervalCalendarScheduler",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resultSummary": f"Evaluated availability for {len(intervals)} study sessions."
                })

                suggested_action = {
                    "id": str(uuid.uuid4()),
                    "actionType": "create_event",
                    "title": f"Confirm {len(intervals)} Scheduled Study Sessions",
                    "confirmationToken": first_token,  # top-level, NOT inside details
                    "details": {
                        "sessions": [m[2]["start"][11:16] + " to " + m[2]["end"][11:16] for m in intervals],
                        "conflictCheck": "⚠️ Some conflicts detected" if conflict_found else "✅ Zero conflicts detected",
                    },
                    "status": "pending"
                }

                response_content = (
                    f"I evaluated your schedule for tomorrow and prepared the requested study intervals:\n\n"
                    + "\n".join(prop_details) +
                    f"\n\n{'⚠️ **Note:** One of the blocks overlaps with existing calendar commitments.' if conflict_found else '✅ **Availability Confirmed:** Both intervals are completely free.'}\n\n"
                    f"Click **Confirm** below to write these sessions directly to your Google Calendar."
                )
            else:
                # Single event proposal
                # Use LLM-extracted title, but fall back to deterministic extractor for generic defaults
                _raw_title = tool_args.get("title", "")
                _generic_titles = {"study session", "personal focus block", "event", "meeting", "calendar event", ""}
                if not _raw_title or _raw_title.lower().strip() in _generic_titles:
                    title = extract_calendar_event_title(query)
                else:
                    title = _raw_title

                start_time_str = tool_args.get("start_time")
                if not start_time_str or not start_time_str.startswith("20"):
                    s_dt, _, _ = parse_natural_datetime(query, user_tz_str=user_tz)
                    start_time_str = s_dt.isoformat()

                duration = tool_args.get("duration_mins", 60)
                location = tool_args.get("location", "")

                prop_res = await tool_registry.execute(
                    "calendar_propose_event",
                    user_id=user_id,
                    db=db,
                    title=title,
                    start_time=start_time_str,
                    duration_mins=duration,
                    location=location
                )

                if prop_res.get("status") == "capability_disabled":
                    response_content = prop_res.get("message")
                elif prop_res.get("status") == "error":
                    response_content = f"Could not schedule event: {prop_res.get('message')}"
                else:
                    is_conflict = prop_res.get("hasConflict", False)
                    token = prop_res.get("confirmationToken")

                    tool_executions.append({
                        "id": str(uuid.uuid4()),
                        "toolName": "CalendarConflictEvaluator",
                        "status": "success",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "resultSummary": f"Evaluated schedule conflicts for '{title}'."
                    })

                    # Build human-readable date and time labels from the ISO timestamp
                    try:
                        import zoneinfo as _zi
                        _tz_obj = _zi.ZoneInfo(user_tz)
                        _start_dt = datetime.fromisoformat(start_time_str).astimezone(_tz_obj)
                        _date_label = _start_dt.strftime("%-d %B %Y") if hasattr(_start_dt, "strftime") else _start_dt.strftime("%d %B %Y").lstrip("0")
                        # Use OS-portable strftime: strip leading zero manually
                        _hour = int(_start_dt.strftime("%I"))
                        _ampm = _start_dt.strftime("%p")
                        _min_str = _start_dt.strftime("%M")
                        _time_label = f"{_hour}:{_min_str} {_ampm}" if _min_str != "00" else f"{_hour} {_ampm}"
                        # Timezone abbreviation
                        try:
                            _tz_abbr = _start_dt.strftime("%Z")
                        except Exception:
                            _tz_abbr = user_tz
                        _time_label_tz = f"{_time_label} {_tz_abbr}"
                    except Exception:
                        _date_label = start_time_str[:10]
                        _time_label_tz = start_time_str[11:16]

                    suggested_action = {
                        "id": str(uuid.uuid4()),
                        "actionType": "create_event",
                        "title": title,
                        "confirmationToken": token,  # top-level, NOT inside details
                        "details": {
                            "title": title,
                            "date": _date_label,
                            "time": _time_label_tz,
                            "timezone": user_tz,
                            "duration": f"{duration} minutes",
                            "location": location if location else None,
                            "calendar": "Primary Google Calendar",
                        },
                        "status": "pending"
                    }
                    # Remove None values from details so frontend filter(Boolean) works correctly
                    suggested_action["details"] = {k: v for k, v in suggested_action["details"].items() if v is not None}

                    conflict_note = "⚠️ **Warning: Overlaps with an existing event.**" if is_conflict else "✅ **No scheduling conflicts detected.**"
                    response_content = (
                        f"I've prepared a calendar event for **{title}**:\n\n"
                        f"• **Date:** {_date_label}\n"
                        f"• **Time:** {_time_label_tz}\n"
                        f"• **Duration:** {duration} mins\n"
                        f"• **Conflict Check:** {conflict_note}\n\n"
                        "Review the proposal below and click **Confirm** to add it to your Google Calendar."
                    )

        # --- PATH 3B: CALENDAR EVENT DELETION ---
        elif selected_tool == "calendar_delete_event":
            target_title = tool_args.get("event_title") or tool_args.get("title", "")
            confirmed = tool_args.get("confirmed", False)
            event_id = tool_args.get("event_id")

            if not is_capability_enabled(user_id, "calendar", "delete_events", db):
                response_content = "The 'Delete & Cancel Events' capability is disabled in your Aurelia Settings. Please enable it under Settings > Integrations."
            else:
                matching_event = None
                if not event_id:
                    s_dt, _, _ = parse_natural_datetime(query, user_tz_str=user_tz)
                    t_min = (s_dt - timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat()
                    t_max = (s_dt + timedelta(days=3)).replace(hour=23, minute=59, second=59).isoformat()
                    cal_res = await tool_registry.execute(
                        "calendar_events_retrieval",
                        user_id=user_id,
                        db=db,
                        time_min=t_min,
                        time_max=t_max
                    )
                    events = cal_res.get("events", [])
                    term = target_title.lower().strip()
                    for ev in events:
                        ev_lower = ev.get("title", "").lower()
                        if term and (term in ev_lower or ev_lower in term):
                            matching_event = ev
                            break
                    if not matching_event and events:
                        matching_event = events[0]

                if matching_event:
                    event_id = matching_event.get("id")
                    ev_title = matching_event.get("title", "Calendar Event")
                    ev_time = matching_event.get("startTime", "")[:16].replace("T", " ")
                else:
                    ev_title = target_title or "Calendar Event"
                    ev_time = "Scheduled Time"

                if not event_id and not matching_event:
                    response_content = f"I could not locate an event matching *\"{target_title or 'your request'}\"* on your Google Calendar to cancel. Please check your Calendar page."
                elif not confirmed:
                    suggested_action = {
                        "id": str(uuid.uuid4()),
                        "actionType": "delete_event",
                        "title": f"Cancel Event: {ev_title}",
                        "details": {
                            "eventId": event_id,
                            "title": ev_title,
                            "time": ev_time,
                            "calendar": "Primary Google Calendar",
                            "warning": "This will remove the event from your Google Calendar."
                        },
                        "status": "pending"
                    }
                    tool_executions.append({
                        "id": str(uuid.uuid4()),
                        "toolName": "CalendarDeletionGuard",
                        "status": "success",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "resultSummary": f"Awaiting user confirmation to cancel event '{ev_title}'."
                    })
                    response_content = (
                        f"⚠️ **Confirmation Required**\n\n"
                        f"Are you sure you want to cancel the event '**{ev_title}**' ({ev_time}) from your Google Calendar?\n\n"
                        f"Please click **Confirm & Commit Action** below to remove this event."
                    )
                else:
                    del_res = await tool_registry.execute("calendar_delete_event", user_id=user_id, db=db, event_id=event_id)
                    tool_executions.append({
                        "id": str(uuid.uuid4()),
                        "toolName": "CalendarEventDeletion",
                        "status": "success" if del_res.get("deleted") or del_res.get("status") == "success" else "failed",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "resultSummary": f"Deleted event '{ev_title}'."
                    })
                    if del_res.get("deleted") or del_res.get("status") == "success":
                        response_content = f"🗑️ The event '**{ev_title}**' has been cancelled and removed from your Google Calendar."
                    else:
                        response_content = f"Could not cancel event: {del_res.get('message', 'Unknown error')}"

        # --- PATH 3C: CALENDAR EVENT UPDATE / RESCHEDULE ---
        elif selected_tool == "calendar_update_event":
            target_title = tool_args.get("event_title") or tool_args.get("title") or tool_args.get("event_name", "")
            time_query = tool_args.get("new_time") or query
            s_dt, e_dt, _ = parse_natural_datetime(time_query, user_tz_str=user_tz)

            if not is_capability_enabled(user_id, "calendar", "edit_events", db):
                response_content = "The 'Edit & Reschedule Events' capability is disabled in your Aurelia Settings. Please enable it under Settings > Integrations."
            else:
                t_min = (s_dt - timedelta(days=2)).replace(hour=0, minute=0, second=0).isoformat()
                t_max = (s_dt + timedelta(days=3)).replace(hour=23, minute=59, second=59).isoformat()
                cal_res = await tool_registry.execute("calendar_events_retrieval", user_id=user_id, db=db, time_min=t_min, time_max=t_max)
                events = cal_res.get("events", [])
                matched = None
                term = target_title.lower().strip()
                for ev in events:
                    if term and term in ev.get("title", "").lower():
                        matched = ev
                        break
                if not matched and events:
                    matched = events[0]

                if matched:
                    up_res = await tool_registry.execute(
                        "calendar_update_event",
                        user_id=user_id,
                        db=db,
                        event_id=matched["id"],
                        start_time=s_dt.isoformat(),
                        end_time=e_dt.isoformat()
                    )
                    if up_res.get("status") == "success":
                        tool_executions.append({
                            "id": str(uuid.uuid4()),
                            "toolName": "CalendarEventRescheduler",
                            "status": "success",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "resultSummary": f"Rescheduled '{matched['title']}' to {s_dt.strftime('%b %d at %I:%M %p')}."
                        })
                        response_content = f"📅 I've rescheduled **{matched['title']}** to **{s_dt.strftime('%A, %B %d, %Y at %I:%M %p')}** on your Google Calendar."
                    else:
                        response_content = f"Could not update event: {up_res.get('message', 'Update failed')}"
                else:
                    response_content = f"I could not locate an event matching *\"{target_title or 'your request'}\"* on your Google Calendar to reschedule."

        # --- PATH 4: GMAIL SEARCH AND SUMMARIZE ---
        elif selected_tool == "gmail_search_and_summarize":
            search_query = tool_args.get("query", "academic")
            g_res = await tool_registry.execute(
                "gmail_priority_messages",
                user_id=user_id,
                db=db,
                query=search_query
            )
            messages = g_res.get("messages", [])
            is_live = g_res.get("isLive", False)

            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "GmailMessageSearch",
                "status": "success" if is_live else g_res.get("status", "failed"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Retrieved {len(messages)} messages from Gmail."
            })

            if not is_live:
                if g_res.get("status") == "capability_disabled":
                    response_content = g_res.get("message")
                else:
                    response_content = "Your Gmail account is not connected. Please connect Gmail in Workspace Integrations to search and summarize emails."
            elif messages:
                for m in messages[:4]:
                    citations.append({
                        "id": str(uuid.uuid4()),
                        "sourceType": "email",
                        "title": f"Email: {m.get('fromName', 'Sender')}",
                        "snippet": f"{m.get('subject', '')}: {m.get('snippet', '')[:120]}",
                        "url": m.get("gmailLink", "https://mail.google.com")
                    })

                if settings.GEMINI_API_KEY:
                    msg_blocks = "\n\n".join([
                        f"Email {i+1}:\nFrom: {m.get('fromName')} <{m.get('fromEmail')}>\nDate: {m.get('date')}\nSubject: {m.get('subject')}\nSnippet: {m.get('snippet')}"
                        for i, m in enumerate(messages[:5])
                    ])
                    user_prompt = (
                        f"{history_context}[Retrieved Gmail Messages]\n{msg_blocks}\n\n"
                        f"[User Request]\n{query}\n\n"
                        "INSTRUCTIONS:\n"
                        "1. Answer the user's question directly based on the emails above.\n"
                        "2. If the user asked for deadlines or tasks, enumerate every deadline, assignment, and action item with dates.\n"
                        "3. If summarizing, highlight key decisions, sender, and follow-ups accurately.\n"
                        "4. Never invent senders, deadlines, or email contents."
                    )
                    gemini_res = await call_gemini_api(user_prompt, AURELIA_SYSTEM_PROMPT)
                    if gemini_res.success and gemini_res.text:
                        response_content = gemini_res.text
                    else:
                        lines = [f"• **{m.get('fromName', 'Sender')}** — *{m.get('subject')}*\n  _{m.get('snippet', '')[:120]}..._" for m in messages[:4]]
                        response_content = "Here are the relevant emails found in your inbox:\n\n" + "\n\n".join(lines)
                else:
                    lines = [f"• **{m.get('fromName', 'Sender')}** — *{m.get('subject')}*\n  _{m.get('snippet', '')[:120]}..._" for m in messages[:4]]
                    response_content = "Here are the relevant emails found in your inbox:\n\n" + "\n\n".join(lines)
            else:
                response_content = f"No emails matching *\"{search_query}\"* were found in your connected Gmail inbox."

        # --- PATH 5: GMAIL SEND MESSAGE (Confirmation Enforcement) ---
        elif selected_tool == "gmail_send_message":
            token = tool_args.get("confirmation_token")
            if token:
                send_res = await tool_registry.execute(
                    "gmail_send_message",
                    user_id=user_id,
                    db=db,
                    confirmation_token=token
                )
                if send_res.get("status") == "capability_disabled":
                    response_content = send_res.get("message")
                elif send_res.get("status") == "success":
                    msg_id = send_res.get("sendResult", {}).get("messageId", "")
                    response_content = f"✅ **Email successfully dispatched via Gmail!**\n\n• Message Reference: `{msg_id}`\n• Recipient: `{send_res.get('sendResult', {}).get('to')}`\n• Subject: {send_res.get('sendResult', {}).get('subject')}"
                else:
                    response_content = f"❌ **Email delivery failed:** {send_res.get('message', 'Unknown transmission error')}"
            else:
                # Require explicit confirmation before sending
                recipient = tool_args.get("to")
                if not recipient or "@" not in recipient:
                    em = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', query)
                    recipient = em.group(0) if em else "recipient@university.edu"

                subject = tool_args.get("subject")
                if not subject:
                    sm = re.search(r'(?:about|regarding|subject[:\s]+)([^.\n]+)', query, re.IGNORECASE)
                    subject = sm.group(1).strip().capitalize() if sm else "Academic Update"

                body = tool_args.get("body")
                if not body and settings.GEMINI_API_KEY:
                    from app.prompts.gmail import GMAIL_DRAFT_PROMPT
                    draft_prompt = (
                        f"{history_context}"
                        f"Recipient: {recipient}\n"
                        f"Subject: {subject}\n"
                        f"User Request: {query}\n\n"
                        "Draft a professional, concise email body matching the user's intent. "
                        "Return ONLY the plain text email body without headers or markdown fencing."
                    )
                    gem_res = await call_gemini_api(draft_prompt, GMAIL_DRAFT_PROMPT)
                    if gem_res.success and gem_res.text:
                        body = gem_res.text.strip()

                if not body:
                    body = (
                        f"Hello,\n\n"
                        f"I am writing regarding: {subject}.\n\n"
                        f"Please review and let me know if you have any questions.\n\n"
                        f"Best regards,\nAlex Chen"
                    )

                prep = google_gmail_service.prepare_send_confirmation(
                    user_id=user_id,
                    to=recipient,
                    subject=subject,
                    body=body
                )

                suggested_action = {
                    "id": str(uuid.uuid4()),
                    "actionType": "send_email",
                    "title": f"Approval Required: Send Email to {recipient}",
                    "confirmationToken": prep["confirmationToken"],  # top-level, NOT inside details
                    "details": {
                        "to": recipient,
                        "subject": subject,
                        "bodyPreview": body[:200] + ("..." if len(body) > 200 else ""),
                        "service": "Google Gmail API",
                        "note": "AURELIA will never dispatch emails without explicit confirmation."
                    },
                    "status": "pending"
                }

                tool_executions.append({
                    "id": str(uuid.uuid4()),
                    "toolName": "GmailSendGuard",
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resultSummary": f"Awaiting user approval to send email to {recipient}."
                })

                response_content = (
                    f"Please review the email details before sending:\n\n"
                    f"• **To:** `{recipient}`\n"
                    f"• **Subject:** `{subject}`\n\n"
                    f"> {body.replace(chr(10), chr(10) + '> ')}\n\n"
                    "🔒 **Security Guard:** Click **Confirm & Commit Action** on the card below to confirm transmission via your authorized Gmail account."
                )

        # --- PATH 6: DRIVE SEARCH & READ ---
        elif selected_tool in ("drive_search_and_read", "drive_search_files"):
            search_term = tool_args.get("query", query)
            drive_res = await tool_registry.execute("drive_search_files", user_id=user_id, db=db, query=search_term)
            files = drive_res.get("files", [])
            is_live = drive_res.get("isLive", False)

            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "GoogleDriveSearch",
                "status": "success" if is_live else drive_res.get("status", "failed"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Retrieved {len(files)} files matching '{search_term}'."
            })

            if not is_live:
                if drive_res.get("status") == "capability_disabled":
                    response_content = drive_res.get("message")
                else:
                    response_content = "Your Google Drive account is not connected. Please connect Google Drive in Workspace Integrations to search your files."
            elif files:
                top_file = files[0]
                file_id = top_file.get("id")
                file_name = top_file.get("name")
                for f_item in files[:4]:
                    citations.append({
                        "id": str(uuid.uuid4()),
                        "sourceType": "google_drive",
                        "title": f_item.get("name"),
                        "snippet": f"Type: {f_item.get('mimeType', 'file')} • Modified: {f_item.get('modifiedTime', '')[:10]}",
                        "url": f_item.get("webViewLink", "https://drive.google.com")
                    })

                # If read requested, read the actual content!
                if tool_args.get("read_content", True):
                    read_res = await tool_registry.execute("drive_read_file", user_id=user_id, db=db, file_id=file_id)
                    if read_res.get("status") == "capability_disabled":
                        response_content = read_res.get("message")
                    elif read_res.get("content"):
                        content_text = read_res["content"]
                        tool_executions.append({
                            "id": str(uuid.uuid4()),
                            "toolName": "GoogleDriveContentExtractor",
                            "status": "success",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "resultSummary": f"Extracted {len(content_text)} characters from '{file_name}'."
                        })

                        if settings.GEMINI_API_KEY:
                            user_prompt = (
                                f"{history_context}"
                                f"[Document Content from Google Drive: {file_name}]\n{content_text[:4000]}\n\n"
                                f"[User Request]\n{query}\n\n"
                                "INSTRUCTIONS:\n"
                                "1. Answer the user's question directly based on the extracted Drive content above.\n"
                                "2. Ground facts strictly on what is written in the document.\n"
                                "3. Provide a clear, evidence-based answer and cite the file name."
                            )
                            gemini_res = await call_gemini_api(user_prompt, AURELIA_SYSTEM_PROMPT)
                            if gemini_res.success and gemini_res.text:
                                response_content = gemini_res.text
                            else:
                                response_content = f"**Document Summary for {file_name}:**\n\n{content_text[:800]}..."
                        else:
                            response_content = f"**Document Summary for {file_name}:**\n\n{content_text[:800]}..."
                    else:
                        response_content = f"Found file **{file_name}** in Google Drive. Direct text extraction is unsupported for this format."
                else:
                    file_lines = "\n".join([f"• **{f['name']}** ({f.get('modifiedTime', '')[:10]})" for f in files[:5]])
                    response_content = f"Found {len(files)} matching file(s) in your Google Drive:\n\n{file_lines}"
            else:
                response_content = f"No documents found in your connected Google Drive matching *\"{search_term}\"*."

        # --- PATH 6B: DOCUMENT INVENTORY & METADATA DISCOVERY (Knowledge Base) ---
        elif selected_tool == "document_inventory":
            inv_res = await tool_registry.execute(
                "document_inventory",
                user_id=user_id,
                db=db,
                query=tool_args.get("query", query),
                category=tool_args.get("category"),
                status=tool_args.get("status")
            )
            docs = inv_res.get("documents", [])
            total_count = inv_res.get("totalCount", 0)
            matching_count = inv_res.get("matchingCount", 0)
            queried_kw = inv_res.get("queriedKeyword")

            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "DocumentInventoryDiscovery",
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Discovered {matching_count} matching documents of {total_count} total stored."
            })

            for d in docs[:5]:
                citations.append({
                    "id": str(uuid.uuid4()),
                    "sourceType": "document",
                    "title": d["filename"],
                    "snippet": f"Category: {d.get('category') or 'General'} • Status: {d.get('status')} • Size: {d.get('fileSize') or 0} bytes • Chunks: {d.get('chunkCount') or 0} • Uploaded: {d.get('uploadedAt') or 'N/A'}",
                    "documentId": d["id"]
                })

            if total_count == 0:
                response_content = (
                    "You have not uploaded any documents to your Knowledge Base yet. "
                    "You can upload lecture notes, syllabi, study materials, or textbooks on the **Knowledge Base** page!"
                )
            elif matching_count == 0 and queried_kw:
                response_content = (
                    f"You have **{total_count} document(s)** stored in your Knowledge Base, but none match *\"{queried_kw}\"*.\n\n"
                    f"You can view and manage all your documents on the **Knowledge Base** page."
                )
            else:
                doc_lines = []
                for d in docs:
                    size_kb = f"{round((d['fileSize'] or 0) / 1024, 1)} KB" if d.get('fileSize') else "Unknown size"
                    doc_lines.append(
                        f"• **{d['filename']}** ({size_kb})\n"
                        f"  – Category: `{d.get('category') or 'General'}` | Status: `{d.get('status')}` | Chunks: `{d.get('chunkCount') or 0}` | Uploaded: {d.get('uploadedAt') or 'Recent'}"
                    )
                heading = f"You have **{total_count} document(s)** stored in your Knowledge Base"
                if queried_kw and matching_count < total_count:
                    heading = f"Found **{matching_count} document(s)** matching *\"{queried_kw}\"* in your Knowledge Base (out of {total_count} total)"
                response_content = f"{heading}:\n\n" + "\n\n".join(doc_lines)

        # --- PATH 7: DOCUMENT SUMMARY (Knowledge Base) ---
        elif selected_tool == "document_summary":
            doc_q = tool_args.get("document_query", query)
            summary_res = await summarize_document(user_id=user_id, db=db, document_query=doc_q)
            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "DocumentAnalysisEngine",
                "status": "success" if summary_res.get("status") == "success" else "not_found",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Analyzed document '{summary_res.get('documentTitle', 'KnowledgeBase')}'."
            })
            if summary_res.get("status") == "success":
                sum_sources = summary_res.get("citations", [])
                for s in sum_sources:
                    citations.append({
                        "id": str(uuid.uuid4()),
                        "sourceType": "document",
                        "title": s["title"],
                        "snippet": s["snippet"],
                        "page": s.get("page"),
                        "pageLabel": s.get("pageLabel") or format_page_citation(s.get("page")),
                        "documentId": s.get("documentId")
                    })
                response_content = format_grounded_rag_response(summary_res["summary"], sum_sources[:3], query=query)
            elif summary_res.get("status") == "error":
                err_info = summary_res.get("error", {})
                return {
                    "id": f"asst_err_{uuid.uuid4().hex[:8]}",
                    "conversationId": conversation_id,
                    "role": "assistant",
                    "content": summary_res.get("message"),
                    "status": "error",
                    "error": err_info,
                    "toolExecutions": tool_executions,
                    "citations": [],
                    "suggestedAction": None,
                    "diagnostics": {
                        "promptVersion": PROMPT_VERSION,
                        "selectedTool": selected_tool,
                        "status": "error",
                        "errorCategory": err_info.get("category"),
                        "geminiCalled": True
                    }
                }
            else:
                response_content = f"**Answer:**\n{summary_res.get('message', 'No matching document found in your Knowledge Base.')}"

        # --- PATH 8: WEATHER ---
        elif selected_tool == "weather_lookup":
            city = tool_args.get("city", "Bengaluru")
            res = await tool_registry.execute("weather_lookup", city=city)
            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "WeatherTelemetry",
                "status": "success" if res.get("status") == "success" else "failed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Retrieved live weather for {res.get('location', city)}."
            })
            if res.get("status") == "success":
                response_content = (
                    f"### Weather for {res['location']}\n\n"
                    f"• **Condition:** {res['condition']}\n"
                    f"• **Temperature:** {res['temperatureC']}°C (feels like {res['apparentTemperatureC']}°C)\n"
                    f"• **Humidity:** {res['humidityPercent']}%\n"
                    f"• **Wind Speed:** {res['windSpeedKmh']} km/h\n"
                    f"• **Precipitation:** {res['precipitationMm']} mm\n\n"
                    f"*Telemetry source: Open-Meteo Live Forecast Service*"
                )
            else:
                response_content = res.get("message", "Unable to retrieve weather data.")

        # --- PATH 9: WEB SEARCH ---
        elif selected_tool == "web_search_intelligence":
            sq = tool_args.get("query", query)
            res = await tool_registry.execute("web_search_intelligence", query=sq)
            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "LiveWebSearch",
                "status": "success" if res.get("status") == "success" else "unconfigured",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Queried web intelligence for '{sq}'."
            })
            if res.get("status") == "success":
                results = res.get("results", [])
                for r in results:
                    citations.append({
                        "id": str(uuid.uuid4()),
                        "sourceType": "document",
                        "title": r["title"],
                        "snippet": r["snippet"],
                        "url": r["url"]
                    })
                items = "\n".join([f"• [{r['title']}]({r['url']}): {r['snippet']}" for r in results[:4]])
                response_content = f"Here is the latest web intelligence for *\"{sq}\"*:\n\n{items}"
            else:
                response_content = res.get("message", "Live web search is not configured.")

        # --- PATH 10: TIMETABLE ---
        elif selected_tool in (
            "timetable_lookup", "search_timetable",
            "get_timetable_for_day", "get_timetable_period", "get_timetable_period_by_time",
            "get_timetable_between_times", "get_timetable_periods", "get_full_timetable", "get_next_class"
        ):
            if selected_tool == "get_timetable_for_day":
                is_tom = "tomorrow" in query.lower()
                tool_res = await tool_registry.execute(
                    "get_timetable_for_day",
                    user_id=user_id,
                    db=db,
                    day=tool_args.get("day", "Monday"),
                    is_tomorrow=is_tom
                )
            elif selected_tool == "get_timetable_period":
                tool_res = await tool_registry.execute(
                    "get_timetable_period",
                    user_id=user_id,
                    db=db,
                    day=tool_args.get("day", "Monday"),
                    period_number=int(tool_args.get("period_number", 1))
                )
            elif selected_tool == "get_timetable_period_by_time":
                tool_res = await tool_registry.execute(
                    "get_timetable_period_by_time",
                    user_id=user_id,
                    db=db,
                    day=tool_args.get("day", "Monday"),
                    time=tool_args.get("time", "10:00 AM")
                )
            elif selected_tool == "get_timetable_between_times":
                tool_res = await tool_registry.execute(
                    "get_timetable_between_times",
                    user_id=user_id,
                    db=db,
                    day=tool_args.get("day"),
                    start_time=tool_args.get("start_time", "10:00 AM"),
                    end_time=tool_args.get("end_time", "12:00 PM")
                )
            elif selected_tool == "get_timetable_periods":
                tool_res = await tool_registry.execute(
                    "get_timetable_periods",
                    user_id=user_id,
                    db=db,
                    day=tool_args.get("day", "Monday"),
                    period_numbers=tool_args.get("period_numbers", [1])
                )
            elif selected_tool == "get_full_timetable":
                tool_res = await tool_registry.execute(
                    "get_full_timetable",
                    user_id=user_id,
                    db=db
                )
            elif selected_tool == "get_next_class":
                tool_res = await tool_registry.execute(
                    "get_next_class",
                    user_id=user_id,
                    db=db,
                    subject=tool_args.get("subject"),
                    is_lab=tool_args.get("is_lab", False)
                )
            else:
                tool_res = await tool_registry.execute(
                    "search_timetable",
                    user_id=user_id,
                    db=db,
                    query=query,
                    day_of_week=tool_args.get("day_of_week"),
                    subject=tool_args.get("subject"),
                    time_start=tool_args.get("time_start"),
                    time_end=tool_args.get("time_end"),
                    check_availability=tool_args.get("check_availability", False),
                    followup_type=tool_args.get("followup_type")
                )
            classes = tool_res.get("classes", [])
            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": selected_tool,
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Retrieved {len(classes)} timetable entries."
            })

            if "customMessage" in tool_res:
                response_content = tool_res["customMessage"]
            elif "availabilityMessage" in tool_res:
                response_content = tool_res["availabilityMessage"]
            elif classes:
                target_day = tool_res.get("targetDay")
                target_subject = tool_res.get("targetSubject")
                header = "According to your academic timetable records"
                if target_day:
                    header += f" for {target_day}"
                if target_subject:
                    header += f" for {target_subject}"
                lines = [f"• **{c['course']}** ({c['code']}): {c['day']} from {c['time']} in {c['room']} ({c.get('classType', 'Theory')})" for c in classes]
                response_content = f"{header}:\n\n" + "\n".join(lines)
            else:
                response_content = "You don't have a scheduled period for that selection."

        # --- PATH 11: GMAIL DRAFT ---
        elif selected_tool == "gmail_create_draft":
            to = tool_args.get("to")
            if not to or "@" not in to:
                em = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', query)
                to = em.group(0) if em else "recipient@university.edu"

            subject = tool_args.get("subject")
            if not subject or subject == "Academic Query":
                sm = re.search(r'(?:about|regarding|subject[:\s]+)([^.\n]+)', query, re.IGNORECASE)
                subject = sm.group(1).strip().capitalize() if sm else "Academic Update"

            body = tool_args.get("body")
            if not body or "I am writing regarding my coursework" in body:
                if settings.GEMINI_API_KEY:
                    from app.prompts.gmail import GMAIL_DRAFT_PROMPT
                    draft_prompt = (
                        f"{history_context}"
                        f"Recipient: {to}\n"
                        f"Subject: {subject}\n"
                        f"User Request: {query}\n\n"
                        "Draft a professional, concise email body matching the user's intent. "
                        "Return ONLY the plain text email body without headers or markdown fencing."
                    )
                    gem_res = await call_gemini_api(draft_prompt, GMAIL_DRAFT_PROMPT)
                    if gem_res.success and gem_res.text:
                        body = gem_res.text.strip()
                if not body:
                    body = (
                        f"Hello,\n\n"
                        f"I am writing regarding: {subject}.\n\n"
                        f"Please review and let me know if you have any questions.\n\n"
                        f"Best regards,\nAlex Chen"
                    )

            suggested_action = {
                "id": str(uuid.uuid4()),
                "actionType": "create_draft",
                "title": f"Create Draft: {subject}",
                "details": {
                    "to": to,
                    "subject": subject,
                    "body": body,
                    "service": "Google Gmail API"
                },
                "status": "pending"
            }

            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "GmailDraftComposer",
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Prepared email draft to {to}."
            })

            response_content = (
                f"I formulated a proposed email draft for you:\n\n"
                f"• **To:** `{to}`\n"
                f"• **Subject:** `{subject}`\n\n"
                f"> {body.replace(chr(10), chr(10) + '> ')}\n\n"
                "Please review the proposed draft. Click **Confirm & Commit Action** below to save it into your Gmail account."
            )

        # --- PATH 12: UNIFIED CALENDAR & STUDY SCHEDULE RETRIEVAL ---
        elif selected_tool == "calendar_events_retrieval":
            # 1. Fetch user local time context
            try:
                user_tz_obj = zoneinfo.ZoneInfo(user_tz)
            except Exception:
                user_tz_obj = zoneinfo.ZoneInfo("UTC")

            now_user = datetime.now(timezone.utc).astimezone(user_tz_obj)
            today_d = now_user.date()
            tomorrow_d = today_d + timedelta(days=1)
            today_iso = today_d.isoformat()
            tomorrow_iso = tomorrow_d.isoformat()

            # 2. Retrieve Google Calendar events
            cal_res = await tool_registry.execute(
                "calendar_events_retrieval",
                user_id=user_id,
                db=db,
                time_min=tool_args.get("time_min"),
                time_max=tool_args.get("time_max")
            )
            cal_events = cal_res.get("events", [])
            is_live = cal_res.get("isLive", False)

            # 3. Retrieve user's Study Plan Tasks
            user_plans = db.query(Plan).filter(Plan.user_id == user_id).all()
            plan_ids = [p.id for p in user_plans]
            plan_title_map = {p.id: p.title for p in user_plans}
            study_tasks = db.query(PlanTask).filter(PlanTask.plan_id.in_(plan_ids)).all() if plan_ids else []

            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "UnifiedScheduleIntelligence",
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Queried schedule (Google Calendar Live: {is_live}, Events: {len(cal_events)}, Study Tasks: {len(study_tasks)})."
            })

            lower_q = query.lower()

            # Sub-case A: Study Session Sync Status Query
            if any(k in lower_q for k in ["synchroniz", "synced", "sync status", "are my study sessions", "are study sessions added", "are tasks synced"]):
                synced_tasks = [t for t in study_tasks if t.google_calendar_event_id]
                unsynced_tasks = [t for t in study_tasks if not t.google_calendar_event_id]

                if not study_tasks:
                    response_content = (
                        "You currently have no study sessions or tasks configured in your Planning Workspace. "
                        "You can create a study plan (e.g., 'Create a 30-day DSA plan') or visit the **Plan** page."
                    )
                else:
                    synced_lines = [f"• ✅ **{t.title}** ({t.scheduled_date or 'Roadmap'} at {t.start_time or 'Scheduled'}) — Synced" for t in synced_tasks[:4]]
                    unsynced_lines = [f"• ◻️ **{t.title}** ({t.scheduled_date or 'Roadmap'} at {t.start_time or 'TBD'}) — Local only" for t in unsynced_tasks[:4]]

                    sync_summary = (
                        f"📊 **Study Session Synchronization Status:**\n\n"
                        f"• **Total Study Tasks:** {len(study_tasks)}\n"
                        f"• **Synchronized to Google Calendar:** {len(synced_tasks)}\n"
                        f"• **Local to Aurelia Planning Workspace:** {len(unsynced_tasks)}\n\n"
                    )
                    if synced_lines:
                        sync_summary += "**Synchronized Sessions:**\n" + "\n".join(synced_lines) + "\n\n"
                    if unsynced_lines:
                        sync_summary += "**Unsynchronized / Local Sessions:**\n" + "\n".join(unsynced_lines) + "\n\n"
                    sync_summary += "To sync pending sessions to your Google Calendar, visit the **Calendar** or **Plan** page and click **Sync to Google Calendar**, or tell me: *'Add the selected study sessions to Google Calendar'*."
                    response_content = sync_summary

            # 4. Parse all Google Calendar events into datetime-aware objects
            all_cal_items = []
            for ev in cal_events:
                s_str = ev.get("startTime") or ev.get("start", {}).get("dateTime")
                e_str = ev.get("endTime") or ev.get("end", {}).get("dateTime")
                if s_str:
                    try:
                        s_dt = datetime.fromisoformat(s_str.replace("Z", "+00:00")).astimezone(user_tz_obj)
                        e_dt = datetime.fromisoformat(e_str.replace("Z", "+00:00")).astimezone(user_tz_obj) if e_str else (s_dt + timedelta(hours=1))
                        ev_title = ev.get("title") or "Event"
                        is_academic = bool(re.search(r'\b(?:study|exam|course|quiz|lecture|assignment|homework)\b', ev_title, re.IGNORECASE))
                        all_cal_items.append({
                            "id": ev.get("id"),
                            "title": ev_title,
                            "start_dt": s_dt,
                            "end_dt": e_dt,
                            "location": ev.get("location") or "Online",
                            "is_academic": is_academic,
                            "raw": ev
                        })
                    except Exception:
                        pass

            # 5. Parse all Study Tasks into datetime-aware objects
            all_study_items = []
            for t in study_tasks:
                if t.scheduled_date:
                    try:
                        t_date = date.fromisoformat(t.scheduled_date)
                        t_time_str = t.start_time or "09:00 AM"
                        try:
                            parsed_t = datetime.strptime(t_time_str.strip(), "%I:%M %p").time()
                        except Exception:
                            parsed_t = datetime.strptime("09:00 AM", "%I:%M %p").time()
                        s_dt = datetime.combine(t_date, parsed_t, tzinfo=user_tz_obj)
                        dur = t.duration_minutes or 45
                        e_dt = s_dt + timedelta(minutes=dur)
                        plan_name = plan_title_map.get(t.plan_id, "Study Plan")
                        all_study_items.append({
                            "task": t,
                            "title": t.title,
                            "start_dt": s_dt,
                            "end_dt": e_dt,
                            "duration": dur,
                            "plan_name": plan_name,
                            "completed": t.completed,
                            "is_synced": bool(t.google_calendar_event_id),
                            "google_calendar_event_id": t.google_calendar_event_id
                        })
                    except Exception:
                        pass

            # Sub-case B: Quiz / Exam Query
            if any(k in lower_q for k in ["quiz", "exam", "test", "midterm", "final exam"]):
                upcoming_quizzes = []
                for c in all_cal_items:
                    if c["end_dt"] >= now_user and any(w in c["title"].lower() for w in ["quiz", "exam", "test", "midterm", "final"]):
                        upcoming_quizzes.append({
                            "title": c["title"],
                            "dt": c["start_dt"],
                            "source": "Google Calendar",
                            "detail": f"{c['start_dt'].strftime('%A, %b %d at %I:%M %p')} ({c['location']})"
                        })
                for s in all_study_items:
                    if s["end_dt"] >= now_user and any(w in s["title"].lower() for w in ["quiz", "exam", "test", "midterm", "final"]):
                        upcoming_quizzes.append({
                            "title": s["title"],
                            "dt": s["start_dt"],
                            "source": f"Study Plan ({s['plan_name']})",
                            "detail": f"{s['start_dt'].strftime('%A, %b %d at %I:%M %p')} ({s['duration']} mins)"
                        })

                upcoming_quizzes.sort(key=lambda x: x["dt"])
                if upcoming_quizzes:
                    q_lines = []
                    for q in upcoming_quizzes[:3]:
                        q_lines.append(f"• 📝 **{q['title']}**\n  – **When:** {q['detail']}\n  – **Source:** {q['source']}")
                        citations.append({
                            "id": str(uuid.uuid4()),
                            "sourceType": "calendar",
                            "title": q["title"],
                            "snippet": f"Quiz/Exam: {q['detail']}"
                        })
                    response_content = "📝 **Upcoming Quizzes & Exams:**\n\n" + "\n\n".join(q_lines)
                else:
                    response_content = "You have no upcoming quizzes, tests, or exams scheduled on your Google Calendar or Study Plans."

            # Sub-case C: Meeting Query ("When is my next meeting?")
            elif any(k in lower_q for k in ["next meeting", "upcoming meeting", "when is my next meeting", "do i have any meetings", "what meetings do i have"]):
                upcoming_meetings = [c for c in all_cal_items if c["end_dt"] >= now_user and not c.get("is_academic", False)]
                upcoming_meetings.sort(key=lambda x: x["start_dt"])
                if upcoming_meetings:
                    m_lines = []
                    for m in upcoming_meetings[:3]:
                        loc_str = f" ({m['location']})" if m['location'] else ""
                        dt_str = m["start_dt"].strftime('%A, %b %d at %I:%M %p')
                        m_lines.append(f"• 📅 **{m['title']}**\n  – **When:** {dt_str}{loc_str}")
                        citations.append({
                            "id": str(uuid.uuid4()),
                            "sourceType": "calendar",
                            "title": m["title"],
                            "snippet": f"Meeting: {dt_str}{loc_str}"
                        })
                    response_content = "📅 **Upcoming Meetings on Google Calendar:**\n\n" + "\n\n".join(m_lines)
                else:
                    response_content = "You have no upcoming meetings scheduled on your calendar."

            # Sub-case D: Multiple Upcoming Events ("What are my next three events?")
            elif any(k in lower_q for k in ["next three", "next 3", "next few", "next 2", "next two", "upcoming events"]):
                synced_event_ids = {s["google_calendar_event_id"] for s in all_study_items if s.get("google_calendar_event_id")}
                combined = []
                for c in all_cal_items:
                    if c["id"] not in synced_event_ids and c["end_dt"] >= now_user:
                        combined.append({"title": c["title"], "start_dt": c["start_dt"], "source": "Google Calendar", "loc": c["location"]})
                for s in all_study_items:
                    if not s["completed"] and s["end_dt"] >= now_user:
                        tag = "Study Session (Synced)" if s["is_synced"] else "Study Plan Block"
                        combined.append({"title": s["title"], "start_dt": s["start_dt"], "source": tag, "loc": s["plan_name"]})
                combined.sort(key=lambda x: x["start_dt"])

                target_count = 2 if any(w in lower_q for w in ["next two", "next 2"]) else 3
                if combined:
                    c_lines = []
                    for idx, it in enumerate(combined[:target_count]):
                        diff = it["start_dt"] - now_user
                        hrs = int(diff.total_seconds() // 3600)
                        mins = int((diff.total_seconds() % 3600) // 60)
                        time_away = f"in {hrs}h {mins}m" if hrs > 0 else f"in {mins}m"
                        if it["start_dt"].date() > today_d:
                            time_away = it["start_dt"].strftime("%b %d at %I:%M %p")
                        c_lines.append(f"{idx+1}. **{it['title']}**\n   – **When:** {it['start_dt'].strftime('%A, %b %d at %I:%M %p')} ({time_away})\n   – **Type:** {it['source']} ({it['loc']})")
                        citations.append({
                            "id": str(uuid.uuid4()),
                            "sourceType": "calendar",
                            "title": it["title"],
                            "snippet": f"{it['start_dt'].strftime('%A, %b %d at %I:%M %p')} • {it['source']}"
                        })
                    response_content = f"⏰ **Your Next {min(len(combined), target_count)} Scheduled Events:**\n\n" + "\n\n".join(c_lines)
                else:
                    response_content = "You have no upcoming scheduled events or pending study tasks for the rest of today or this week."

            # Sub-case E: Next 1 Event ("What is my next event?")
            elif any(k in lower_q for k in ["next scheduled", "next task", "next event", "what is next", "when is my next", "next commitment"]):
                synced_event_ids = {s["google_calendar_event_id"] for s in all_study_items if s.get("google_calendar_event_id")}
                combined = []
                for c in all_cal_items:
                    if c["id"] not in synced_event_ids and c["end_dt"] >= now_user:
                        combined.append({"title": c["title"], "start_dt": c["start_dt"], "source": "Google Calendar", "loc": c["location"]})
                for s in all_study_items:
                    if not s["completed"] and s["end_dt"] >= now_user:
                        tag = "Study Session (Synced)" if s["is_synced"] else "Study Plan Block"
                        combined.append({"title": s["title"], "start_dt": s["start_dt"], "source": tag, "loc": s["plan_name"]})
                combined.sort(key=lambda x: x["start_dt"])

                if combined:
                    next_item = combined[0]
                    diff = next_item["start_dt"] - now_user
                    hours_away = int(diff.total_seconds() // 3600)
                    mins_away = int((diff.total_seconds() % 3600) // 60)
                    time_away_str = f"in {hours_away}h {mins_away}m" if hours_away > 0 else f"in {mins_away} minutes"
                    if next_item["start_dt"].date() > today_d:
                        time_away_str = f"tomorrow at {next_item['start_dt'].strftime('%I:%M %p')}"

                    citations.append({
                        "id": str(uuid.uuid4()),
                        "sourceType": "calendar",
                        "title": next_item["title"],
                        "snippet": f"{next_item['start_dt'].strftime('%A, %b %d at %I:%M %p')} ({next_item['source']})"
                    })

                    response_content = (
                        f"⏰ **Your Next Scheduled Task:**\n\n"
                        f"• **{next_item['title']}**\n"
                        f"  – **When:** {next_item['start_dt'].strftime('%A, %b %d at %I:%M %p')} ({time_away_str})\n"
                        f"  – **Type:** {next_item['source']} ({next_item['loc']})\n"
                    )
                else:
                    response_content = (
                        "You have no upcoming scheduled events or pending study tasks for the rest of today. "
                        "Your schedule is completely clear!"
                    )

            # Sub-case F: Free Time / Availability Query
            elif any(k in lower_q for k in ["free time", "am i free", "open slot", "free slot", "availability", "available"]):
                target_date = tomorrow_d if "tomorrow" in lower_q else today_d
                explicit_d = parse_explicit_calendar_date(query, ref_date=today_d)
                if explicit_d:
                    target_date = explicit_d
                target_date_str = target_date.isoformat()
                day_name = "tomorrow" if target_date == tomorrow_d else ("today" if target_date == today_d else target_date.strftime("%A, %b %d"))

                # Check if specific clock time requested: e.g. "at 6 PM", "6 PM", "18:00"
                time_match = re.search(r'\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', lower_q)
                target_hour = None
                target_minute = 0
                if time_match:
                    h = int(time_match.group(1))
                    m = int(time_match.group(2) or 0)
                    ampm = time_match.group(3)
                    if ampm == "pm" and h != 12:
                        h += 12
                    elif ampm == "am" and h == 12:
                        h = 0
                    target_hour = h
                    target_minute = m

                is_afternoon_query = "afternoon" in lower_q

                busy_intervals = []
                for c in all_cal_items:
                    if c["start_dt"].date() == target_date:
                        busy_intervals.append((c["start_dt"], c["end_dt"], c["title"]))
                for s in all_study_items:
                    if not s["completed"] and s["start_dt"].date() == target_date:
                        if not any(s["start_dt"] < b_e and s["end_dt"] > b_s for b_s, b_e, _ in busy_intervals):
                            busy_intervals.append((s["start_dt"], s["end_dt"], f"Study: {s['title']}"))

                if target_hour is not None:
                    check_dt = datetime(target_date.year, target_date.month, target_date.day, target_hour, target_minute, tzinfo=user_tz_obj)
                    check_end = check_dt + timedelta(hours=1)
                    conflict = None
                    for b_s, b_e, b_title in busy_intervals:
                        if check_dt < b_e and check_end > b_s:
                            conflict = (b_title, b_s, b_e)
                            break

                    time_label = check_dt.strftime("%I:%M %p").lstrip("0")
                    if conflict:
                        conf_title, conf_start, conf_end = conflict
                        response_content = (
                            f"❌ **You are not free {day_name} at {time_label}.**\n\n"
                            f"You have **{conf_title}** scheduled from {conf_start.strftime('%I:%M %p').lstrip('0')} to {conf_end.strftime('%I:%M %p').lstrip('0')}."
                        )
                    else:
                        response_content = (
                            f"✅ **Yes, you are free {day_name} at {time_label}!**\n\n"
                            f"There are no Google Calendar events or study sessions scheduled at that time."
                        )
                elif is_afternoon_query:
                    # Evaluate 12:00 PM to 5:00 PM
                    aft_start = datetime(target_date.year, target_date.month, target_date.day, 12, 0, tzinfo=user_tz_obj)
                    aft_end = datetime(target_date.year, target_date.month, target_date.day, 17, 0, tzinfo=user_tz_obj)
                    aft_conflicts = [b for b in busy_intervals if b[0] < aft_end and b[1] > aft_start]
                    if not aft_conflicts:
                        response_content = (
                            f"✅ **Yes, you have completely free time {day_name} afternoon!**\n\n"
                            f"Your schedule is entirely clear between **12:00 PM and 5:00 PM**."
                        )
                    else:
                        c_lines = [f"• **{b[2]}**: {b[0].strftime('%I:%M %p').lstrip('0')} – {b[1].strftime('%I:%M %p').lstrip('0')}" for b in aft_conflicts]
                        response_content = (
                            f"🕒 **Your Afternoon Schedule for {day_name.capitalize()}:**\n\n"
                            + "\n".join(c_lines) +
                            "\n\nYou have commitments during this period, but you can schedule around them."
                        )
                else:
                    day_start = datetime(target_date.year, target_date.month, target_date.day, 9, 0, tzinfo=user_tz_obj)
                    day_end = datetime(target_date.year, target_date.month, target_date.day, 21, 0, tzinfo=user_tz_obj)
                    busy_intervals.sort(key=lambda x: x[0])
                    free_slots = []
                    curr = day_start
                    for b_s, b_e, _ in busy_intervals:
                        if b_s > curr and (b_s - curr).total_seconds() >= 1800:
                            free_slots.append((curr, min(b_s, day_end)))
                        curr = max(curr, b_e)
                    if curr < day_end and (day_end - curr).total_seconds() >= 1800:
                        free_slots.append((curr, day_end))

                    if free_slots:
                        slot_lines = []
                        for s_f, e_f in free_slots:
                            dur_h = (e_f - s_f).total_seconds() / 3600
                            slot_lines.append(f"• **{s_f.strftime('%I:%M %p').lstrip('0')} – {e_f.strftime('%I:%M %p').lstrip('0')}** ({dur_h:g} hours available)")
                        response_content = (
                            f"🕒 **Free Time Gaps for {day_name.capitalize()} ({target_date.strftime('%A, %b %d')}):**\n\n"
                            + "\n".join(slot_lines) +
                            f"\n\nWould you like me to schedule a study session or personal event during one of these open slots?"
                        )
                    else:
                        response_content = f"Your schedule for {day_name} is fully booked between 9:00 AM and 9:00 PM with no gaps longer than 30 minutes."

            # Sub-case G: Study Tasks specifically requested or Session count
            elif any(k in lower_q for k in ["study task", "study tasks", "what study", "study sessions", "tasks today", "study plan tasks", "how many study sessions"]):
                if "week" in lower_q:
                    w_start, w_end, _, _ = get_user_week_bounds(user_tz)
                    week_study = [s for s in all_study_items if w_start <= s["start_dt"] <= w_end]
                    completed_count = sum(1 for s in week_study if s["completed"])
                    pending_count = len(week_study) - completed_count
                    lines = [f"• {'✅' if s['completed'] else '◻️'} **{s['title']}** ({s['start_dt'].strftime('%a %b %d, %I:%M %p')}, {s['duration']}m)" for s in week_study[:6]]
                    response_content = (
                        f"📚 **Study Sessions This Week ({w_start.strftime('%b %d')} – {w_end.strftime('%b %d')}):**\n\n"
                        f"You have **{len(week_study)} study sessions** scheduled this week ({completed_count} completed, {pending_count} pending):\n\n"
                        + "\n".join(lines)
                    )
                else:
                    target_date_str = tomorrow_iso if "tomorrow" in lower_q else today_iso
                    day_name = "tomorrow" if "tomorrow" in lower_q else "today"
                    explicit_d = parse_explicit_calendar_date(query, ref_date=today_d)
                    if explicit_d:
                        target_date_str = explicit_d.isoformat()
                        day_name = explicit_d.strftime("%A, %b %d")

                    matching_study = [t for t in study_tasks if t.scheduled_date == target_date_str]
                    if matching_study:
                        lines = []
                        for t in matching_study:
                            plan_name = plan_title_map.get(t.plan_id, "Study Plan")
                            status_str = "✅ Completed" if t.completed else "◻️ Pending"
                            sync_str = " (Synced to Calendar)" if t.google_calendar_event_id else ""
                            time_str = f" at {t.start_time}" if t.start_time else ""
                            lines.append(f"• {status_str} **{t.title}** ({t.duration_minutes}m{time_str}){sync_str} — *{plan_name}*")
                            citations.append({
                                "id": str(uuid.uuid4()),
                                "sourceType": "study_plan",
                                "title": t.title,
                                "snippet": f"Plan: {plan_name} • Duration: {t.duration_minutes}m • Date: {target_date_str}"
                            })
                        response_content = f"📚 **Study Tasks for {day_name.capitalize()} ({target_date_str}):**\n\n" + "\n".join(lines)
                    else:
                        pending_total = sum(1 for t in study_tasks if not t.completed)
                        response_content = (
                            f"You have no study tasks scheduled for **{day_name}** ({target_date_str}). "
                            f"(You have {pending_total} pending tasks remaining across your roadmap.)"
                        )

            # Sub-case H: Google Calendar events specifically requested
            elif any(k in lower_q for k in ["google calendar events", "google calendar for today", "google calendar today", "external events"]):
                target_date = tomorrow_d if "tomorrow" in lower_q else today_d
                explicit_d = parse_explicit_calendar_date(query, ref_date=today_d)
                if explicit_d:
                    target_date = explicit_d
                day_name = "tomorrow" if target_date == tomorrow_d else ("today" if target_date == today_d else target_date.strftime("%A, %b %d"))

                matching_cal = [c for c in all_cal_items if c["start_dt"].date() == target_date]
                if matching_cal:
                    c_lines = [f"• 📅 **{c['title']}**: {c['start_dt'].strftime('%I:%M %p').lstrip('0')} ({c['location']})" for c in matching_cal]
                    response_content = f"📅 **Google Calendar Events for {day_name.capitalize()} ({target_date.strftime('%A, %b %d')}):**\n\n" + "\n".join(c_lines)
                else:
                    response_content = f"You have no Google Calendar events scheduled for **{day_name}** ({target_date.strftime('%A, %b %d')})."

            # Sub-case I: Week Schedule ("What is on my calendar this week?")
            elif "week" in lower_q and any(w in lower_q for w in ["calendar", "schedule", "planned", "what do i have", "events"]):
                w_start, w_end, _, _ = get_user_week_bounds(user_tz)
                matching_cal = [c for c in all_cal_items if w_start <= c["start_dt"] <= w_end]
                matching_study = [s for s in all_study_items if w_start <= s["start_dt"] <= w_end]

                sections = []
                if is_live and matching_cal:
                    c_lines = [f"• 📅 **{c['title']}**: {c['start_dt'].strftime('%a %b %d, %I:%M %p')} ({c['location']})" for c in matching_cal]
                    sections.append("**Google Calendar Events:**\n" + "\n".join(c_lines))
                if matching_study:
                    s_lines = [f"• {'✅' if s['completed'] else '◻️'} 📚 **{s['title']}**: {s['start_dt'].strftime('%a %b %d, %I:%M %p')} — *{s['plan_name']}*" for s in matching_study]
                    sections.append("**Study Plan Sessions:**\n" + "\n".join(s_lines))

                if not sections:
                    response_content = f"You have nothing scheduled for **this week** ({w_start.strftime('%b %d')} – {w_end.strftime('%b %d')}). Your schedule is clear!"
                else:
                    response_content = f"📅 **Your Unified Schedule for This Week ({w_start.strftime('%b %d')} – {w_end.strftime('%b %d')}):**\n\n" + "\n\n".join(sections)

            # Sub-case J: Month Schedule ("What do I have planned for this month?")
            elif "month" in lower_q and any(w in lower_q for w in ["calendar", "schedule", "planned", "what do i have", "events"]):
                m_start, m_end, _, _ = get_user_month_bounds(user_tz)
                matching_cal = [c for c in all_cal_items if m_start <= c["start_dt"] <= m_end]
                matching_study = [s for s in all_study_items if m_start <= s["start_dt"] <= m_end]

                sections = []
                if is_live and matching_cal:
                    c_lines = [f"• 📅 **{c['title']}**: {c['start_dt'].strftime('%b %d, %I:%M %p')} ({c['location']})" for c in matching_cal[:8]]
                    sections.append(f"**Google Calendar Events ({len(matching_cal)} total):**\n" + "\n".join(c_lines))
                if matching_study:
                    s_lines = [f"• {'✅' if s['completed'] else '◻️'} 📚 **{s['title']}**: {s['start_dt'].strftime('%b %d')} — *{s['plan_name']}*" for s in matching_study[:8]]
                    sections.append(f"**Study Plan Tasks ({len(matching_study)} total):**\n" + "\n".join(s_lines))

                if not sections:
                    response_content = f"You have nothing scheduled for **this month** ({m_start.strftime('%B %Y')}). Your schedule is clear!"
                else:
                    response_content = f"📅 **Your Schedule Overview for {m_start.strftime('%B %Y')}:**\n\n" + "\n\n".join(sections)

            # Sub-case K: Day-Specific or General Daily Schedule (Supports "November 5", "tomorrow", "today", "yesterday")
            else:
                target_date = tomorrow_d if "tomorrow" in lower_q else today_d
                explicit_d = parse_explicit_calendar_date(query, ref_date=today_d)
                if explicit_d:
                    target_date = explicit_d
                elif "yesterday" in lower_q:
                    target_date = today_d - timedelta(days=1)

                target_date_str = target_date.isoformat()
                day_name = "tomorrow" if target_date == tomorrow_d else ("today" if target_date == today_d else ("yesterday" if target_date == (today_d - timedelta(days=1)) else target_date.strftime("%A, %b %d")))

                matching_cal = [c for c in all_cal_items if c["start_dt"].date() == target_date]
                matching_study = [s for s in all_study_items if s["start_dt"].date() == target_date]

                sections = []
                if is_live:
                    if matching_cal:
                        c_lines = []
                        for c in matching_cal:
                            citations.append({
                                "id": str(uuid.uuid4()),
                                "sourceType": "calendar",
                                "title": c["title"],
                                "snippet": f"Time: {c['start_dt'].strftime('%I:%M %p')} • Location: {c['location']}"
                            })
                            c_lines.append(f"• 📅 **{c['title']}**: {c['start_dt'].strftime('%I:%M %p').lstrip('0')} ({c['location']})")
                        sections.append("**Google Calendar Events:**\n" + "\n".join(c_lines))
                    else:
                        sections.append(f"**Google Calendar:** No external events scheduled for {day_name}.")
                else:
                    sections.append("ℹ️ *Google Calendar is not connected. (Connect it in Integrations to view external events).*")

                if matching_study:
                    s_lines = []
                    for s in matching_study:
                        status_str = "✅" if s["completed"] else "◻️"
                        sync_tag = " [Synced]" if s["is_synced"] else ""
                        citations.append({
                            "id": str(uuid.uuid4()),
                            "sourceType": "study_plan",
                            "title": s["title"],
                            "snippet": f"Plan: {s['plan_name']} • Duration: {s['duration']}m • Date: {target_date_str}"
                        })
                        s_lines.append(f"• {status_str} 📚 **{s['title']}** ({s['duration']}m at {s['start_dt'].strftime('%I:%M %p').lstrip('0')}){sync_tag} — *{s['plan_name']}*")
                    sections.append("**Aurelia Study Plan Sessions:**\n" + "\n".join(s_lines))

                if not matching_cal and not matching_study:
                    response_content = f"You have nothing scheduled for **{day_name}** ({target_date.strftime('%A, %b %d')}). Your schedule is clear!"
                else:
                    response_content = f"📅 **Your Schedule for {day_name.capitalize()} ({target_date.strftime('%A, %b %d')}):**\n\n" + "\n\n".join(sections)
                    response_content = f"📅 **Your Schedule for {day_name.capitalize()} ({target_date.strftime('%A, %b %d')}):**\n\n" + "\n\n".join(sections)

        # --- PATH 13: GMAIL PRIORITY MESSAGES ---
        elif selected_tool == "gmail_priority_messages":
            g_res = await tool_registry.execute("gmail_priority_messages", user_id=user_id, db=db, query=tool_args.get("query", ""))
            messages = g_res.get("messages", [])
            is_live = g_res.get("isLive", False)

            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "GmailMessageSearch",
                "status": "success" if is_live else g_res.get("status", "failed"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": f"Retrieved {len(messages)} messages from Gmail (Connected: {is_live})."
            })

            if not is_live:
                if g_res.get("status") == "capability_disabled":
                    response_content = g_res.get("message")
                else:
                    response_content = "Your Gmail account is not connected. Please connect Gmail in Workspace Integrations to view and summarize your emails."
            elif messages:
                for m in messages[:4]:
                    citations.append({
                        "id": str(uuid.uuid4()),
                        "sourceType": "email",
                        "title": f"Email: {m.get('fromName', 'Sender')}",
                        "snippet": f"{m.get('subject', '')}: {m.get('snippet', '')[:150]}",
                        "url": m.get("gmailLink", "https://mail.google.com")
                    })
                lines = [f"• **{m.get('fromName', 'Sender')}** — *{m.get('subject')}*\n  _{m.get('snippet', '')[:120]}..._" for m in messages[:4]]
                response_content = "Here are your priority emails matching your query:\n\n" + "\n\n".join(lines)
            else:
                response_content = "No emails matching your search were found in your connected Gmail inbox."

        # --- PATH 13B: GENERAL QA & CONVERSATION ---
        elif selected_tool == "general_qa":
            if settings.GEMINI_API_KEY:
                user_prompt = f"{history_context}User Query: {query}"
                gemini_res = await call_gemini_api(user_prompt, GENERAL_QA_PROMPT)
                if gemini_res.success and gemini_res.text:
                    response_content = gemini_res.text
                else:
                    response_content = (
                        "Hello! I am **Aurelia AI**, your personal academic and productivity assistant. "
                        "I can help you review emails, schedule Google Calendar events, manage study plans, "
                        "search your uploaded documents and lecture notes, check live weather, and search the web. "
                        "How can I assist you today?"
                    )
            else:
                response_content = (
                    "Hello! I am **Aurelia AI**, your personal academic and productivity assistant. "
                    "I can help you review emails, schedule Google Calendar events, manage study plans, "
                    "search your uploaded documents and lecture notes, check live weather, and search the web. "
                    "How can I assist you today?"
                )
            tool_executions.append({
                "id": str(uuid.uuid4()),
                "toolName": "GeneralConversationAgent",
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "resultSummary": "Provided conversational response."
            })

        # --- PATH 14: KNOWLEDGE BASE RAG (Default Fallback) ---
        else:
            # Check if query is a follow-up referring to a previously cited document in conversational memory
            explicit_doc_id = None
            follow_up_tokens = [
                "it", "that document", "this document", "the document", "the paper", "that paper",
                "the second point", "in simpler terms", "more about it", "explain that", "what else does",
                "tell me more", "give an example", "give examples", "what about", "explain more",
                "elaborate", "can you clarify", "what does it mean", "explain this", "what is that"
            ]
            lower_q = query.lower()
            has_followup_token = any(tok in lower_q for tok in follow_up_tokens)
            is_short_query = len(query.strip().split()) <= 6
            if has_followup_token or is_short_query:
                for pm in prior_msgs:
                    if pm.role == "assistant" and pm.citations:
                        for cit in pm.citations:
                            if isinstance(cit, dict) and cit.get("sourceType") == "document" and cit.get("documentId"):
                                explicit_doc_id = cit.get("documentId")
                                break
                    if explicit_doc_id:
                        break

            rag_res = await tool_registry.execute("rag_knowledge_lookup", user_id=user_id, db=db, query=query, explicit_doc_id=explicit_doc_id)
            if rag_res.get("mode") == "document_summary" and rag_res.get("summary"):
                sum_sources = rag_res.get("sources", [])
                for s in sum_sources:
                    citations.append({
                        "id": str(uuid.uuid4()),
                        "sourceType": "document",
                        "title": s["title"],
                        "snippet": s["snippet"],
                        "page": s.get("page"),
                        "pageLabel": s.get("pageLabel") or format_page_citation(s.get("page")),
                        "documentId": s.get("documentId")
                    })
                response_content = format_grounded_rag_response(rag_res["summary"], sum_sources[:3], query=query)
            else:
                sources = rag_res.get("sources", [])
                relevance_eval = rag_res.get("relevanceEvaluation", "sufficient_evidence")
                tool_executions.append({
                    "id": str(uuid.uuid4()),
                    "toolName": "KnowledgeBaseRetrieval",
                    "status": "success" if (sources and relevance_eval != "insufficient_evidence") else "insufficient_evidence",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "resultSummary": f"Retrieved {len(sources)} grounded document chunks (mode: {rag_res.get('retrievalMode', 'hybrid')})."
                })

                if sources and relevance_eval != "insufficient_evidence":
                    for s in sources:
                        citations.append({
                            "id": str(uuid.uuid4()),
                            "sourceType": "document",
                            "title": s["title"],
                            "snippet": s["snippet"],
                            "page": s.get("page"),
                            "pageLabel": s.get("pageLabel") or format_page_citation(s.get("page")),
                            "documentId": s.get("documentId")
                        })

                    evidence_blocks = "\n\n".join([
                        f"[{s['title']} - {s.get('pageLabel') or format_page_citation(s.get('page'))}]\n{s.get('fullContent', s['snippet'])}"
                        for s in sources[:4]
                    ])

                    if settings.GEMINI_API_KEY:
                        user_prompt = (
                            f"{history_context}"
                            f"[Retrieved Document Evidence]\n{evidence_blocks}\n\n"
                            f"[User Question]\n{query}\n\n"
                            f"INSTRUCTIONS:\n"
                            f"1. Answer the user's SPECIFIC question directly in the first sentence.\n"
                            f"2. Lead with facts that directly address the question.\n"
                            f"3. Base your answer strictly on the retrieved document evidence above.\n"
                            f"4. If the evidence is insufficient, state exactly: "
                            f"'The uploaded documents do not provide enough information to answer this question.'\n"
                            f"5. Do not invent facts, citations, or identifiers not present in the evidence."
                        )
                        gemini_res = await call_gemini_api(
                            user_prompt, SPECIFIC_RAG_PROMPT,
                            max_output_tokens=2048, temperature=0.1
                        )

                        if not gemini_res.success:
                            return {
                                "id": f"asst_err_{uuid.uuid4().hex[:8]}",
                                "conversationId": conversation_id,
                                "role": "assistant",
                                "content": gemini_res.user_message,
                                "status": "error",
                                "error": {
                                    "category": gemini_res.error_category,
                                    "message": gemini_res.user_message,
                                    "statusCode": gemini_res.status_code
                                },
                                "toolExecutions": tool_executions,
                                "citations": [],
                                "suggestedAction": None,
                                "diagnostics": {
                                    "promptVersion": PROMPT_VERSION,
                                    "selectedTool": selected_tool,
                                    "retrievalCount": len(sources),
                                    "model": settings.LLM_MODEL,
                                    "status": "error",
                                    "errorCategory": gemini_res.error_category,
                                    "statusCode": gemini_res.status_code,
                                    "finishReason": gemini_res.finish_reason,
                                    "geminiCalled": True
                                }
                            }

                        raw_answer = gemini_res.text
                    else:
                        return {
                            "id": f"asst_err_{uuid.uuid4().hex[:8]}",
                            "conversationId": conversation_id,
                            "role": "assistant",
                            "content": "Gemini API key is not configured. Answer generation requires a valid API key.",
                            "status": "error",
                            "error": {
                                "category": "missing_api_key",
                                "message": "Gemini API key is not configured. Please check your system configuration.",
                                "statusCode": 500
                            },
                            "toolExecutions": tool_executions,
                            "citations": [],
                            "suggestedAction": None,
                            "diagnostics": {
                                "status": "error",
                                "errorCategory": "missing_api_key",
                                "geminiCalled": False
                            }
                        }

                    response_content = format_grounded_rag_response(raw_answer, sources, query=query)
                else:
                    response_content = "**Answer:**\nThe uploaded documents do not provide enough information to answer this question."

        # Step 3: Global LLM Synthesis with Gemini (for non-RAG tools where synthesis adds value and wasn't already run)
        already_synthesized = [
            "document_summary", "rag_knowledge_lookup", "multi_service_planner",
            "drive_search_and_read", "gmail_search_and_summarize",
            "calendar_mark_leave", "calendar_propose_event",
            "calendar_delete_event", "calendar_update_event",
            "plan_create", "plan_update", "plan_complete_task",
            "plan_reschedule_task", "plan_delete", "plan_list",
            "plan_add_task", "plan_delete_task", "plan_get",
            "plan_propose_schedule", "plan_sync_calendar",
            "general_qa", "gmail_send_message", "gmail_create_draft",
            "document_inventory", "calendar_events_retrieval",
            "search_timetable", "timetable_lookup", "get_uploaded_documents",
            "get_timetable_for_day", "get_timetable_period", "get_timetable_period_by_time",
            "get_timetable_between_times", "get_timetable_periods", "get_full_timetable", "get_next_class"
        ]
        if settings.GEMINI_API_KEY and response_content and selected_tool not in already_synthesized and not suggested_action:
            user_prompt = f"{history_context}[Grounding Evidence from Tools]\n{response_content}\n\n[User Query]\n{query}"
            gemini_res = await call_gemini_api(user_prompt, AURELIA_SYSTEM_PROMPT)
            if gemini_res.success and gemini_res.text:
                response_content = gemini_res.text

        # Step 4: Persist Tool Log
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        log = ToolExecutionLog(
            user_id=user_id,
            tool_name=tool_executions[0]["toolName"] if tool_executions else "AgentOrchestration",
            status="success",
            parameters={"query": query, "tool": selected_tool, "version": PROMPT_VERSION},
            result_summary=response_content[:200],
            execution_duration_ms=duration_ms
        )
        db.add(log)
        db.commit()

        return {
            "id": f"asst_{uuid.uuid4().hex[:8]}",
            "conversationId": conversation_id,
            "role": "assistant",
            "content": response_content,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "toolExecutions": tool_executions,
            "citations": citations,
            "suggestedAction": suggested_action,
            "diagnostics": {
                "promptVersion": PROMPT_VERSION,
                "selectedTool": selected_tool,
                "retrievalCount": len(citations),
                "model": settings.LLM_MODEL if settings.GEMINI_API_KEY else "offline_deterministic",
                "status": "success"
            }
        }

agent_orchestrator = AureliaAgent()
