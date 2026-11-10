import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Callable, Optional
from sqlalchemy.orm import Session
from app.db.models import User, Timetable, TimetablePeriod, TimetableEntry, Document, DocumentChunk, Plan, PlanTask
from app.rag.retrieval import retrieve_knowledge
from app.services.google_services.gmail_service import google_gmail_service
from app.services.google_services.calendar_service import google_calendar_service
from app.services.google_services.drive_service import google_drive_service
from app.services.weather_service import weather_service
from app.services.web_search_service import web_search_service
from app.services.capabilities import is_capability_enabled
from app.services.date_parser import get_user_current_date, get_user_tz
from app.services.table_extractor import DAY_MAP, VALID_CATEGORIES

def parse_time_str_to_minutes(t_str: str) -> Optional[int]:
    """Converts strings like '09:00 AM', '2 PM', '14:30', '9:00' to minutes from midnight."""
    if not t_str:
        return None
    s = t_str.strip().upper()
    m = re.match(r'(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?', s)
    if not m:
        return None
    h = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    meridiem = m.group(3)
    if meridiem == "PM" and h < 12:
        h += 12
    elif meridiem == "AM" and h == 12:
        h = 0
    return h * 60 + minute

ORDINAL_MAP = {
    'first': 1, '1st': 1, 'one': 1,
    'second': 2, '2nd': 2, 'two': 2,
    'third': 3, '3rd': 3, 'three': 3,
    'fourth': 4, '4th': 4, 'four': 4,
    'fifth': 5, '5th': 5, 'five': 5,
    'sixth': 6, '6th': 6, 'six': 6,
    'seventh': 7, '7th': 7, 'seven': 7,
    'eighth': 8, '8th': 8, 'eight': 8,
    'ninth': 9, '9th': 9, 'nine': 9,
    'tenth': 10, '10th': 10, 'ten': 10,
    'last': -1, 'final': -1
}

def normalize_timetable_day(day_str: str) -> str:
    cleaned = (day_str or "").strip().lower()
    return DAY_MAP.get(cleaned, day_str.strip().capitalize() if day_str else "Monday")

def format_period_line(p: Dict[str, Any]) -> str:
    p_num = p.get("periodNumber") or p.get("period_number") or 1
    subj = p.get("subjectName") or p.get("course") or "Class"
    code = p.get("subjectCode") or p.get("code") or ""
    start_t = p.get("startTime") or p.get("start_time") or ""
    end_t = p.get("endTime") or p.get("end_time") or ""
    room = p.get("room") or "TBD"
    faculty = p.get("faculty") or p.get("instructor") or "Faculty"
    c_type = p.get("classType") or p.get("class_type") or "Lecture"

    subj_display = f"{subj} ({code})" if code else subj
    return f"• Period {p_num}: {subj_display} | {start_t} - {end_t} | Room: {room} | Faculty: {faculty} | Type: {c_type}"

def get_user_timetable_periods(user_id: str, db: Session, day: Optional[str] = None) -> List[Dict[str, Any]]:
    periods = db.query(TimetablePeriod).filter(TimetablePeriod.user_id == user_id).all()
    if not periods:
        periods = db.query(TimetableEntry).filter(TimetableEntry.user_id == user_id).all()

    if not periods:
        return []

    norm_filter_day = normalize_timetable_day(day) if day else None

    # Group by normalized day of week
    day_groups: Dict[str, List[Any]] = {}
    for p in periods:
        d = normalize_timetable_day(getattr(p, "day_of_week", "") or "")
        if norm_filter_day and d.lower() != norm_filter_day.lower():
            continue
        day_groups.setdefault(d, []).append(p)

    day_order_list = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    sorted_days = sorted(day_groups.keys(), key=lambda d: day_order_list.index(d) if d in day_order_list else 99)

    res: List[Dict[str, Any]] = []
    for d in sorted_days:
        d_periods = day_groups[d]
        d_periods.sort(key=lambda p: parse_time_str_to_minutes(getattr(p, "start_time", "")) or 0)
        for idx, p in enumerate(d_periods):
            explicit_num = getattr(p, "period_number", None)
            eff_num = explicit_num if (explicit_num is not None and explicit_num > 0) else (idx + 1)
            c_name = getattr(p, "subject_name", None) or getattr(p, "course_name", "") or ""
            c_code = getattr(p, "subject_code", None) or getattr(p, "course_code", "") or ""
            fac = getattr(p, "faculty", None) or getattr(p, "instructor", "") or "Faculty"
            room_val = getattr(p, "room", None) or getattr(p, "room_number", "") or "TBD"
            c_type = getattr(p, "class_type", None) or "Lecture"
            notes_val = getattr(p, "notes", "") or ""
            s_time = getattr(p, "start_time", "") or ""
            e_time = getattr(p, "end_time", "") or ""

            res.append({
                "id": str(p.id),
                "periodNumber": eff_num,
                "period_number": eff_num,
                "course": c_name,
                "subjectName": c_name,
                "subject_name": c_name,
                "code": c_code,
                "subjectCode": c_code,
                "subject_code": c_code,
                "day": d,
                "dayOfWeek": d,
                "day_of_week": d,
                "time": f"{s_time} - {e_time}",
                "startTime": s_time,
                "start_time": s_time,
                "endTime": e_time,
                "end_time": e_time,
                "room": room_val,
                "faculty": fac,
                "instructor": fac,
                "classType": c_type,
                "class_type": c_type,
                "notes": notes_val
            })
    return res

def parse_period_query_details(lower_q: str, user_curr_day: str = "Monday") -> Dict[str, Any]:
    target_day = None
    for d_k, d_v in DAY_MAP.items():
        if re.search(rf'\b{d_k}\b', lower_q):
            target_day = d_v
            break
    if not target_day:
        if "tomorrow" in lower_q:
            target_day = "tomorrow"
        elif "today" in lower_q:
            target_day = user_curr_day

    if any(w in lower_q for w in ["complete timetable", "full timetable", "weekly timetable", "entire timetable", "whole timetable", "show my timetable", "my complete schedule"]) or (
        ("complete" in lower_q or "full" in lower_q or "weekly" in lower_q or "show" in lower_q or "view" in lower_q) and "timetable" in lower_q and not target_day
    ):
        return {"intent": "FULL_TIMETABLE"}

    if ("next" in lower_q or "upcoming" in lower_q) and any(w in lower_q for w in ["lab", "laboratory", "practical"]):
        return {"intent": "NEXT_LAB"}
    if ("next" in lower_q or "upcoming" in lower_q) and any(w in lower_q for w in ["class", "lecture", "session"]):
        m_subj = re.search(r'(?:next|upcoming)\s+([a-zA-Z0-9\+#\s]+?)\s+(?:class|lecture|lab)', lower_q)
        subj_name = m_subj.group(1).strip() if m_subj else None
        return {"intent": "NEXT_CLASS", "subject": subj_name}

    range_m = re.search(r'\b(?:periods?|from)?\s*([a-z0-9]+)\s*(?:to|-|through)\s*([a-z0-9]+)\s*periods?\b', lower_q)
    if range_m:
        w1, w2 = range_m.group(1), range_m.group(2)
        n1 = ORDINAL_MAP.get(w1, int(w1) if w1.isdigit() else None)
        n2 = ORDINAL_MAP.get(w2, int(w2) if w2.isdigit() else None)
        if n1 and n2 and n1 > 0 and n2 >= n1:
            return {"intent": "PERIODS_RANGE", "day": target_day, "period_numbers": list(range(n1, n2 + 1))}

    if ("period" in lower_q or "periods" in lower_q) and any(sep in lower_q for sep in ["and", ",", "&"]):
        tokens = re.findall(r'\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|[1-9]|10)\b', lower_q)
        nums = []
        for t in tokens:
            v = ORDINAL_MAP.get(t, int(t) if t.isdigit() else None)
            if v and v > 0 and v not in nums:
                nums.append(v)
        if len(nums) > 1:
            return {"intent": "PERIODS_MULTIPLE", "day": target_day, "period_numbers": sorted(nums)}
        elif len(nums) == 1:
            return {"intent": "PERIOD_SINGLE", "day": target_day, "period_number": nums[0]}

    single_m = re.search(r'\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|last|final)\s+period\b', lower_q)
    if not single_m:
        single_m = re.search(r'\bperiod\s+(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|[1-9]|10)\b', lower_q)
    if single_m:
        w = single_m.group(1)
        n = ORDINAL_MAP.get(w, int(w) if w.isdigit() else None)
        if n:
            return {"intent": "PERIOD_SINGLE", "day": target_day, "period_number": n}

    at_m = re.search(r'\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b', lower_q)
    if at_m and any(w in lower_q for w in ["class", "have", "schedule", "period"]):
        return {"intent": "AT_TIME", "day": target_day, "time": at_m.group(1).strip()}

    btw_m = re.search(r'between\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:and|to|-)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)', lower_q)
    if btw_m:
        return {"intent": "BETWEEN_TIMES", "day": target_day, "start_time": btw_m.group(1).strip(), "end_time": btw_m.group(2).strip()}

    if target_day and any(w in lower_q for w in ["timetable", "schedule", "classes", "what classes", "show"]):
        return {"intent": "DAY_SCHEDULE", "day": target_day}

    return {"intent": "GENERAL", "day": target_day}

class ToolRegistry:
    """
    Modular tool registry providing typed tool execution for Aurelia Agent.
    Strictly tenant-isolated by user_id and backed by real services.
    Enforces website-level capability preferences before dispatching Google requests.
    Truthful error handling: never returns invented emails, files, or calendar events.
    """
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._descriptions: Dict[str, str] = {}
        self._register_default_tools()

    def register(self, name: str, description: str):
        def decorator(func: Callable):
            self._tools[name] = func
            self._descriptions[name] = description
            return func
        return decorator

    def _register_default_tools(self):
        # 1a. Specific Day Schedule Tool
        @self.register("get_timetable_for_day", "Retrieve the complete timetable schedule for a specific day.")
        def get_timetable_for_day_tool(user_id: str, db: Session, day: str, is_tomorrow: bool = False) -> Dict[str, Any]:
            user = db.query(User).filter(User.id == user_id).first()
            user_tz = user.timezone if user else "UTC"
            user_curr_date = get_user_current_date(user_tz)
            if (day and day.strip().lower() == "tomorrow") or is_tomorrow:
                norm_day = (user_curr_date + timedelta(days=1)).strftime("%A")
                is_tomorrow = True
            else:
                norm_day = normalize_timetable_day(day)

            day_periods = get_user_timetable_periods(user_id, db, day=norm_day)
            day_label = f"tomorrow ({norm_day})" if is_tomorrow else f"**{norm_day}**"
            if not day_periods:
                all_p = get_user_timetable_periods(user_id, db)
                if not all_p:
                    return {
                        "status": "not_found",
                        "count": 0,
                        "classes": [],
                        "periods": [],
                        "customMessage": "You have not created a timetable yet. You can create your timetable in Knowledge Base under the Timetable section."
                    }
                empty_msg = f"You have no classes scheduled for tomorrow ({norm_day})." if is_tomorrow else f"You have no classes scheduled for {day_label}."
                return {
                    "status": "empty",
                    "count": 0,
                    "classes": [],
                    "periods": [],
                    "targetDay": norm_day,
                    "customMessage": empty_msg
                }
            lines = [format_period_line(p) for p in day_periods]
            return {
                "status": "success",
                "count": len(day_periods),
                "classes": day_periods,
                "periods": day_periods,
                "targetDay": norm_day,
                "customMessage": f"Here is your timetable for {day_label}:\n\n" + "\n".join(lines)
            }

        # 1b. Single Specific Period Tool
        @self.register("get_timetable_period", "Retrieve a single specific period by day and period number.")
        def get_timetable_period_tool(user_id: str, db: Session, day: str, period_number: int) -> Dict[str, Any]:
            norm_day = normalize_timetable_day(day)
            day_periods = get_user_timetable_periods(user_id, db, day=norm_day)

            target = None
            if period_number == -1 and day_periods:
                target = day_periods[-1]
            else:
                for p in day_periods:
                    if p["periodNumber"] == period_number:
                        target = p
                        break

            if not target:
                return {
                    "status": "not_found",
                    "count": 0,
                    "classes": [],
                    "periods": [],
                    "targetDay": norm_day,
                    "customMessage": "You don't have a scheduled period for that selection."
                }

            line = format_period_line(target)
            return {
                "status": "success",
                "count": 1,
                "classes": [target],
                "periods": [target],
                "targetDay": norm_day,
                "customMessage": line
            }

        # 1c. Period By Time Tool
        @self.register("get_timetable_period_by_time", "Retrieve the period covering a specific time on a day.")
        def get_timetable_period_by_time_tool(user_id: str, db: Session, day: str, time: str) -> Dict[str, Any]:
            norm_day = normalize_timetable_day(day)
            day_periods = get_user_timetable_periods(user_id, db, day=norm_day)
            t_min = parse_time_str_to_minutes(time)

            target = None
            if t_min is not None:
                for p in day_periods:
                    s_m = parse_time_str_to_minutes(p["startTime"])
                    e_m = parse_time_str_to_minutes(p["endTime"])
                    if s_m is not None and e_m is not None:
                        if s_m <= t_min < e_m:
                            target = p
                            break

            if not target:
                return {
                    "status": "not_found",
                    "count": 0,
                    "classes": [],
                    "periods": [],
                    "targetDay": norm_day,
                    "customMessage": "You don't have a scheduled period for that selection."
                }

            line = format_period_line(target)
            return {
                "status": "success",
                "count": 1,
                "classes": [target],
                "periods": [target],
                "targetDay": norm_day,
                "customMessage": line
            }

        # 1d. Between Times Tool
        @self.register("get_timetable_between_times", "Retrieve periods occurring between two times on a day.")
        def get_timetable_between_times_tool(user_id: str, db: Session, day: Optional[str] = None, start_time: str = "10:00 AM", end_time: str = "12:00 PM") -> Dict[str, Any]:
            norm_day = normalize_timetable_day(day) if (day and day.lower() not in ("none", "null", "all")) else None
            candidate_periods = get_user_timetable_periods(user_id, db, day=norm_day)
            req_s = parse_time_str_to_minutes(start_time)
            req_e = parse_time_str_to_minutes(end_time)

            matches = []
            if req_s is not None and req_e is not None:
                for p in candidate_periods:
                    s_m = parse_time_str_to_minutes(p["startTime"])
                    e_m = parse_time_str_to_minutes(p["endTime"])
                    if s_m is not None and e_m is not None:
                        if max(req_s, s_m) < min(req_e, e_m):
                            matches.append(p)

            if not matches:
                msg = "You don't have a scheduled period for that selection." if norm_day else f"You have no classes scheduled between {start_time} and {end_time}."
                return {
                    "status": "not_found",
                    "count": 0,
                    "classes": [],
                    "periods": [],
                    "targetDay": norm_day,
                    "customMessage": msg
                }

            lines = [format_period_line(p) for p in matches]
            day_suffix = f" on **{norm_day}**" if norm_day else ""
            return {
                "status": "success",
                "count": len(matches),
                "classes": matches,
                "periods": matches,
                "targetDay": norm_day,
                "customMessage": f"Here are your classes between {start_time} and {end_time}{day_suffix}:\n\n" + "\n".join(lines)
            }

        # 1e. Multiple Periods Tool
        @self.register("get_timetable_periods", "Retrieve multiple specific timetable periods by period numbers on a day.")
        def get_timetable_periods_tool(user_id: str, db: Session, day: str, period_numbers: List[int]) -> Dict[str, Any]:
            norm_day = normalize_timetable_day(day)
            day_periods = get_user_timetable_periods(user_id, db, day=norm_day)

            matches = []
            for num in period_numbers:
                for p in day_periods:
                    if p["periodNumber"] == num and p not in matches:
                        matches.append(p)

            if not matches:
                return {
                    "status": "not_found",
                    "count": 0,
                    "classes": [],
                    "periods": [],
                    "targetDay": norm_day,
                    "customMessage": "You don't have a scheduled period for that selection."
                }

            lines = [format_period_line(p) for p in matches]
            return {
                "status": "success",
                "count": len(matches),
                "classes": matches,
                "periods": matches,
                "targetDay": norm_day,
                "customMessage": f"Here are your requested periods for {norm_day}:\n\n" + "\n".join(lines)
            }

        # 1f. Full Timetable Tool
        @self.register("get_full_timetable", "Retrieve the user's complete weekly timetable across all days.")
        def get_full_timetable_tool(user_id: str, db: Session) -> Dict[str, Any]:
            all_periods = get_user_timetable_periods(user_id, db)
            if not all_periods:
                return {
                    "status": "empty",
                    "count": 0,
                    "classes": [],
                    "periods": [],
                    "customMessage": "You have not created a timetable yet. You can create your timetable in Knowledge Base under the Timetable section."
                }

            days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            by_day: Dict[str, List[Dict[str, Any]]] = {}
            for p in all_periods:
                by_day.setdefault(p["day"], []).append(p)

            week_lines = ["Here is your complete weekly timetable:\n"]
            for d in days_order:
                if d in by_day and by_day[d]:
                    week_lines.append(f"**{d}:**")
                    for p in by_day[d]:
                        week_lines.append(format_period_line(p))
                    week_lines.append("")

            return {
                "status": "success",
                "count": len(all_periods),
                "classes": all_periods,
                "periods": all_periods,
                "customMessage": "\n".join(week_lines).strip()
            }

        # 1g. Next Class Tool
        @self.register("get_next_class", "Retrieve the next upcoming class or lab session.")
        def get_next_class_tool(user_id: str, db: Session, subject: Optional[str] = None, is_lab: bool = False) -> Dict[str, Any]:
            user = db.query(User).filter(User.id == user_id).first()
            user_tz = user.timezone if user else "UTC"
            user_curr_date = get_user_current_date(user_tz)
            user_curr_day = user_curr_date.strftime("%A")
            now_dt = datetime.now(get_user_tz(user_tz))
            curr_mins = now_dt.hour * 60 + now_dt.minute

            all_periods = get_user_timetable_periods(user_id, db)
            if not all_periods:
                return {
                    "status": "empty",
                    "count": 0,
                    "classes": [],
                    "periods": [],
                    "customMessage": "You have not created a timetable yet. You can create your timetable in Knowledge Base under the Timetable section."
                }

            candidates = all_periods
            if is_lab:
                candidates = [p for p in candidates if any(w in p["classType"].lower() for w in ["lab", "practical"]) or any(w in p["course"].lower() for w in ["lab", "practical"])]
            elif subject:
                candidates = [p for p in candidates if subject.lower() in p["course"].lower() or subject.lower() in p["code"].lower()]

            if not candidates:
                kind = "lab or practical session" if is_lab else (f"'{subject}' class" if subject else "class")
                return {
                    "status": "not_found",
                    "count": 0,
                    "classes": [],
                    "periods": [],
                    "customMessage": f"You do not have any {kind} scheduled in your timetable."
                }

            days_seq = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            curr_idx = days_seq.index(user_curr_day) if user_curr_day in days_seq else 0

            found = None
            for offset in range(7):
                check_day = days_seq[(curr_idx + offset) % 7]
                day_matches = [c for c in candidates if c["day"].lower() == check_day.lower()]
                for c in day_matches:
                    s_min = parse_time_str_to_minutes(c["startTime"]) or 0
                    if offset > 0 or s_min > curr_mins:
                        found = c
                        break
                if found:
                    break

            if not found:
                for offset in range(1, 8):
                    check_day = days_seq[(curr_idx + offset) % 7]
                    day_matches = [c for c in candidates if c["day"].lower() == check_day.lower()]
                    if day_matches:
                        found = day_matches[0]
                        break

            if not found:
                return {
                    "status": "not_found",
                    "count": 0,
                    "classes": [],
                    "periods": [],
                    "customMessage": "You do not have any upcoming classes scheduled in your timetable."
                }

            subj_display = f"{found['course']} ({found['code']})" if found['code'] else found['course']
            custom_msg = f"Your next class is **{subj_display}** on **{found['day']}** (Period {found['periodNumber']}) | {found['startTime']} - {found['endTime']} | Room: {found['room']} | Faculty: {found['faculty']} | Type: {found['classType']}."
            return {
                "status": "success",
                "count": 1,
                "classes": [found],
                "periods": [found],
                "customMessage": custom_msg
            }

        # 1. Timetable Lookup & Schedule Search (General Gateway)
        @self.register("search_timetable", "Search authenticated user's weekly timetable by weekday, subject, or check free time availability.")
        @self.register("timetable_lookup", "Look up exact class schedule, timings, and rooms from timetable records.")
        def timetable_tool(
            user_id: str,
            db: Session,
            query: str = "",
            day_of_week: Optional[str] = None,
            subject: Optional[str] = None,
            time_start: Optional[str] = None,
            time_end: Optional[str] = None,
            check_availability: bool = False,
            followup_type: Optional[str] = None
        ) -> Dict[str, Any]:
            user = db.query(User).filter(User.id == user_id).first()
            user_tz = user.timezone if user else "UTC"
            user_curr_date = get_user_current_date(user_tz)
            user_curr_day = user_curr_date.strftime("%A")

            all_classes = get_user_timetable_periods(user_id, db)
            if not all_classes:
                return {
                    "count": 0,
                    "classes": [],
                    "periods": [],
                    "customMessage": "You have not created a timetable yet. You can create your timetable in Knowledge Base under the Timetable section."
                }

            lower_q = (query or "").lower().strip()

            # Inspect query with precise period parser details
            details = parse_period_query_details(lower_q, user_curr_day=user_curr_day)
            intent = details.get("intent")
            resolved_day = details.get("day") or day_of_week
            if resolved_day == "tomorrow":
                resolved_day = (user_curr_date + timedelta(days=1)).strftime("%A")
            elif resolved_day == "today":
                resolved_day = user_curr_day

            # Dispatch to specialized tools if matched
            if intent == "PERIOD_SINGLE":
                target_day_to_use = resolved_day or user_curr_day
                return get_timetable_period_tool(user_id, db, day=target_day_to_use, period_number=details["period_number"])

            if intent in ("PERIODS_MULTIPLE", "PERIODS_RANGE"):
                target_day_to_use = resolved_day or user_curr_day
                return get_timetable_periods_tool(user_id, db, day=target_day_to_use, period_numbers=details["period_numbers"])

            if intent == "AT_TIME":
                target_day_to_use = resolved_day or user_curr_day
                return get_timetable_period_by_time_tool(user_id, db, day=target_day_to_use, time=details["time"])

            if intent == "BETWEEN_TIMES":
                return get_timetable_between_times_tool(user_id, db, day=resolved_day, start_time=details["start_time"], end_time=details["end_time"])

            if intent == "FULL_TIMETABLE":
                return get_full_timetable_tool(user_id, db)

            if intent == "NEXT_LAB":
                return get_next_class_tool(user_id, db, is_lab=True)

            if intent == "NEXT_CLASS":
                return get_next_class_tool(user_id, db, subject=details.get("subject"))

            if intent == "DAY_SCHEDULE":
                is_tom = "tomorrow" in lower_q
                return get_timetable_for_day_tool(user_id, db, day=resolved_day, is_tomorrow=is_tom)

            # 1. Check for Overlapping Classes Query
            is_overlap_q = any(w in lower_q for w in ["overlapping", "overlap", "clash", "conflict", "double booked"])
            if is_overlap_q and not time_start:
                day_groups: Dict[str, List[Dict[str, Any]]] = {}
                for c in all_classes:
                    day_groups.setdefault(c["day"], []).append(c)

                overlaps = []
                for day_name, day_entries in day_groups.items():
                    for i in range(len(day_entries)):
                        for j in range(i + 1, len(day_entries)):
                            e1, e2 = day_entries[i], day_entries[j]
                            s1 = parse_time_str_to_minutes(e1["startTime"])
                            e_1 = parse_time_str_to_minutes(e1["endTime"])
                            s2 = parse_time_str_to_minutes(e2["startTime"])
                            e_2 = parse_time_str_to_minutes(e2["endTime"])
                            if s1 is not None and e_1 is not None and s2 is not None and e_2 is not None:
                                if max(s1, s2) < min(e_1, e_2):
                                    overlaps.append(f"• **{e1['course']}** ({e1['startTime']}-{e1['endTime']}) clashes with **{e2['course']}** ({e2['startTime']}-{e2['endTime']}) on {day_name}.")

                if overlaps:
                    custom_msg = "You have the following overlapping classes in your timetable:\n\n" + "\n".join(overlaps)
                else:
                    custom_msg = "According to your timetable records, you have no overlapping classes scheduled."
                return {
                    "count": len(overlaps),
                    "classes": [],
                    "customMessage": custom_msg
                }

            # 2. Check for Complete Weekly Schedule Query
            is_complete_timetable_q = any(w in lower_q for w in ["complete timetable", "full timetable", "weekly timetable", "entire timetable", "whole timetable", "show my timetable", "my complete schedule"]) or (
                ("complete" in lower_q or "full" in lower_q or "weekly" in lower_q or "show" in lower_q or "view" in lower_q) and "timetable" in lower_q and not any(w in lower_q for w in ["tomorrow", "today", "yesterday", "next", "last class", "free period", "free periods", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "lab", "faculty", "who"])
            )
            if is_complete_timetable_q:
                return get_full_timetable_tool(user_id, db)

            # 3. Detect target day
            target_day = resolved_day

            # 4. Detect target subject
            target_subject = subject
            if not target_subject:
                for c in all_classes:
                    c_clean = c["course"].lower()
                    c_code_clean = c["code"].lower() if c["code"] else ""
                    if c_clean and re.search(rf'\b{re.escape(c_clean)}\b', lower_q):
                        target_subject = c["course"]
                        break
                    elif c_code_clean and re.search(rf'\b{re.escape(c_code_clean)}\b', lower_q):
                        target_subject = c["course"]
                        break
                    elif len(c_clean.split()) > 0 and len(c_clean.split()[0]) >= 3 and re.search(rf'\b{re.escape(c_clean.split()[0])}\b', lower_q):
                        target_subject = c["course"]
                        break

            if not target_subject:
                common_subjs = ["java", "dbms", "python", "dsa", "c++", "ai", "machine learning", "operating system", "networks", "math", "algorithms", "software engineering", "web dev", "compiler"]
                for s in common_subjs:
                    if re.search(rf'\b{re.escape(s)}\b', lower_q):
                        target_subject = s.upper()
                        break

            # 5. Query: "What is my last class today?"
            is_last_class_q = any(w in lower_q for w in ["last class", "final class", "end of day class"])
            if is_last_class_q:
                day_for_last = target_day or user_curr_day
                day_classes = [c for c in all_classes if c["day"].lower() == day_for_last.lower()]
                if not day_classes:
                    return {
                        "count": 0,
                        "classes": [],
                        "targetDay": day_for_last,
                        "customMessage": f"You have no classes scheduled for {'today' if day_for_last == user_curr_day else day_for_last} (**{day_for_last}**)."
                    }
                day_sorted = sorted(day_classes, key=lambda x: parse_time_str_to_minutes(x["startTime"]) or 0)
                last_c = day_sorted[-1]
                return {
                    "count": 1,
                    "classes": [last_c],
                    "targetDay": day_for_last,
                    "customMessage": f"Your last class {'today' if day_for_last == user_curr_day else f'on {day_for_last}'} is **{last_c['course']}** ({last_c['code']}) from **{last_c['time']}** in room **{last_c['room']}** (taught by **{last_c['instructor']}**)."
                }

            # 6. Query: "When is my next lab?" / "next lab"
            is_next_lab_q = ("next" in lower_q or "upcoming" in lower_q) and any(w in lower_q for w in ["lab", "laboratory", "practical"])
            if is_next_lab_q:
                return get_next_class_tool(user_id, db, is_lab=True)

            # 7. Query: "When is my next Java class?" / "next <subject> class"
            is_next_subject_q = ("next" in lower_q or "upcoming" in lower_q) and target_subject
            if is_next_subject_q:
                return get_next_class_tool(user_id, db, subject=target_subject)

            # 8. Query: "Which faculty teaches DBMS?" / "Who teaches DBMS?"
            is_faculty_q = followup_type == "faculty" or any(w in lower_q for w in ["who teaches", "who is the faculty", "who is the instructor", "who is the teacher", "who teaches it", "taught by", "instructor for", "which faculty", "which teacher"])
            if is_faculty_q:
                subj_kw = target_subject or re.sub(r'\b(?:who|teaches|is|the|faculty|for|instructor|teacher|which|it|class|subject)\b', '', lower_q).strip()
                matching_faculty = [c for c in all_classes if subj_kw.lower() in c["course"].lower() or subj_kw.lower() in c["code"].lower()] if subj_kw else all_classes
                if matching_faculty:
                    c = matching_faculty[0]
                    return {
                        "count": len(matching_faculty),
                        "classes": matching_faculty,
                        "customMessage": f"**{c['course']}** ({c['code']}) is taught by **{c['instructor']}** (scheduled on {c['day']} from {c['time']} in room {c['room']})."
                    }
                else:
                    return {
                        "count": 0,
                        "classes": [],
                        "customMessage": f"I could not find a {subj_kw or 'matching'} class in your timetable."
                    }

            # 9. Query: "Which room is it in?" (Followup)
            is_room_q = followup_type == "room" or any(w in lower_q for w in ["which room", "what room", "where is my", "where is the", "where is it", "room number"])
            if is_room_q and target_subject:
                matching_room = [c for c in all_classes if target_subject.lower() in c["course"].lower() or target_subject.lower() in c["code"].lower()]
                if matching_room:
                    c = matching_room[0]
                    return {
                        "count": len(matching_room),
                        "classes": matching_room,
                        "customMessage": f"**{c['course']}** ({c['code']}) is held in **{c['room']}** on {c['day']} from {c['time']}."
                    }

            # 10. Query: "Free periods on Wednesday" / "Do I have any free periods on Wednesday?"
            is_free_period_q = any(w in lower_q for w in ["free period", "free periods", "free slot", "free slots", "free time"])
            if is_free_period_q and not (time_start and time_end):
                day_for_free = target_day or user_curr_day
                day_classes = [c for c in all_classes if c["day"].lower() == day_for_free.lower()]
                if not day_classes:
                    return {
                        "count": 0,
                        "classes": [],
                        "targetDay": day_for_free,
                        "customMessage": f"You have no scheduled classes on **{day_for_free}**. Your entire day is free!"
                    }

                day_sorted = sorted(day_classes, key=lambda x: parse_time_str_to_minutes(x["startTime"]) or 0)
                gaps = []
                for i in range(len(day_sorted) - 1):
                    end_prev = parse_time_str_to_minutes(day_sorted[i]["endTime"])
                    start_next = parse_time_str_to_minutes(day_sorted[i+1]["startTime"])
                    if end_prev is not None and start_next is not None and start_next > end_prev:
                        gap_mins = start_next - end_prev
                        if gap_mins >= 15:
                            gaps.append({
                                "start": day_sorted[i]["endTime"],
                                "end": day_sorted[i+1]["startTime"],
                                "duration": gap_mins,
                                "before": day_sorted[i]["course"],
                                "after": day_sorted[i+1]["course"]
                            })

                c_times = ", ".join([f"{c['course']} ({c['time']})" for c in day_sorted])
                if gaps:
                    gap_lines = [f"• **{g['start']} to {g['end']}** ({g['duration']} mins, between {g['before']} and {g['after']})" for g in gaps]
                    custom_msg = (
                        f"On **{day_for_free}**, you have {len(day_sorted)} classes: {c_times}.\n\n"
                        f"You have the following free periods between classes:\n" + "\n".join(gap_lines) +
                        f"\n\nOutside of scheduled class hours (before {day_sorted[0]['startTime']} and after {day_sorted[-1]['endTime']}), your time is also free."
                    )
                else:
                    custom_msg = (
                        f"On **{day_for_free}**, you have continuous classes from {day_sorted[0]['startTime']} to {day_sorted[-1]['endTime']} ({c_times}) with no free periods between them. Outside of these hours, your time is free."
                    )
                return {
                    "count": len(day_sorted),
                    "classes": day_sorted,
                    "targetDay": day_for_free,
                    "customMessage": custom_msg
                }

            # 11. Time Window Query (e.g. between 10 AM and 1 PM)
            interval_m = re.search(r'between\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:and|to|-)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)', lower_q, re.IGNORECASE)
            if interval_m and not time_start and not time_end:
                time_start = interval_m.group(1).strip()
                time_end = interval_m.group(2).strip()

            is_avail_q = check_availability or any(w in lower_q for w in ["free", "available", "conflict", "overlap", "busy"])
            if time_start and time_end:
                return get_timetable_between_times_tool(user_id, db, day=target_day or user_curr_day, start_time=time_start, end_time=time_end)

            # 12. Specific Day Schedule Query
            if target_day and not target_subject:
                return get_timetable_for_day_tool(user_id, db, day=target_day)

            # 13. Specific Subject Query (e.g. "When is Java?")
            if target_subject:
                subj_classes = [c for c in all_classes if target_subject.lower() in c["course"].lower() or target_subject.lower() in c["code"].lower()]
                if target_day:
                    subj_classes = [c for c in subj_classes if c["day"].lower() == target_day.lower()]
                subj_sorted = sorted(subj_classes, key=lambda x: parse_time_str_to_minutes(x["startTime"]) or 0)
                if subj_sorted:
                    lines = [format_period_line(c) for c in subj_sorted]
                    custom_msg = f"Here is the timetable for **{target_subject}**:\n\n" + "\n".join(lines)
                else:
                    custom_msg = f"You do not have any {target_subject} classes scheduled in your timetable{f' on {target_day}' if target_day else ''}."
                return {
                    "count": len(subj_sorted),
                    "classes": subj_sorted,
                    "targetSubject": target_subject,
                    "customMessage": custom_msg
                }

            # 14. Fallback Default: return sorted classes with standard message
            day_sorted = sorted(all_classes, key=lambda x: parse_time_str_to_minutes(x["startTime"]) or 0)
            lines = [format_period_line(c) for c in day_sorted[:10]]
            return {
                "count": len(all_classes),
                "classes": all_classes,
                "customMessage": "According to your academic timetable:\n\n" + "\n".join(lines)
            }

        # 2. Local RAG Knowledge
        @self.register("rag_knowledge_lookup", "Search through uploaded personal documents, syllabi, and notes.")
        async def rag_tool(user_id: str, db: Session, query: str, top_k: int = 6, explicit_doc_id: Optional[str] = None) -> Dict[str, Any]:
            return await retrieve_knowledge(query, user_id, db, top_k=top_k, explicit_doc_id=explicit_doc_id)

        # 2b. Document Inventory & Metadata Discovery
        @self.register("get_uploaded_documents", "Retrieve and inspect user's uploaded documents, distinguishing syllabi, timetables, and academic calendars.")
        @self.register("document_inventory", "Query and discover user's uploaded documents metadata, status, count, and categories.")
        async def doc_inventory_tool(
            user_id: str,
            db: Session,
            query: str = "",
            category: Optional[str] = None,
            document_type: Optional[str] = None,
            status: Optional[str] = None
        ) -> Dict[str, Any]:
            q = db.query(Document).filter(Document.user_id == user_id)
            if document_type:
                q = q.filter(Document.document_type == document_type.upper().strip())
            elif category:
                q = q.filter(Document.category == category)
            if status:
                q = q.filter(Document.status == status)
            docs = q.order_by(Document.created_at.desc()).all()

            # Filter by topic/keyword if query is specific
            matched = docs
            kw = query.lower().strip()
            # Clean common filler words
            clean_kw = re.sub(r'\b(?:what|which|list|show|all|my|uploaded|documents|files|pdfs|how|many|do|i|have|any|stored|about|related|to)\b', '', kw).strip()
            if clean_kw and len(clean_kw) >= 2:
                filtered = []
                for d in docs:
                    fn = d.filename.lower()
                    cat = (d.category or "").lower()
                    dtype = (d.document_type or "").lower()
                    if clean_kw in fn or clean_kw in cat or clean_kw in dtype or any(part in fn for part in clean_kw.split() if len(part) >= 3):
                        filtered.append(d)
                # If specific keywords matched documents, use that subset
                if filtered:
                    matched = filtered
                else:
                    # Specific query asked for topic not present
                    matched = []

            return {
                "totalCount": db.query(Document).filter(Document.user_id == user_id).count(),
                "matchingCount": len(matched),
                "queriedKeyword": clean_kw or None,
                "documents": [
                    {
                        "id": d.id,
                        "filename": d.filename,
                        "fileSize": d.file_size,
                        "mimeType": d.mime_type,
                        "category": d.category,
                        "documentType": d.document_type or "NOTES",
                        "status": d.status,
                        "processingStatus": d.processing_status or "COMPLETED",
                        "chunkCount": d.chunk_count,
                        "pageCount": d.page_count,
                        "uploadedAt": d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else None,
                        "errorMessage": d.error_message
                    }
                    for d in matched
                ]
            }

        # 3. Real Google Calendar Events Retrieval
        @self.register("calendar_events_retrieval", "Retrieve scheduled Google Calendar events and examine open slots.")
        async def calendar_tool(user_id: str, db: Session, time_min: str = "", time_max: str = "") -> Dict[str, Any]:
            if not is_capability_enabled(user_id, "calendar", "read_events", db):
                return {
                    "status": "capability_disabled",
                    "capability": "read_events",
                    "message": "The 'Read Calendar Events' capability is disabled in your Aurelia Settings. Please enable it under Settings > Integrations to view your calendar schedule.",
                    "events": [],
                    "count": 0,
                    "isLive": False
                }
            try:
                res = await google_calendar_service.list_events(
                    user_id=user_id,
                    db=db,
                    time_min=time_min or None,
                    time_max=time_max or None
                )
                events = res.get("events", [])
                return {"status": "success", "events": events, "count": len(events), "isLive": True}
            except Exception as e:
                return {
                    "status": "not_connected",
                    "message": str(e),
                    "events": [],
                    "count": 0,
                    "isLive": False
                }

        # 4. Real Google Calendar Conflict Check & Event Proposal
        @self.register("calendar_propose_event", "Propose a study block or calendar event for explicit user approval.")
        async def propose_event_tool(
            user_id: str,
            db: Session,
            title: str,
            start_time: str,
            duration_mins: int = 60,
            location: str = "",
            is_all_day: bool = False
        ) -> Dict[str, Any]:
            if not is_capability_enabled(user_id, "calendar", "create_events", db):
                return {
                    "status": "capability_disabled",
                    "capability": "create_events",
                    "message": "The 'Create Events & Study Sessions' capability is disabled in your Aurelia Settings. Please enable it under Settings > Integrations to schedule calendar events.",
                    "requiresConfirmation": False,
                    "previewEvent": None,
                    "conflicts": [],
                    "hasConflict": False,
                    "isLive": False
                }
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                if is_all_day:
                    # For all-day events, end time is the next day; time component is ignored
                    end_dt = start_dt + timedelta(days=1)
                else:
                    end_dt = start_dt + timedelta(minutes=duration_mins)
                res = await google_calendar_service.prepare_event_proposal(
                    user_id=user_id,
                    db=db,
                    title=title,
                    start_time=start_dt.isoformat(),
                    end_time=end_dt.isoformat(),
                    location=location or None,
                    is_all_day=is_all_day
                )
                return res
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Could not propose calendar event: {str(e)}",
                    "requiresConfirmation": False,
                    "previewEvent": None,
                    "conflicts": [],
                    "hasConflict": False,
                    "isLive": False
                }

        # 5. Calendar Event Deletion
        @self.register("calendar_delete_event", "Delete a scheduled event from Google Calendar.")
        async def calendar_delete_tool(user_id: str, db: Session, event_id: str) -> Dict[str, Any]:
            if not is_capability_enabled(user_id, "calendar", "delete_events", db):
                return {
                    "status": "capability_disabled",
                    "capability": "delete_events",
                    "message": "The 'Delete & Cancel Events' capability is disabled in your Aurelia Settings. Please enable it under Settings > Integrations to cancel calendar events."
                }
            try:
                return await google_calendar_service.delete_event(user_id=user_id, db=db, event_id=event_id)
            except Exception as e:
                return {"status": "error", "message": str(e)}

        # 6. Calendar Event Update / Reschedule
        @self.register("calendar_update_event", "Update or reschedule an existing event in Google Calendar.")
        async def calendar_update_tool(
            user_id: str,
            db: Session,
            event_id: str,
            title: Optional[str] = None,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None
        ) -> Dict[str, Any]:
            if not is_capability_enabled(user_id, "calendar", "edit_events", db):
                return {
                    "status": "capability_disabled",
                    "capability": "edit_events",
                    "message": "The 'Edit & Reschedule Events' capability is disabled in your Aurelia Settings. Please enable it under Settings > Integrations."
                }
            try:
                return await google_calendar_service.update_event(
                    user_id=user_id,
                    db=db,
                    event_id=event_id,
                    title=title,
                    start_time=start_time,
                    end_time=end_time
                )
            except Exception as e:
                return {"status": "error", "message": str(e)}

        # 7. Real Gmail Priority Message Search
        @self.register("gmail_priority_messages", "Search priority emails from authorized Gmail stream.")
        async def gmail_tool(user_id: str, db: Session, query: str = "", filter_type: str = "today") -> Dict[str, Any]:
            if not is_capability_enabled(user_id, "gmail", "read_messages", db):
                return {
                    "status": "capability_disabled",
                    "capability": "read_messages",
                    "message": "The 'Search & Read Emails' capability is disabled in your Aurelia Settings. Please enable it under Settings > Integrations to search or read emails.",
                    "messages": [],
                    "count": 0,
                    "isLive": False
                }
            try:
                res = await google_gmail_service.list_messages(
                    user_id=user_id,
                    db=db,
                    query=query or None,
                    max_results=10
                )
                messages = res.get("messages", [])
                return {"status": "success", "messages": messages, "count": len(messages), "isLive": True}
            except Exception as e:
                return {
                    "status": "not_connected",
                    "message": str(e),
                    "messages": [],
                    "count": 0,
                    "isLive": False
                }

        # 8. Real Gmail Draft Creation
        @self.register("gmail_create_draft", "Create an email draft in the user's Gmail account.")
        async def draft_tool(user_id: str, db: Session, to: str, subject: str, body: str) -> Dict[str, Any]:
            if not is_capability_enabled(user_id, "gmail", "create_drafts", db):
                return {
                    "status": "capability_disabled",
                    "capability": "create_drafts",
                    "message": "The 'Compose Email Drafts' capability is disabled in your Aurelia Settings. Please enable it under Settings > Integrations to create email drafts.",
                    "isLive": False
                }
            try:
                res = await google_gmail_service.create_draft(user_id=user_id, db=db, to=to, subject=subject, body=body)
                return {"status": "success", "draft": res, "isLive": True}
            except Exception as e:
                return {"status": "not_connected", "message": str(e), "isLive": False}

        # 9. Real Gmail Send Message (Requires explicit user confirmation)
        @self.register("gmail_send_message", "Send an email after explicit user approval.")
        async def send_email_tool(user_id: str, db: Session, confirmation_token: str) -> Dict[str, Any]:
            if not is_capability_enabled(user_id, "gmail", "send_messages", db):
                return {
                    "status": "capability_disabled",
                    "capability": "send_messages",
                    "message": "The 'Send Approved Emails' capability is disabled in your Aurelia Settings. Please enable it under Settings > Integrations to allow sending emails.",
                    "isLive": False
                }
            try:
                res = await google_gmail_service.send_email_confirmed(user_id=user_id, db=db, confirmation_token=confirmation_token)
                return {"status": "success", "sendResult": res, "isLive": True}
            except Exception as e:
                return {"status": "error", "message": str(e), "isLive": False}

        # 10. Real Google Drive File Search
        @self.register("drive_search_files", "Search project proposals, documents, and notes in authorized Google Drive.")
        async def drive_search_tool(user_id: str, db: Session, query: str = "") -> Dict[str, Any]:
            if not is_capability_enabled(user_id, "drive", "search_files", db):
                return {
                    "status": "capability_disabled",
                    "capability": "search_files",
                    "message": "The 'Search Drive Files' capability is disabled in your Aurelia Settings. Please enable it under Settings > Integrations to search Google Drive.",
                    "files": [],
                    "count": 0,
                    "isLive": False
                }
            try:
                res = await google_drive_service.search_files(user_id=user_id, db=db, query=query or None, page_size=10)
                files = res.get("files", [])
                return {"status": "success", "files": files, "count": len(files), "isLive": True}
            except Exception as e:
                return {
                    "status": "not_connected",
                    "message": str(e),
                    "files": [],
                    "count": 0,
                    "isLive": False
                }

        # 11. Real Google Drive Read File
        @self.register("drive_read_file", "Read text content or Google Docs export from Google Drive.")
        async def drive_read_tool(user_id: str, db: Session, file_id: str) -> Dict[str, Any]:
            if not is_capability_enabled(user_id, "drive", "read_file_content", db):
                return {
                    "status": "capability_disabled",
                    "capability": "read_file_content",
                    "message": "The 'Read & Ground on Documents' capability is disabled in your Aurelia Settings. Please enable it under Settings > Integrations to read Drive files.",
                    "isSupported": False
                }
            return await google_drive_service.read_file_content(user_id=user_id, db=db, file_id=file_id)

        # 12. Real Live Web Search
        @self.register("web_search_intelligence", "Query live web intelligence using configured Tavily search provider.")
        async def web_tool(query: str) -> Dict[str, Any]:
            return await web_search_service.search(query=query)

        # 13. Real Weather Telemetry (Open-Meteo)
        @self.register("weather_lookup", "Retrieve real-time meteorological conditions and temperature for a city.")
        async def weather_tool(city: str = "Bengaluru") -> Dict[str, Any]:
            return await weather_service.get_weather(city=city)

        # 14. Plan Management: Create Plan
        @self.register("plan_create", "Create a new study plan with milestones and tasks.")
        def plan_create_tool(
            user_id: str,
            db: Session,
            title: str,
            period: str = "Current Sprint",
            goals: Optional[List[str]] = None,
            tasks: Optional[List[Dict[str, Any]]] = None,
            suggested_study_blocks: Optional[List[Dict[str, Any]]] = None,
            subject: Optional[str] = None,
            learning_goal: Optional[str] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None,
            duration_days: Optional[int] = None,
            daily_hours_target: Optional[float] = None,
            preferred_study_days: Optional[List[str]] = None
        ) -> Dict[str, Any]:
            plan = Plan(
                user_id=user_id,
                title=title,
                period=period,
                subject=subject,
                learning_goal=learning_goal,
                start_date=start_date,
                end_date=end_date,
                duration_days=duration_days,
                daily_hours_target=daily_hours_target or 2.0,
                preferred_study_days=preferred_study_days or [],
                generation_status="complete",
                goals=goals or [],
                suggested_study_blocks=suggested_study_blocks or []
            )
            db.add(plan)
            db.commit()
            db.refresh(plan)

            created_tasks = []
            if tasks:
                for idx, t in enumerate(tasks):
                    pt = PlanTask(
                        plan_id=plan.id,
                        title=t.get("title", "Task"),
                        duration_minutes=int(t.get("duration_minutes", t.get("durationMinutes", 45))),
                        priority=t.get("priority", "high"),
                        completed=bool(t.get("completed", False)),
                        scheduled_date=t.get("scheduled_date", t.get("scheduledDate")),
                        start_time=t.get("start_time", t.get("startTime")),
                        end_time=t.get("end_time", t.get("endTime")),
                        timezone=t.get("timezone"),
                        google_calendar_event_id=t.get("google_calendar_event_id", t.get("googleCalendarEventId")),
                        month_number=t.get("month_number", t.get("monthNumber")),
                        week_number=t.get("week_number", t.get("weekNumber")),
                        day_number=t.get("day_number", t.get("dayNumber")),
                        task_order=t.get("task_order", t.get("taskOrder", idx + 1)),
                        task_type=t.get("task_type", t.get("taskType", "daily")),
                        day_label=t.get("day_label", t.get("dayLabel")),
                        week_label=t.get("week_label", t.get("weekLabel")),
                        month_label=t.get("month_label", t.get("monthLabel")),
                        milestone_group=t.get("milestone_group", t.get("milestoneGroup"))
                    )
                    db.add(pt)
                    created_tasks.append(pt)
                db.commit()

            return {
                "status": "success",
                "plan": {
                    "id": plan.id,
                    "title": plan.title,
                    "period": plan.period,
                    "subject": plan.subject,
                    "learningGoal": plan.learning_goal,
                    "startDate": plan.start_date,
                    "endDate": plan.end_date,
                    "durationDays": plan.duration_days,
                    "dailyHoursTarget": plan.daily_hours_target,
                    "goals": plan.goals,
                    "tasks": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "durationMinutes": t.duration_minutes,
                            "priority": t.priority,
                            "completed": t.completed,
                            "scheduledDate": t.scheduled_date,
                            "startTime": t.start_time,
                            "endTime": t.end_time,
                            "timezone": t.timezone,
                            "googleCalendarEventId": t.google_calendar_event_id,
                            "monthNumber": t.month_number,
                            "weekNumber": t.week_number,
                            "dayNumber": t.day_number,
                            "taskOrder": t.task_order,
                            "taskType": t.task_type,
                            "dayLabel": t.day_label,
                            "weekLabel": t.week_label,
                            "monthLabel": t.month_label,
                            "milestoneGroup": t.milestone_group
                        }
                        for t in created_tasks
                    ]
                }
            }

        # 15. Plan Management: List Plans
        @self.register("plan_list", "List the user's saved study plans.")
        def plan_list_tool(user_id: str, db: Session) -> Dict[str, Any]:
            plans = db.query(Plan).filter(Plan.user_id == user_id).order_by(Plan.created_at.desc()).all()
            res = []
            for p in plans:
                t_count = db.query(PlanTask).filter(PlanTask.plan_id == p.id).count()
                completed_count = db.query(PlanTask).filter(PlanTask.plan_id == p.id, PlanTask.completed == True).count()
                res.append({
                    "id": p.id,
                    "title": p.title,
                    "period": p.period,
                    "taskCount": t_count,
                    "completedTasks": completed_count,
                    "goals": p.goals or []
                })
            return {"status": "success", "count": len(res), "plans": res}

        # 16. Plan Management: Get Plan Details
        @self.register("plan_get", "Get a study plan and its tasks.")
        def plan_get_tool(user_id: str, db: Session, plan_id: Optional[str] = None) -> Dict[str, Any]:
            query = db.query(Plan).filter(Plan.user_id == user_id)
            if plan_id:
                plan = query.filter(Plan.id == plan_id).first()
            else:
                plan = query.order_by(Plan.updated_at.desc()).first()

            if not plan:
                return {"status": "not_found", "message": "No study plan found for user."}

            tasks = db.query(PlanTask).filter(PlanTask.plan_id == plan.id).all()
            return {
                "status": "success",
                "plan": {
                    "id": plan.id,
                    "title": plan.title,
                    "period": plan.period,
                    "goals": plan.goals or [],
                    "suggestedStudyBlocks": plan.suggested_study_blocks or [],
                    "tasks": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "durationMinutes": t.duration_minutes,
                            "priority": t.priority,
                            "completed": t.completed,
                            "scheduledDate": t.scheduled_date,
                            "startTime": t.start_time,
                            "endTime": t.end_time,
                            "timezone": t.timezone,
                            "googleCalendarEventId": t.google_calendar_event_id
                        }
                        for t in tasks
                    ]
                }
            }

        # 17. Plan Management: Update Plan
        @self.register("plan_update", "Update a study plan's details, goals, or daily hours.")
        def plan_update_tool(
            user_id: str,
            db: Session,
            plan_id: Optional[str] = None,
            title: Optional[str] = None,
            period: Optional[str] = None,
            goals: Optional[List[str]] = None,
            daily_hours: Optional[float] = None
        ) -> Dict[str, Any]:
            query = db.query(Plan).filter(Plan.user_id == user_id)
            if plan_id:
                plan = query.filter(Plan.id == plan_id).first()
            else:
                plan = query.order_by(Plan.updated_at.desc()).first()

            if not plan:
                return {"status": "not_found", "message": "No plan found to update."}

            if title:
                plan.title = title
            if period:
                plan.period = period
            if goals is not None:
                plan.goals = goals

            # If daily hours changed (e.g. Example B: "I can only study two hours daily now. Update my plan.")
            updated_task_count = 0
            if daily_hours is not None:
                target_mins = int(daily_hours * 60)
                # Update duration of incomplete tasks to fit new daily allocation
                incomplete_tasks = db.query(PlanTask).filter(
                    PlanTask.plan_id == plan.id,
                    PlanTask.completed == False
                ).all()
                for t in incomplete_tasks:
                    t.duration_minutes = target_mins
                    updated_task_count += 1

            db.commit()
            db.refresh(plan)

            tasks = db.query(PlanTask).filter(PlanTask.plan_id == plan.id).all()
            return {
                "status": "success",
                "planId": plan.id,
                "title": plan.title,
                "period": plan.period,
                "goals": plan.goals,
                "updatedTaskCount": updated_task_count,
                "totalTasks": len(tasks)
            }

        # 18. Plan Management: Add Task
        @self.register("plan_add_task", "Add a new task to a study plan.")
        def plan_add_task_tool(
            user_id: str,
            db: Session,
            plan_id: Optional[str] = None,
            title: str = "New Task",
            duration_minutes: int = 45,
            priority: str = "high",
            scheduled_date: Optional[str] = None,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None,
            timezone: Optional[str] = None
        ) -> Dict[str, Any]:
            query = db.query(Plan).filter(Plan.user_id == user_id)
            if plan_id:
                plan = query.filter(Plan.id == plan_id).first()
            else:
                plan = query.order_by(Plan.updated_at.desc()).first()

            if not plan:
                return {"status": "not_found", "message": "No active study plan to add task to."}

            pt = PlanTask(
                plan_id=plan.id,
                title=title,
                duration_minutes=duration_minutes,
                priority=priority,
                completed=False,
                scheduled_date=scheduled_date,
                start_time=start_time,
                end_time=end_time,
                timezone=timezone
            )
            db.add(pt)
            db.commit()
            db.refresh(pt)
            return {
                "status": "success",
                "planId": plan.id,
                "taskId": pt.id,
                "title": pt.title,
                "durationMinutes": pt.duration_minutes
            }

        # 19. Plan Management: Update / Complete / Reschedule Task
        @self.register("plan_update_task", "Update an existing task in a study plan (complete, reschedule, rename).")
        async def plan_update_task_tool(
            user_id: str,
            db: Session,
            task_id: Optional[str] = None,
            task_title_search: Optional[str] = None,
            plan_id: Optional[str] = None,
            completed: Optional[bool] = None,
            title: Optional[str] = None,
            scheduled_date: Optional[str] = None,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None,
            duration_minutes: Optional[int] = None
        ) -> Dict[str, Any]:
            # Locate task
            user_plans = db.query(Plan).filter(Plan.user_id == user_id).all()
            if not user_plans:
                return {"status": "not_found", "message": "No study plans found."}

            user_plan_ids = [p.id for p in user_plans]
            task = None
            if task_id:
                task = db.query(PlanTask).filter(PlanTask.id == task_id, PlanTask.plan_id.in_(user_plan_ids)).first()
            elif task_title_search:
                term = task_title_search.strip().lower()
                candidates = db.query(PlanTask).filter(
                    PlanTask.plan_id.in_(user_plan_ids),
                    PlanTask.title.ilike(f"%{term}%")
                ).all()
                if len(candidates) > 1 and completed is True:
                    # Prefer uncompleted task
                    uncompleted = [c for c in candidates if not c.completed]
                    task = uncompleted[0] if uncompleted else candidates[0]
                elif candidates:
                    task = candidates[0]

            if not task:
                # If neither id nor search term matched, check most recent uncompleted task
                task = db.query(PlanTask).filter(
                    PlanTask.plan_id.in_(user_plan_ids),
                    PlanTask.completed == False
                ).first()

            if not task:
                return {"status": "not_found", "message": "Could not identify the intended task in your study plan."}

            if completed is not None:
                task.completed = completed
            if title:
                task.title = title
            if scheduled_date is not None:
                task.scheduled_date = scheduled_date
            if start_time is not None:
                task.start_time = start_time
            if end_time is not None:
                task.end_time = end_time
            if duration_minutes is not None:
                task.duration_minutes = duration_minutes

            # Sync with linked Google Calendar event if one exists
            calendar_synced = False
            if task.google_calendar_event_id and (start_time or end_time or title):
                try:
                    cal_res = await google_calendar_service.update_event(
                        user_id=user_id,
                        db=db,
                        event_id=task.google_calendar_event_id,
                        title=task.title,
                        start_time=task.start_time,
                        end_time=task.end_time
                    )
                    if cal_res.get("status") == "success":
                        calendar_synced = True
                except Exception:
                    pass

            db.commit()
            db.refresh(task)

            return {
                "status": "success",
                "taskId": task.id,
                "title": task.title,
                "completed": task.completed,
                "scheduledDate": task.scheduled_date,
                "startTime": task.start_time,
                "endTime": task.end_time,
                "durationMinutes": task.duration_minutes,
                "calendarSynced": calendar_synced
            }

        # 20. Plan Management: Delete Task
        @self.register("plan_delete_task", "Delete a task from a study plan.")
        def plan_delete_task_tool(
            user_id: str,
            db: Session,
            task_id: Optional[str] = None,
            task_title_search: Optional[str] = None
        ) -> Dict[str, Any]:
            user_plan_ids = [p.id for p in db.query(Plan.id).filter(Plan.user_id == user_id).all()]
            task = None
            if task_id:
                task = db.query(PlanTask).filter(PlanTask.id == task_id, PlanTask.plan_id.in_(user_plan_ids)).first()
            elif task_title_search:
                task = db.query(PlanTask).filter(
                    PlanTask.plan_id.in_(user_plan_ids),
                    PlanTask.title.ilike(f"%{task_title_search.strip()}%")
                ).first()

            if not task:
                return {"status": "not_found", "message": "Task not found."}

            db.delete(task)
            db.commit()
            return {"status": "success", "deletedTaskId": task.id, "title": task.title}

        # 21. Plan Management: Delete Plan
        @self.register("plan_delete", "Permanently delete a study plan.")
        def plan_delete_tool(user_id: str, db: Session, plan_id: str) -> Dict[str, Any]:
            plan = db.query(Plan).filter(Plan.id == plan_id, Plan.user_id == user_id).first()
            if not plan:
                return {"status": "not_found", "message": "Plan not found."}

            db.query(PlanTask).filter(PlanTask.plan_id == plan.id).delete()
            db.delete(plan)
            db.commit()
            return {"status": "success", "deletedPlanId": plan_id, "title": plan.title}


    async def execute(self, tool_name: str, **kwargs) -> Any:
        if tool_name not in self._tools:
            raise ValueError(f"Tool {tool_name} is not registered in Aurelia agent registry.")
        func = self._tools[tool_name]
        import inspect
        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)

tool_registry = ToolRegistry()
