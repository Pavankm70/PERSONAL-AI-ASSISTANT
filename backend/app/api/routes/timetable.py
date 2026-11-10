import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, Timetable, TimetablePeriod
from app.api.routes.auth import get_current_user
from app.schemas import (
    TimetableCreateSchema,
    TimetableUpdateSchema,
    TimetableResponseSchema,
    PeriodCreateSchema,
    PeriodUpdateSchema,
    PeriodResponseSchema
)

router = APIRouter(prefix="/timetable", tags=["Manual Timetable"])

DAY_ORDER = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7
}

DAY_MAP = {
    "mon": "Monday", "monday": "Monday",
    "tue": "Tuesday", "tues": "Tuesday", "tuesday": "Tuesday",
    "wed": "Wednesday", "wednesday": "Wednesday",
    "thu": "Thursday", "thur": "Thursday", "thurs": "Thursday", "thursday": "Thursday",
    "fri": "Friday", "friday": "Friday",
    "sat": "Saturday", "saturday": "Saturday",
    "sun": "Sunday", "sunday": "Sunday"
}

def parse_time_to_minutes(time_str: str) -> Optional[int]:
    """Parses 12-hour or 24-hour time string into minutes since midnight."""
    if not time_str:
        return None
    cleaned = time_str.strip()
    # 12-hour AM/PM format (e.g. "09:00 AM", "9:30 pm")
    m12 = re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)$', cleaned)
    if m12:
        h = int(m12.group(1))
        m = int(m12.group(2))
        p = m12.group(3).upper()
        if h == 12:
            h = 0 if p == "AM" else 12
        elif p == "PM":
            h += 12
        return h * 60 + m

    # 24-hour format (e.g. "09:00", "14:30")
    m24 = re.match(r'^(\d{1,2}):(\d{2})$', cleaned)
    if m24:
        h = int(m24.group(1))
        m = int(m24.group(2))
        return h * 60 + m

    return None

def normalize_day(day_str: str) -> str:
    cleaned = day_str.strip().lower()
    return DAY_MAP.get(cleaned, day_str.strip().capitalize())

def validate_period_times(start_time: str, end_time: str):
    start_m = parse_time_to_minutes(start_time)
    end_m = parse_time_to_minutes(end_time)
    if start_m is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid start time format: '{start_time}'. Please use '09:00 AM' or '09:00'."
        )
    if end_m is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid end time format: '{end_time}'. Please use '10:00 AM' or '10:00'."
        )
    if end_m <= start_m:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"End time ('{end_time}') must be later than start time ('{start_time}')."
        )

def detect_period_conflicts(periods: List[Any]) -> List[str]:
    """Detects overlapping periods on the same day and returns warning messages."""
    warnings = []
    day_groups: Dict[str, List[Any]] = {}
    for p in periods:
        d = normalize_day(getattr(p, "day_of_week", "") or "")
        day_groups.setdefault(d, []).append(p)

    for day, p_list in day_groups.items():
        for i in range(len(p_list)):
            for j in range(i + 1, len(p_list)):
                p1, p2 = p_list[i], p_list[j]
                s1 = parse_time_to_minutes(getattr(p1, "start_time", ""))
                e1 = parse_time_to_minutes(getattr(p1, "end_time", ""))
                s2 = parse_time_to_minutes(getattr(p2, "start_time", ""))
                e2 = parse_time_to_minutes(getattr(p2, "end_time", ""))
                if s1 is not None and e1 is not None and s2 is not None and e2 is not None:
                    if max(s1, s2) < min(e1, e2):
                        subj1 = getattr(p1, "subject_name", "Period 1")
                        subj2 = getattr(p2, "subject_name", "Period 2")
                        warnings.append(
                            f"Overlapping periods on {day}: '{subj1}' ({getattr(p1, 'start_time', '')}-{getattr(p1, 'end_time', '')}) conflicts with '{subj2}' ({getattr(p2, 'start_time', '')}-{getattr(p2, 'end_time', '')})."
                        )
    return warnings

def ensure_period_numbers(periods: List[TimetablePeriod]):
    """Assigns sequential 1-based period numbers chronologically for each day if not set."""
    day_groups: Dict[str, List[TimetablePeriod]] = {}
    for p in periods:
        day_groups.setdefault(p.day_of_week, []).append(p)
    for day, p_list in day_groups.items():
        p_list.sort(key=lambda x: parse_time_to_minutes(x.start_time) or 0)
        for idx, p in enumerate(p_list):
            if p.period_number is None or p.period_number <= 0:
                p.period_number = idx + 1


# ---------------------------------------------------------------------------
# Timetable CRUD Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=Optional[TimetableResponseSchema])
def get_user_timetable(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns the authenticated user's current timetable with all periods.
    Returns None if no timetable has been created yet.
    """
    tt = db.query(Timetable).filter(Timetable.user_id == user.id).order_by(Timetable.updated_at.desc()).first()
    if not tt:
        return None

    # Sort periods by day order, then start time
    periods = db.query(TimetablePeriod).filter(TimetablePeriod.timetable_id == tt.id).all()
    periods.sort(key=lambda p: (
        DAY_ORDER.get(p.day_of_week.lower(), 99),
        parse_time_to_minutes(p.start_time) or 0
    ))
    ensure_period_numbers(periods)
    tt.periods = periods
    return tt


@router.post("", response_model=TimetableResponseSchema, status_code=status.HTTP_201_CREATED)
def create_timetable(
    payload: TimetableCreateSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Creates a new manual timetable for the authenticated user along with its periods.
    """
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Timetable name is required.")

    # Validate all period times
    for p in payload.periods:
        validate_period_times(p.start_time, p.end_time)

    # Detect conflicts for user notice
    detect_period_conflicts(payload.periods)

    # Create Timetable
    tt = Timetable(
        user_id=user.id,
        name=payload.name.strip(),
        academic_year=payload.academic_year.strip() if payload.academic_year else None,
        semester=payload.semester.strip() if payload.semester else None,
        section=payload.section.strip() if payload.section else None
    )
    db.add(tt)
    db.flush()

    # Add periods
    for p in payload.periods:
        norm_day = normalize_day(p.day_of_week)
        period = TimetablePeriod(
            timetable_id=tt.id,
            user_id=user.id,
            day_of_week=norm_day,
            period_number=getattr(p, "period_number", None),
            subject_name=p.subject_name.strip(),
            subject_code=p.subject_code.strip() if p.subject_code else None,
            start_time=p.start_time.strip(),
            end_time=p.end_time.strip(),
            room=p.room.strip() if p.room else None,
            faculty=p.faculty.strip() if p.faculty else None,
            class_type=p.class_type.strip() if p.class_type else "Theory",
            notes=p.notes.strip() if p.notes else None
        )
        db.add(period)

    db.commit()
    db.refresh(tt)

    # Sort periods for return
    periods = db.query(TimetablePeriod).filter(TimetablePeriod.timetable_id == tt.id).all()
    periods.sort(key=lambda p: (
        DAY_ORDER.get(p.day_of_week.lower(), 99),
        parse_time_to_minutes(p.start_time) or 0
    ))
    ensure_period_numbers(periods)
    tt.periods = periods
    return tt


@router.get("/{timetable_id}", response_model=TimetableResponseSchema)
def get_timetable_by_id(
    timetable_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Fetches a specific timetable by ID ensuring authenticated user ownership.
    """
    tt = db.query(Timetable).filter(
        Timetable.id == timetable_id,
        Timetable.user_id == user.id
    ).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found.")

    periods = db.query(TimetablePeriod).filter(TimetablePeriod.timetable_id == tt.id).all()
    periods.sort(key=lambda p: (
        DAY_ORDER.get(p.day_of_week.lower(), 99),
        parse_time_to_minutes(p.start_time) or 0
    ))
    ensure_period_numbers(periods)
    tt.periods = periods
    return tt


@router.put("/{timetable_id}", response_model=TimetableResponseSchema)
def update_timetable(
    timetable_id: str,
    payload: TimetableUpdateSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates timetable metadata and optionally replaces all periods in a single transaction.
    """
    tt = db.query(Timetable).filter(
        Timetable.id == timetable_id,
        Timetable.user_id == user.id
    ).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found.")

    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(status_code=400, detail="Timetable name cannot be empty.")
        tt.name = payload.name.strip()
    if payload.academic_year is not None:
        tt.academic_year = payload.academic_year.strip() if payload.academic_year else None
    if payload.semester is not None:
        tt.semester = payload.semester.strip() if payload.semester else None
    if payload.section is not None:
        tt.section = payload.section.strip() if payload.section else None

    # If periods list is provided, validate and atomically replace
    if payload.periods is not None:
        for p in payload.periods:
            validate_period_times(p.start_time, p.end_time)

        # Remove old periods
        db.query(TimetablePeriod).filter(TimetablePeriod.timetable_id == tt.id).delete()

        # Insert updated periods
        for p in payload.periods:
            norm_day = normalize_day(p.day_of_week)
            period = TimetablePeriod(
                timetable_id=tt.id,
                user_id=user.id,
                day_of_week=norm_day,
                period_number=getattr(p, "period_number", None),
                subject_name=p.subject_name.strip(),
                subject_code=p.subject_code.strip() if p.subject_code else None,
                start_time=p.start_time.strip(),
                end_time=p.end_time.strip(),
                room=p.room.strip() if p.room else None,
                faculty=p.faculty.strip() if p.faculty else None,
                class_type=p.class_type.strip() if p.class_type else "Theory",
                notes=p.notes.strip() if p.notes else None
            )
            db.add(period)

    tt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tt)

    periods = db.query(TimetablePeriod).filter(TimetablePeriod.timetable_id == tt.id).all()
    periods.sort(key=lambda p: (
        DAY_ORDER.get(p.day_of_week.lower(), 99),
        parse_time_to_minutes(p.start_time) or 0
    ))
    ensure_period_numbers(periods)
    tt.periods = periods
    return tt


@router.delete("/{timetable_id}")
def delete_timetable(
    timetable_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deletes a timetable and cascade-deletes all its periods.
    Does not affect RAG documents or any unrelated user data.
    """
    tt = db.query(Timetable).filter(
        Timetable.id == timetable_id,
        Timetable.user_id == user.id
    ).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found.")

    db.delete(tt)
    db.commit()
    return {"success": True, "message": "Timetable deleted successfully.", "deletedId": timetable_id}


# ---------------------------------------------------------------------------
# Individual Period CRUD Endpoints
# ---------------------------------------------------------------------------

@router.post("/{timetable_id}/periods", response_model=PeriodResponseSchema, status_code=status.HTTP_201_CREATED)
def add_period_to_timetable(
    timetable_id: str,
    payload: PeriodCreateSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Adds a new period to an existing timetable with ownership check.
    """
    tt = db.query(Timetable).filter(
        Timetable.id == timetable_id,
        Timetable.user_id == user.id
    ).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found.")

    validate_period_times(payload.start_time, payload.end_time)
    norm_day = normalize_day(payload.day_of_week)

    period = TimetablePeriod(
        timetable_id=tt.id,
        user_id=user.id,
        day_of_week=norm_day,
        period_number=getattr(payload, "period_number", None),
        subject_name=payload.subject_name.strip(),
        subject_code=payload.subject_code.strip() if payload.subject_code else None,
        start_time=payload.start_time.strip(),
        end_time=payload.end_time.strip(),
        room=payload.room.strip() if payload.room else None,
        faculty=payload.faculty.strip() if payload.faculty else None,
        class_type=payload.class_type.strip() if payload.class_type else "Theory",
        notes=payload.notes.strip() if payload.notes else None
    )
    db.add(period)
    tt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(period)

    # Ensure period_number is populated for response
    if period.period_number is None:
        day_count = db.query(TimetablePeriod).filter(
            TimetablePeriod.timetable_id == tt.id,
            TimetablePeriod.day_of_week == norm_day
        ).count()
        period.period_number = day_count

    return period


@router.put("/{timetable_id}/periods/{period_id}", response_model=PeriodResponseSchema)
def update_period(
    timetable_id: str,
    period_id: str,
    payload: PeriodUpdateSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates an individual period with timing validation and ownership check.
    """
    tt = db.query(Timetable).filter(
        Timetable.id == timetable_id,
        Timetable.user_id == user.id
    ).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found.")

    period = db.query(TimetablePeriod).filter(
        TimetablePeriod.id == period_id,
        TimetablePeriod.timetable_id == tt.id,
        TimetablePeriod.user_id == user.id
    ).first()
    if not period:
        raise HTTPException(status_code=404, detail="Period not found.")

    new_start = payload.start_time if payload.start_time is not None else period.start_time
    new_end = payload.end_time if payload.end_time is not None else period.end_time
    validate_period_times(new_start, new_end)

    if payload.period_number is not None:
        period.period_number = payload.period_number
    if payload.day_of_week is not None:
        period.day_of_week = normalize_day(payload.day_of_week)
    if payload.subject_name is not None:
        if not payload.subject_name.strip():
            raise HTTPException(status_code=400, detail="Subject name cannot be empty.")
        period.subject_name = payload.subject_name.strip()
    if payload.subject_code is not None:
        period.subject_code = payload.subject_code.strip() if payload.subject_code else None
    if payload.start_time is not None:
        period.start_time = payload.start_time.strip()
    if payload.end_time is not None:
        period.end_time = payload.end_time.strip()
    if payload.room is not None:
        period.room = payload.room.strip() if payload.room else None
    if payload.faculty is not None:
        period.faculty = payload.faculty.strip() if payload.faculty else None
    if payload.class_type is not None:
        period.class_type = payload.class_type.strip() if payload.class_type else "Theory"
    if payload.notes is not None:
        period.notes = payload.notes.strip() if payload.notes else None

    period.updated_at = datetime.now(timezone.utc)
    tt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(period)
    return period


@router.delete("/{timetable_id}/periods/{period_id}")
def delete_period(
    timetable_id: str,
    period_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deletes an individual period from a timetable with ownership check.
    """
    tt = db.query(Timetable).filter(
        Timetable.id == timetable_id,
        Timetable.user_id == user.id
    ).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found.")

    period = db.query(TimetablePeriod).filter(
        TimetablePeriod.id == period_id,
        TimetablePeriod.timetable_id == tt.id,
        TimetablePeriod.user_id == user.id
    ).first()
    if not period:
        raise HTTPException(status_code=404, detail="Period not found.")

    db.delete(period)
    tt.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"success": True, "message": "Period deleted successfully.", "deletedPeriodId": period_id}

