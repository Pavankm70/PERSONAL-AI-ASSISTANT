import base64
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Dict, Any, List, Optional
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.services.google_oauth.oauth_service import get_valid_user_credentials

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

class GoogleGmailService:
    """
    Real Google Gmail operations service.
    Strictly tenant-isolated: all calls require user_id and use only the authenticated user's credentials.
    """
    TOKEN_TTL_SECONDS = 900  # 15 minute lifespan for email dispatch confirmations

    def __init__(self):
        # Confirmation tokens for sensitive operations (e.g. sending emails)
        # Token -> {"user_id": str, "payload": dict, "created_at": datetime}
        self._send_confirmations: Dict[str, Dict[str, Any]] = {}

    def _get_client_headers(self, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def _get_access_token_or_raise(self, user_id: str, db: Session) -> str:
        creds = await get_valid_user_credentials(user_id=user_id, provider="gmail", db=db)
        if not creds or not creds.get("access_token"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Gmail is not connected or credentials have expired. Please connect Gmail in Integrations."
            )
        return creds["access_token"]

    async def list_messages(
        self,
        user_id: str,
        db: Session,
        query: Optional[str] = None,
        max_results: int = 15,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Lists and searches messages in the authenticated user's Gmail mailbox.
        """
        token = await self._get_access_token_or_raise(user_id, db)
        params: Dict[str, Any] = {"maxResults": min(max_results, 50)}
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{GMAIL_API_BASE}/messages",
                headers=self._get_client_headers(token),
                params=params
            )
            if res.status_code == 401 or res.status_code == 403:
                raise HTTPException(
                    status_code=res.status_code,
                    detail="Gmail authorization error: Access expired or insufficient permissions."
                )
            if res.status_code == 429:
                raise HTTPException(status_code=429, detail="Gmail rate limit exceeded. Please try again shortly.")
            if res.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Gmail API error: {res.text}"
                )

            data = res.json()
            raw_messages = data.get("messages", [])
            next_page = data.get("nextPageToken")

            # Hydrate top messages with headers/snippets
            messages = []
            for item in raw_messages[:15]:
                msg_id = item["id"]
                msg_detail = await self.get_message(user_id, db, msg_id, format="metadata")
                if msg_detail:
                    messages.append(msg_detail)

            return {
                "messages": messages,
                "nextPageToken": next_page,
                "resultSizeEstimate": data.get("resultSizeEstimate", len(messages))
            }

    async def get_message(
        self,
        user_id: str,
        db: Session,
        message_id: str,
        format: str = "full"
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves full details or metadata for a single email message.
        """
        token = await self._get_access_token_or_raise(user_id, db)
        params = {"format": format}
        if format == "metadata":
            params["metadataHeaders"] = ["From", "Subject", "Date", "To"]

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{GMAIL_API_BASE}/messages/{message_id}",
                headers=self._get_client_headers(token),
                params=params
            )
            if res.status_code != 200:
                return None

            msg_json = res.json()
            headers_list = msg_json.get("payload", {}).get("headers", [])
            headers = {h["name"].lower(): h["value"] for h in headers_list if "name" in h and "value" in h}

            from_header = headers.get("from", "Unknown Sender")
            from_name = from_header
            from_email = from_header
            if "<" in from_header and ">" in from_header:
                parts = from_header.split("<")
                from_name = parts[0].strip(' "')
                from_email = parts[1].split(">")[0].strip()

            snippet = msg_json.get("snippet", "")
            date_str = headers.get("date", datetime.now(timezone.utc).isoformat())

            # Check labels
            label_ids = msg_json.get("labelIds", [])
            is_unread = "UNREAD" in label_ids
            is_important = "IMPORTANT" in label_ids

            # Extract body if full format requested
            body_text = snippet
            if format == "full":
                body_text = self._extract_body(msg_json.get("payload", {})) or snippet

            return {
                "id": msg_json.get("id"),
                "threadId": msg_json.get("threadId"),
                "fromName": from_name,
                "fromEmail": from_email,
                "to": headers.get("to", ""),
                "subject": headers.get("subject", "(No Subject)"),
                "snippet": snippet,
                "body": body_text,
                "date": date_str,
                "isUnread": is_unread,
                "isImportant": is_important,
                "aiPriority": "high" if is_important or "urgent" in snippet.lower() else "normal",
                "labelIds": label_ids,
                "gmailLink": f"https://mail.google.com/mail/u/0/#inbox/{msg_json.get('threadId')}"
            }

    async def get_thread(self, user_id: str, db: Session, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a full email conversation thread.
        """
        token = await self._get_access_token_or_raise(user_id, db)
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{GMAIL_API_BASE}/threads/{thread_id}",
                headers=self._get_client_headers(token)
            )
            if res.status_code != 200:
                return None
            return res.json()

    async def create_draft(
        self,
        user_id: str,
        db: Session,
        to: str,
        subject: str,
        body: str
    ) -> Dict[str, Any]:
        """
        Creates an email draft in the authenticated user's Gmail account.
        """
        token = await self._get_access_token_or_raise(user_id, db)
        raw_b64 = self._encode_email(to=to, subject=subject, body=body)

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                f"{GMAIL_API_BASE}/drafts",
                headers=self._get_client_headers(token),
                json={"message": {"raw": raw_b64}}
            )
            if res.status_code not in (200, 201):
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"Failed to create Gmail draft: {res.text}"
                )
            data = res.json()
            return {
                "draftId": data.get("id"),
                "messageId": data.get("message", {}).get("id"),
                "to": to,
                "subject": subject,
                "status": "draft_created"
            }

    def prepare_send_confirmation(
        self,
        user_id: str,
        to: str,
        subject: str,
        body: str
    ) -> Dict[str, Any]:
        """
        Constructs an explicit confirmation proposal for sending an email.
        Security invariant: No email is sent until user explicitly provides this confirmation token.
        """
        token = f"tok_mail_{uuid.uuid4().hex}"
        self._send_confirmations[token] = {
            "user_id": user_id,
            "to": to,
            "subject": subject,
            "body": body,
            "created_at": datetime.now(timezone.utc)
        }
        return {
            "confirmationToken": token,
            "requiresConfirmation": True,
            "proposedEmail": {
                "to": to,
                "subject": subject,
                "bodyPreview": body[:300] + ("..." if len(body) > 300 else "")
            }
        }

    async def send_email_confirmed(
        self,
        user_id: str,
        db: Session,
        confirmation_token: str
    ) -> Dict[str, Any]:
        """
        Sends an email via Gmail API ONLY after validating human confirmation token.
        """
        if not confirmation_token or confirmation_token not in self._send_confirmations:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired send confirmation token."
            )

        proposal = self._send_confirmations.pop(confirmation_token)
        if proposal["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security violation: Confirmation token does not belong to the authenticated user."
            )

        # Check token expiry (15 mins)
        age_seconds = (datetime.now(timezone.utc) - proposal["created_at"]).total_seconds()
        if age_seconds > self.TOKEN_TTL_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Send email confirmation token has expired (15-minute limit). Please request sending again."
            )

        token = await self._get_access_token_or_raise(user_id, db)
        raw_b64 = self._encode_email(
            to=proposal["to"],
            subject=proposal["subject"],
            body=proposal["body"]
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                f"{GMAIL_API_BASE}/messages/send",
                headers=self._get_client_headers(token),
                json={"raw": raw_b64}
            )
            if res.status_code not in (200, 201):
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"Gmail send failed: {res.text}"
                )
            data = res.json()
            return {
                "sent": True,
                "messageId": data.get("id"),
                "threadId": data.get("threadId"),
                "to": proposal["to"],
                "subject": proposal["subject"]
            }

    def _encode_email(self, to: str, subject: str, body: str) -> str:
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        raw_bytes = msg.as_bytes()
        return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        # Check direct body
        body_data = payload.get("body", {}).get("data")
        if body_data:
            try:
                return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            except Exception:
                pass

        # Check multipart
        parts = payload.get("parts", [])
        for part in parts:
            mime = part.get("mimeType", "")
            if mime == "text/plain":
                data = part.get("body", {}).get("data")
                if data:
                    try:
                        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    except Exception:
                        pass
        return ""

google_gmail_service = GoogleGmailService()
