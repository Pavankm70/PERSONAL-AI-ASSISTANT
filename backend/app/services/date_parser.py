import re
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional, Tuple, Dict, Any, List
import zoneinfo

WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6
}

MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}

MONTH_REGEX_PART = r'(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)'

DATE_PATTERN_MDY = re.compile(
    rf'\b({MONTH_REGEX_PART})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b',
    re.IGNORECASE
)

DATE_PATTERN_DMY = re.compile(
    rf'\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({MONTH_REGEX_PART})\.?(?:,?\s+(\d{{4}}))?\b',
    re.IGNORECASE
)

DATE_PATTERN_ISO = re.compile(
    r'\b(\d{4})-(\d{2})-(\d{2})\b'
)

def parse_explicit_calendar_date(text: str, ref_date: Optional[date] = None) -> Optional[date]:
    """
    Extracts an explicit calendar date from natural language text, such as:
    'October 28, 2026', 'Oct 28 2026', '28 October 2026', '28th of October 2026',
    'October 28', '2026-10-28'.
    """
    if ref_date is None:
        ref_date = date.today()

    # 1. ISO date check: YYYY-MM-DD
    iso_match = DATE_PATTERN_ISO.search(text)
    if iso_match:
        try:
            return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            pass

    # 2. Month-Day-Year check: 'October 28, 2026' or 'Oct 28'
    mdy_match = DATE_PATTERN_MDY.search(text)
    if mdy_match:
        m_str = mdy_match.group(1).lower()
        month = MONTH_NAMES.get(m_str)
        day = int(mdy_match.group(2))
        year_str = mdy_match.group(3)
        if year_str:
            year = int(year_str)
        else:
            year = ref_date.year
            try:
                if date(year, month, day) < ref_date:
                    year += 1
            except ValueError:
                pass
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # 3. Day-Month-Year check: '28 October 2026' or '28th of October'
    dmy_match = DATE_PATTERN_DMY.search(text)
    if dmy_match:
        day = int(dmy_match.group(1))
        m_str = dmy_match.group(2).lower()
        month = MONTH_NAMES.get(m_str)
        year_str = dmy_match.group(3)
        if year_str:
            year = int(year_str)
        else:
            year = ref_date.year
            try:
                if date(year, month, day) < ref_date:
                    year += 1
            except ValueError:
                pass
        try:
            return date(year, month, day)
        except ValueError:
            pass

    return None

TIME_PATTERNS = [
    # 3:30 PM, 03:30 pm, 3:30pm
    (re.compile(r'\b(\d{1,2}):(\d{2})\s*(am|pm)\b', re.IGNORECASE), "hm_ampm"),
    # 3 PM, 11 am
    (re.compile(r'\b(\d{1,2})\s*(am|pm)\b', re.IGNORECASE), "h_ampm"),
    # 15:30 (24h)
    (re.compile(r'\b([01]?\d|2[0-3]):([0-5]\d)\b'), "24h"),
    # at 3 (implied PM if 1-6)
    (re.compile(r'\bat\s+(\d{1,2})\b', re.IGNORECASE), "at_h")
]

DURATION_PATTERNS = [
    (re.compile(r'for\s+(\d+)\s*(?:hour|hr)s?', re.IGNORECASE), "hours"),
    (re.compile(r'for\s+(\d+)\s*(?:minute|min)s?', re.IGNORECASE), "minutes"),
    (re.compile(r'for\s+half\s+(?:an\s+)?hour', re.IGNORECASE), "half_hour"),
    (re.compile(r'for\s+an\s+hour', re.IGNORECASE), "one_hour"),
]

def parse_natural_time(text: str) -> Optional[time]:
    """Extracts a clock time from text, or returns None."""
    lower = text.lower()
    
    # Check general time of day keywords
    if "noon" in lower:
        return time(12, 0)
    if "midnight" in lower:
        return time(0, 0)
    if "morning" in lower and not any(re.search(p[0], lower) for p in TIME_PATTERNS):
        return time(9, 0)
    if "afternoon" in lower and not any(re.search(p[0], lower) for p in TIME_PATTERNS):
        return time(14, 0)
    if "evening" in lower and not any(re.search(p[0], lower) for p in TIME_PATTERNS):
        return time(18, 0)
    if "night" in lower and not any(re.search(p[0], lower) for p in TIME_PATTERNS):
        return time(20, 0)

    for pattern, ptype in TIME_PATTERNS:
        match = pattern.search(lower)
        if match:
            if ptype == "hm_ampm":
                h, m, ampm = int(match.group(1)), int(match.group(2)), match.group(3).lower()
                if ampm == "pm" and h < 12:
                    h += 12
                elif ampm == "am" and h == 12:
                    h = 0
                return time(h, m)
            elif ptype == "h_ampm":
                h, ampm = int(match.group(1)), match.group(2).lower()
                if ampm == "pm" and h < 12:
                    h += 12
                elif ampm == "am" and h == 12:
                    h = 0
                return time(h, 0)
            elif ptype == "24h":
                h, m = int(match.group(1)), int(match.group(2))
                return time(h, m)
            elif ptype == "at_h":
                h = int(match.group(1))
                if 1 <= h <= 6:
                    h += 12 # Assume afternoon for business hours (e.g., at 3 -> 15:00)
                return time(h, 0)

    return None

def parse_natural_duration_minutes(text: str, default_minutes: int = 60) -> int:
    """Extracts duration in minutes from natural language text."""
    lower = text.lower()
    for pattern, ptype in DURATION_PATTERNS:
        match = pattern.search(lower)
        if match:
            if ptype == "hours":
                return int(match.group(1)) * 60
            elif ptype == "minutes":
                return int(match.group(1))
            elif ptype == "half_hour":
                return 30
            elif ptype == "one_hour":
                return 60
    return default_minutes

def parse_natural_datetime(
    query: str,
    user_tz_str: str = "UTC",
    reference_dt: Optional[datetime] = None
) -> Tuple[datetime, datetime, Dict[str, Any]]:
    """
    Deterministically normalizes natural language dates and times into timezone-aware datetimes.
    Handles 'today', 'tomorrow', 'yesterday', 'this Friday', 'next Monday', ISO timestamps,
    times like '3 PM', '10:30 AM', durations, and timezones.
    
    NEVER throws on natural language or passes strings like 'tomorrow' to datetime.fromisoformat.
    Returns: (start_datetime, end_datetime, metadata)
    """
    # 1. Resolve timezone safely
    try:
        tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        tz = timezone.utc

    # 2. Establish current reference point in user's timezone
    if reference_dt is None:
        ref_now = datetime.now(tz)
    else:
        ref_now = reference_dt.astimezone(tz) if reference_dt.tzinfo else reference_dt.replace(tzinfo=tz)

    lower = query.lower()

    # 3. Check for ISO 8601 timestamps in the query first
    iso_match = re.search(r'\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?\b', query)
    if iso_match:
        iso_str = iso_match.group(0)
        try:
            if "T" in iso_str:
                parsed_dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=tz)
                dur = parse_natural_duration_minutes(query)
                return parsed_dt, parsed_dt + timedelta(minutes=dur), {"parsedType": "iso_explicit", "timezone": str(tz)}
            else:
                # Date only ISO (YYYY-MM-DD)
                d_obj = date.fromisoformat(iso_str)
                t_obj = parse_natural_time(query) or time(10, 0)
                combined = datetime.combine(d_obj, t_obj, tzinfo=tz)
                dur = parse_natural_duration_minutes(query)
                return combined, combined + timedelta(minutes=dur), {"parsedType": "iso_date_with_time", "timezone": str(tz)}
        except Exception:
            pass

    # 4. Resolve Target Calendar Date
    target_date = ref_now.date()
    date_type = "today"

    explicit_cal_date = parse_explicit_calendar_date(query, ref_date=ref_now.date())
    if explicit_cal_date:
        target_date = explicit_cal_date
        date_type = "explicit_date"
    elif "tomorrow" in lower:
        target_date = ref_now.date() + timedelta(days=1)
        date_type = "tomorrow"
    elif "yesterday" in lower:
        target_date = ref_now.date() - timedelta(days=1)
        date_type = "yesterday"
    elif "day after tomorrow" in lower:
        target_date = ref_now.date() + timedelta(days=2)
        date_type = "day_after_tomorrow"
    else:
        # Check weekday expressions: "this friday", "next monday", "on tuesday"
        found_weekday = False
        for day_name, day_idx in WEEKDAYS.items():
            if re.search(rf'\b(?:this\s+|next\s+|on\s+)?{day_name}\b', lower):
                current_day_idx = ref_now.weekday() # 0 = Monday
                diff = (day_idx - current_day_idx) % 7
                if diff == 0 and "next" in lower:
                    diff = 7
                elif diff == 0 and not ("today" in lower or "this" in lower):
                    diff = 7 # e.g. on Friday when today is Friday -> next Friday
                target_date = ref_now.date() + timedelta(days=diff)
                date_type = f"weekday_{day_name}"
                found_weekday = True
                break

    # 5. Resolve Clock Time
    target_time = parse_natural_time(query)
    if target_time is None:
        # Reasonable default business hour if time was omitted
        if date_type in ["tomorrow", "day_after_tomorrow"] or "weekday" in date_type:
            target_time = time(10, 0) # 10:00 AM
        else:
            # If today and morning has passed, schedule for next convenient hour
            current_hour = ref_now.hour
            next_hour = (current_hour + 2) if current_hour < 21 else 9
            target_time = time(next_hour % 24, 0)

    # 6. Extract Duration
    duration_mins = parse_natural_duration_minutes(query, default_minutes=60)

    # 7. Construct timezone-aware datetimes
    start_dt = datetime.combine(target_date, target_time, tzinfo=tz)
    end_dt = start_dt + timedelta(minutes=duration_mins)

    return start_dt, end_dt, {
        "dateType": date_type,
        "durationMinutes": duration_mins,
        "timezone": str(tz),
        "isFuture": start_dt > ref_now
    }

def _parse_time_token(token: str, context_ampm: Optional[str] = None) -> Optional[time]:
    """Helper to parse a single time token like '7', '7 AM', '18:00', '9:30 pm'."""
    token = token.strip().lower()
    m_ampm = re.match(r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$', token)
    if m_ampm:
        h = int(m_ampm.group(1))
        m = int(m_ampm.group(2) or 0)
        ampm = m_ampm.group(3)
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        return time(h, m)

    m_num = re.match(r'^(\d{1,2})(?::(\d{2}))?$', token)
    if m_num:
        h = int(m_num.group(1))
        m = int(m_num.group(2) or 0)
        if context_ampm in ("morning", "am"):
            if h == 12:
                h = 0
        elif context_ampm in ("afternoon", "evening", "night", "pm"):
            if h < 12:
                h += 12
        elif 1 <= h <= 6:
            h += 12
        return time(h, m)
    return None

def parse_natural_time_intervals(
    query: str,
    user_tz_str: str = "UTC",
    reference_dt: Optional[datetime] = None
) -> List[Tuple[datetime, datetime, Dict[str, Any]]]:
    """
    Parses one or multiple time intervals from phrases like:
    'from 7 AM to 9 AM and 6 PM to 8 PM'
    'from 7 to 9 in the morning'
    'between 2 PM and 4 PM'
    """
    try:
        tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        tz = timezone.utc

    if reference_dt is None:
        ref_now = datetime.now(tz)
    else:
        ref_now = reference_dt.astimezone(tz) if reference_dt.tzinfo else reference_dt.replace(tzinfo=tz)

    lower = query.lower()
    target_date = ref_now.date()
    if "tomorrow" in lower:
        target_date = ref_now.date() + timedelta(days=1)
    elif "yesterday" in lower:
        target_date = ref_now.date() - timedelta(days=1)
    elif "day after tomorrow" in lower:
        target_date = ref_now.date() + timedelta(days=2)
    else:
        for day_name, day_idx in WEEKDAYS.items():
            if re.search(rf'\b(?:this\s+|next\s+|on\s+)?{day_name}\b', lower):
                diff = (day_idx - ref_now.weekday()) % 7
                if diff == 0 and "next" in lower:
                    diff = 7
                target_date = ref_now.date() + timedelta(days=diff)
                break

    interval_regex = re.compile(
        r'(?:from|between)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|and|-)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)(?:\s+(?:in\s+the\s+)?(morning|afternoon|evening|night))?',
        re.IGNORECASE
    )

    matches = list(interval_regex.finditer(query))
    intervals = []
    for m in matches:
        start_tok = m.group(1).strip()
        end_tok = m.group(2).strip()
        period_hint = (m.group(3) or "").lower()

        start_ampm = "am" if "am" in start_tok.lower() else ("pm" if "pm" in start_tok.lower() else None)
        end_ampm = "am" if "am" in end_tok.lower() else ("pm" if "pm" in end_tok.lower() else None)
        if not start_ampm and end_ampm:
            start_ampm = end_ampm

        t_start = _parse_time_token(start_tok, context_ampm=start_ampm or period_hint)
        t_end = _parse_time_token(end_tok, context_ampm=end_ampm or period_hint)

        if t_start and t_end:
            dt_start = datetime.combine(target_date, t_start, tzinfo=tz)
            dt_end = datetime.combine(target_date, t_end, tzinfo=tz)
            if dt_end <= dt_start:
                dt_end += timedelta(hours=12)
            duration = int((dt_end - dt_start).total_seconds() / 60)
            intervals.append((dt_start, dt_end, {
                "start": dt_start.isoformat(),
                "end": dt_end.isoformat(),
                "durationMinutes": duration,
                "timezone": str(tz)
            }))

    return intervals

def parse_leave_request(query: str, user_tz_str: str = "UTC") -> Optional[Dict[str, Any]]:
    """
    Detects personal leave, sickness, or holiday requests.
    e.g. 'I have a fever tomorrow. Mark tomorrow as a holiday and remove my study sessions.'
    e.g. 'Mark tomorrow as a holiday.'
    """
    lower = query.lower()
    # If the user is merely querying, listing, or asking about holidays or events, it's not a leave creation request
    if any(q_word in lower for q_word in ["list", "what", "which", "show", "tell", "when", "how many", "are there", "any holidays"]):
        return None

    leave_keywords = ["fever", "sick", "mark tomorrow as a holiday", "mark as a holiday", "mark today as a holiday", "personal leave", "day off", "unwell", "ill", "not feeling well", "doctor appointment"]
    if not any(k in lower for k in leave_keywords) and not ("holiday" in lower and any(act in lower for act in ["mark", "take", "declare", "set", "book"])):
        return None

    try:
        tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        tz = timezone.utc

    ref_now = datetime.now(tz)
    explicit_date = parse_explicit_calendar_date(query, ref_date=ref_now.date())
    if explicit_date:
        target_date = explicit_date
    elif "tomorrow" in lower:
        target_date = ref_now.date() + timedelta(days=1)
    elif "today" in lower:
        target_date = ref_now.date()
    elif "day after tomorrow" in lower:
        target_date = ref_now.date() + timedelta(days=2)
    else:
        for day_name, day_idx in WEEKDAYS.items():
            if re.search(rf'\b{day_name}\b', lower):
                diff = (day_idx - ref_now.weekday()) % 7
                if diff == 0 and "next" in lower:
                    diff = 7
                target_date = ref_now.date() + timedelta(days=diff)
                break
        else:
            target_date = ref_now.date()

    all_day_start = datetime.combine(target_date, time(0, 0, 0), tzinfo=tz)
    all_day_end = datetime.combine(target_date, time(23, 59, 59), tzinfo=tz)

    remove_study = any(w in lower for w in [
        "remove my study", "remove study", "cancel my study", "cancel study",
        "delete my study", "clear my study", "drop study", "reschedule my study"
    ])

    title = "Personal Leave / Sick Day" if any(w in lower for w in ["fever", "sick", "ill", "unwell"]) else "Personal Holiday / Leave"

    return {
        "is_leave": True,
        "target_date": target_date.isoformat(),
        "title": title,
        "all_day_start": all_day_start.isoformat(),
        "all_day_end": all_day_end.isoformat(),
        "remove_study_sessions": remove_study,
        "date_str": target_date.strftime("%A, %B %d, %Y")
    }

# --- Standardized Timezone & Date Range Helpers ---

def get_user_tz(user_tz_str: Optional[str] = None) -> zoneinfo.ZoneInfo:
    """Safely retrieves a ZoneInfo instance for user's configured timezone, defaulting to UTC."""
    if user_tz_str and isinstance(user_tz_str, str) and user_tz_str.strip():
        try:
            return zoneinfo.ZoneInfo(user_tz_str.strip())
        except Exception:
            pass
    return zoneinfo.ZoneInfo("UTC")

def get_user_current_date(user_tz_str: Optional[str] = None) -> date:
    """Returns the current calendar date in the user's timezone."""
    tz = get_user_tz(user_tz_str)
    return datetime.now(tz).date()

def get_user_today_bounds(user_tz_str: Optional[str] = None) -> Tuple[datetime, datetime, str, str]:
    """
    Returns (start_of_day_dt, end_of_day_dt, start_iso, end_iso) strictly aligned
    to the user's local calendar day boundaries (00:00:00 to 23:59:59.999999).
    """
    tz = get_user_tz(user_tz_str)
    local_now = datetime.now(tz)
    today = local_now.date()
    start_dt = datetime.combine(today, time(0, 0, 0, 0), tzinfo=tz)
    end_dt = datetime.combine(today, time(23, 59, 59, 999999), tzinfo=tz)
    return start_dt, end_dt, start_dt.isoformat(), end_dt.isoformat()

def get_user_week_bounds(user_tz_str: Optional[str] = None, week_starts_monday: bool = True) -> Tuple[datetime, datetime, str, str]:
    """
    Returns inclusive week boundaries in the user's timezone.
    """
    tz = get_user_tz(user_tz_str)
    local_now = datetime.now(tz)
    today = local_now.date()
    day_of_week = today.weekday() # 0 = Monday, 6 = Sunday
    offset = day_of_week if week_starts_monday else (day_of_week + 1) % 7
    week_start_date = today - timedelta(days=offset)
    week_end_date = week_start_date + timedelta(days=6)

    start_dt = datetime.combine(week_start_date, time(0, 0, 0, 0), tzinfo=tz)
    end_dt = datetime.combine(week_end_date, time(23, 59, 59, 999999), tzinfo=tz)
    return start_dt, end_dt, start_dt.isoformat(), end_dt.isoformat()

def get_user_month_bounds(user_tz_str: Optional[str] = None) -> Tuple[datetime, datetime, str, str]:
    """
    Returns inclusive month boundaries in the user's timezone.
    """
    tz = get_user_tz(user_tz_str)
    local_now = datetime.now(tz)
    today = local_now.date()
    month_start_date = today.replace(day=1)
    
    # Calculate last day of month
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    month_end_date = next_month - timedelta(days=1)

    start_dt = datetime.combine(month_start_date, time(0, 0, 0, 0), tzinfo=tz)
    end_dt = datetime.combine(month_end_date, time(23, 59, 59, 999999), tzinfo=tz)
    return start_dt, end_dt, start_dt.isoformat(), end_dt.isoformat()

def is_date_today_in_user_tz(target_date_str: str, user_tz_str: Optional[str] = None) -> bool:
    """
    Checks if a target date string ('YYYY-MM-DD' or ISO) matches today's date in user's timezone.
    """
    if not target_date_str:
        return False
    tz = get_user_tz(user_tz_str)
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    clean_target = target_date_str[:10]
    return clean_target == today_str

def get_user_greeting(user_tz_str: Optional[str] = None) -> str:
    """
    Returns greeting based on the user's localized clock hour.
    Morning:   5:00 AM – 11:59 AM
    Afternoon: 12:00 PM – 4:59 PM
    Evening:   5:00 PM – 8:59 PM
    Night:     9:00 PM – 4:59 AM
    """
    tz = get_user_tz(user_tz_str)
    local_now = datetime.now(tz)
    hour = local_now.hour
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    elif 17 <= hour < 21:
        return "Good evening"
    else:
        return "Good night"


