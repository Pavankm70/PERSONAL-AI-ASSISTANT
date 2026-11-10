import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.services.google_oauth.oauth_service import get_valid_user_credentials

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary"

class GoogleCalendarService:
    """
    Real Google Calendar API operations service.
    Strictly tenant-isolated by user_id with human-in-the-loop confirmation before writes.
    """
    # Tokens expire after 15 minutes
    TOKEN_TTL_SECONDS = 900

    def __init__(self):
        # Tokens for pending event creation confirmation
        self._event_confirmations: Dict[str, Dict[str, Any]] = {}
        # Tracks already-consumed tokens to prevent duplicate execution
        self._completed_tokens: set = set()

    def _get_client_headers(self, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def _get_access_token_or_raise(self, user_id: str, db: Session) -> str:
        creds = await get_valid_user_credentials(user_id=user_id, provider="calendar", db=db)
        if not creds or not creds.get("access_token"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google Calendar is not connected or credentials have expired. Please connect Calendar in Integrations."
            )
        return creds["access_token"]

    async def list_events(
        self,
        user_id: str,
        db: Session,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 50,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Lists events from the primary calendar within the specified date range.
        """
        token = await self._get_access_token_or_raise(user_id, db)
        now = datetime.now(timezone.utc)
        if not time_min:
            time_min = (now - timedelta(days=60)).isoformat()
        if not time_max:
            time_max = (now + timedelta(days=120)).isoformat()

        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": min(max_results, 250)
        }
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{CALENDAR_API_BASE}/events",
                headers=self._get_client_headers(token),
                params=params
            )
            if res.status_code == 401 or res.status_code == 403:
                raise HTTPException(
                    status_code=res.status_code,
                    detail="Google Calendar authorization error: Invalid or revoked permissions."
                )
            if res.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Google Calendar API error: {res.text}"
                )

            data = res.json()
            raw_items = data.get("items", [])
            events = []
            for item in raw_items:
                start_obj = item.get("start", {})
                end_obj = item.get("end", {})
                start_time = start_obj.get("dateTime") or start_obj.get("date")
                end_time = end_obj.get("dateTime") or end_obj.get("date")
                events.append({
                    "id": item.get("id"),
                    "title": item.get("summary", "(No Title)"),
                    "description": item.get("description", ""),
                    "startTime": start_time,
                    "endTime": end_time,
                    "location": item.get("location", ""),
                    "status": item.get("status", "confirmed"),
                    "htmlLink": item.get("htmlLink", ""),
                    "category": "calendar_event",
                    "source": "google_calendar"
                })

            return {
                "events": events,
                "nextPageToken": data.get("nextPageToken"),
                "timeZone": data.get("timeZone", "UTC")
            }

    async def check_availability(
        self,
        user_id: str,
        db: Session,
        target_start: datetime,
        target_end: datetime
    ) -> Dict[str, Any]:
        """
        Checks for scheduling conflicts between the proposed time and existing events.
        """
        events_res = await self.list_events(
            user_id=user_id,
            db=db,
            time_min=(target_start - timedelta(hours=12)).isoformat(),
            time_max=(target_end + timedelta(hours=12)).isoformat()
        )
        conflicts = []
        for ev in events_res.get("events", []):
            try:
                ev_start = datetime.fromisoformat(ev["startTime"].replace("Z", "+00:00"))
                ev_end = datetime.fromisoformat(ev["endTime"].replace("Z", "+00:00"))
                # Overlap condition: start < other_end and end > other_start
                if target_start < ev_end and target_end > ev_start:
                    conflicts.append(ev)
            except Exception:
                continue

        return {
            "hasConflict": len(conflicts) > 0,
            "conflicts": conflicts,
            "proposedStart": target_start.isoformat(),
            "proposedEnd": target_end.isoformat()
        }

    async def prepare_event_proposal(
        self,
        user_id: str,
        db: Session,
        title: str,
        start_time: str,
        end_time: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
        is_all_day: bool = False
    ) -> Dict[str, Any]:
        """
        Creates an explicit proposal and confirmation token.
        Security requirement: User must inspect conflicts and confirm before event is written to Calendar.
        For all-day events set is_all_day=True; start_time/end_time dates are used, times are ignored.
        """
        from app.services.date_parser import parse_natural_datetime
        try:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        except Exception:
            start_dt, end_dt, _ = parse_natural_datetime(f"{start_time} to {end_time}")

        if not is_all_day and end_dt <= start_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Event end time must be after start time."
            )

        token = f"tok_cal_{uuid.uuid4().hex}"

        if is_all_day:
            # Google Calendar all-day event: use date-only strings, end date is exclusive
            date_str = start_dt.strftime("%Y-%m-%d")
            end_date_str = (start_dt + timedelta(days=1)).strftime("%Y-%m-%d")
            event_payload = {
                "summary": title,
                "description": description or "",
                "location": location or "",
                "start": {"date": date_str},
                "end": {"date": end_date_str},
                "colorId": "11"
            }
            avail = {"hasConflict": False, "conflicts": []}  # All-day blocks don't conflict with timed events
            preview_start = date_str
            preview_end = end_date_str
        else:
            try:
                avail = await self.check_availability(user_id, db, start_dt, end_dt)
            except Exception:
                avail = {"isAvailable": True, "conflicts": [], "hasConflict": False}
            event_payload = {
                "summary": title,
                "description": description or "",
                "location": location or "",
                "start": {"dateTime": start_dt.isoformat()},
                "end": {"dateTime": end_dt.isoformat()}
            }
            preview_start = start_dt.isoformat()
            preview_end = end_dt.isoformat()

        self._event_confirmations[token] = {
            "user_id": user_id,
            "event_payload": event_payload,
            "is_all_day": is_all_day,
            "created_at": datetime.now(timezone.utc)
        }

        return {
            "confirmationToken": token,
            "requiresConfirmation": True,
            "isAllDay": is_all_day,
            "previewEvent": {
                "title": title,
                "startTime": preview_start,
                "endTime": preview_end,
                "location": location or "",
                "description": description or "",
                "isAllDay": is_all_day
            },
            "conflicts": avail["conflicts"],
            "hasConflict": avail["hasConflict"]
        }

    async def create_event_confirmed(
        self,
        user_id: str,
        db: Session,
        confirmation_token: str
    ) -> Dict[str, Any]:
        """
        Executes Google Calendar event creation ONLY after human confirmation token validation.
        Prevents duplicate execution: each token can only be used once.
        Enforces 15-minute token expiry.
        """
        # Reject already-consumed tokens (prevents duplicate events on retry)
        if confirmation_token in self._completed_tokens:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This confirmation has already been executed. The event may already exist on your calendar."
            )

        if not confirmation_token or confirmation_token not in self._event_confirmations:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired calendar confirmation token. Please start a new request."
            )

        proposal = self._event_confirmations[confirmation_token]

        # Enforce token expiry
        age_seconds = (datetime.now(timezone.utc) - proposal["created_at"]).total_seconds()
        if age_seconds > self.TOKEN_TTL_SECONDS:
            self._event_confirmations.pop(confirmation_token, None)
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Calendar confirmation token has expired (15-minute limit). Please start a new request."
            )

        # Tenant isolation: confirm user owns this token
        if proposal["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security violation: Confirmation token does not belong to authenticated user."
            )

        # Consume token atomically before API call (prevents race-condition duplicates)
        self._event_confirmations.pop(confirmation_token)
        self._completed_tokens.add(confirmation_token)

        # Limit completed-tokens set size to prevent unbounded growth
        if len(self._completed_tokens) > 2000:
            self._completed_tokens.clear()

        access_token = await self._get_access_token_or_raise(user_id, db)
        is_all_day = proposal.get("is_all_day", False)
        summary = proposal["event_payload"].get("summary", "")

        # Check for existing equivalent event on the calendar before creating (handles idempotency & retry after timeout)
        try:
            if is_all_day:
                d_start = proposal["event_payload"].get("start", {}).get("date")
                d_end = proposal["event_payload"].get("end", {}).get("date")
                check_min = f"{d_start}T00:00:00Z"
                check_max = f"{d_end}T23:59:59Z"
            else:
                check_min = proposal["event_payload"].get("start", {}).get("dateTime")
                check_max = proposal["event_payload"].get("end", {}).get("dateTime")

            if check_min and check_max:
                existing_res = await self.list_events(
                    user_id=user_id,
                    db=db,
                    time_min=check_min,
                    time_max=check_max
                )
                for existing_ev in existing_res.get("events", []):
                    if existing_ev.get("title", "").strip().lower() == summary.strip().lower():
                        existing_start = existing_ev.get("startTime", "")
                        if is_all_day and (existing_start == d_start or existing_start.startswith(d_start)):
                            return {
                                "created": True,
                                "id": existing_ev.get("id"),
                                "title": existing_ev.get("title"),
                                "startTime": d_start,
                                "endTime": d_end,
                                "isAllDay": True,
                                "htmlLink": existing_ev.get("htmlLink", ""),
                                "alreadyExisted": True,
                                "status": "confirmed",
                                "message": f"Your {existing_ev.get('title')} event has been confirmed on your Google Calendar as an all-day event."
                            }
                        elif not is_all_day and existing_start == check_min:
                            return {
                                "created": True,
                                "id": existing_ev.get("id"),
                                "title": existing_ev.get("title"),
                                "startTime": existing_start,
                                "endTime": existing_ev.get("endTime"),
                                "isAllDay": False,
                                "htmlLink": existing_ev.get("htmlLink", ""),
                                "alreadyExisted": True,
                                "status": "confirmed",
                                "message": f"Your {existing_ev.get('title')} event has been confirmed on your Google Calendar."
                            }
        except Exception:
            pass

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                f"{CALENDAR_API_BASE}/events",
                headers=self._get_client_headers(access_token),
                json=proposal["event_payload"]
            )
            if res.status_code not in (200, 201):
                # Re-allow retry on API failure (remove from completed set)
                self._completed_tokens.discard(confirmation_token)
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"Google Calendar event creation failed: {res.text}"
                )
            created = res.json()
            if is_all_day:
                start_val = created.get("start", {}).get("date")
                end_val = created.get("end", {}).get("date")
            else:
                start_val = created.get("start", {}).get("dateTime")
                end_val = created.get("end", {}).get("dateTime")
            return {
                "created": True,
                "id": created.get("id"),
                "title": created.get("summary"),
                "startTime": start_val,
                "endTime": end_val,
                "isAllDay": is_all_day,
                "htmlLink": created.get("htmlLink"),
                "status": "confirmed",
                "message": f"Your {created.get('summary')} event has been added to your Google Calendar as an all-day event." if is_all_day else f"Your {created.get('summary')} event has been added to your Google Calendar."
            }

    async def update_event(
        self,
        user_id: str,
        db: Session,
        event_id: str,
        title: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Updates an existing event in Google Calendar.
        """
        token = await self._get_access_token_or_raise(user_id, db)
        patch_body: Dict[str, Any] = {}
        if title:
            patch_body["summary"] = title
        if start_time:
            patch_body["start"] = {"dateTime": start_time}
        if end_time:
            patch_body["end"] = {"dateTime": end_time}

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.patch(
                f"{CALENDAR_API_BASE}/events/{event_id}",
                headers=self._get_client_headers(token),
                json=patch_body
            )
            if res.status_code != 200:
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"Failed to update calendar event: {res.text}"
                )
            return res.json()

    async def create_event_direct(
        self,
        user_id: str,
        db: Session,
        title: str,
        start_time: str,
        end_time: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a Calendar event directly without requiring a confirmation token.
        Used by the plan sync-calendar endpoint after the user has already confirmed
        their selection in the UI. Not exposed to the chatbot or unguarded endpoints.
        """
        token = await self._get_access_token_or_raise(user_id, db)

        # Ensure timezone info is present (Google requires it)
        def _ensure_tz(dt_str: str) -> str:
            if "+" not in dt_str and not dt_str.endswith("Z") and "T" in dt_str:
                return dt_str + "Z"
            return dt_str

        event_body: Dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": _ensure_tz(start_time)},
            "end":   {"dateTime": _ensure_tz(end_time)},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                f"{CALENDAR_API_BASE}/events",
                headers=self._get_client_headers(token),
                json=event_body
            )
            if res.status_code not in (200, 201):
                raise Exception(f"Google Calendar API error {res.status_code}: {res.text[:300]}")
            data = res.json()
            return {
                "status": "success",
                "eventId": data.get("id"),
                "title": data.get("summary"),
                "startTime": data.get("start", {}).get("dateTime"),
                "endTime": data.get("end", {}).get("dateTime"),
                "htmlLink": data.get("htmlLink"),
            }

    async def delete_event(
        self,
        user_id: str,
        db: Session,
        event_id: str
    ) -> Dict[str, Any]:
        """
        Deletes an event from the user's primary Google Calendar.
        """
        token = await self._get_access_token_or_raise(user_id, db)
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.delete(
                f"{CALENDAR_API_BASE}/events/{event_id}",
                headers=self._get_client_headers(token)
            )
            if res.status_code not in (200, 204):
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"Failed to delete Google Calendar event: {res.text}"
                )
            return {"deleted": True, "eventId": event_id}

google_calendar_service = GoogleCalendarService()
