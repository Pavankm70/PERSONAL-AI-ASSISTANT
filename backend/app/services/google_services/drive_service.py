from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.services.google_oauth.oauth_service import get_valid_user_credentials

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

class GoogleDriveService:
    """
    Real Google Drive API operations service.
    Strictly tenant-isolated by user_id with read-only least-privilege operations.
    """
    def _get_client_headers(self, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }

    async def _get_access_token_or_raise(self, user_id: str, db: Session) -> str:
        creds = await get_valid_user_credentials(user_id=user_id, provider="drive", db=db)
        if not creds or not creds.get("access_token"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google Drive is not connected or credentials have expired. Please connect Drive in Integrations."
            )
        return creds["access_token"]

    async def search_files(
        self,
        user_id: str,
        db: Session,
        query: Optional[str] = None,
        page_size: int = 20,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Searches and lists relevant files in the user's Drive.
        Excludes trashed files by default.
        """
        token = await self._get_access_token_or_raise(user_id, db)
        q_clauses = ["trashed = false"]
        if query:
            # Match in name or full text
            escaped = query.replace("'", "\\'")
            q_clauses.append(f"(name contains '{escaped}' or fullText contains '{escaped}')")

        params = {
            "q": " and ".join(q_clauses),
            "pageSize": min(page_size, 50),
            "fields": "nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink, iconLink, capabilities/canDownload)"
        }
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{DRIVE_API_BASE}/files",
                headers=self._get_client_headers(token),
                params=params
            )
            if res.status_code == 401 or res.status_code == 403:
                raise HTTPException(
                    status_code=res.status_code,
                    detail="Google Drive authorization error: Invalid or missing drive permissions."
                )
            if res.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Google Drive API error: {res.text}"
                )

            data = res.json()
            files = []
            for f in data.get("files", []):
                size_bytes = int(f.get("size", 0)) if f.get("size") else None
                files.append({
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "mimeType": f.get("mimeType"),
                    "sizeBytes": size_bytes,
                    "modifiedTime": f.get("modifiedTime"),
                    "webViewLink": f.get("webViewLink"),
                    "iconLink": f.get("iconLink"),
                    "isGoogleDoc": "application/vnd.google-apps" in f.get("mimeType", "")
                })

            return {
                "files": files,
                "nextPageToken": data.get("nextPageToken"),
                "count": len(files)
            }

    async def get_file_metadata(
        self,
        user_id: str,
        db: Session,
        file_id: str
    ) -> Dict[str, Any]:
        """
        Retrieves complete metadata for a Drive file.
        """
        token = await self._get_access_token_or_raise(user_id, db)
        params = {
            "fields": "id, name, mimeType, size, modifiedTime, createdTime, webViewLink, owners, capabilities"
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{DRIVE_API_BASE}/files/{file_id}",
                headers=self._get_client_headers(token),
                params=params
            )
            if res.status_code != 200:
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"Failed to retrieve file metadata from Google Drive: {res.text}"
                )
            return res.json()

    async def read_file_content(
        self,
        user_id: str,
        db: Session,
        file_id: str,
        max_bytes: int = 100_000
    ) -> Dict[str, Any]:
        """
        Reads text content from supported Drive files:
        - Plain text, markdown, json, csv
        - Google Docs exported as text/plain
        - Google Sheets exported as text/csv
        - PDF preview/extraction
        """
        token = await self._get_access_token_or_raise(user_id, db)
        meta = await self.get_file_metadata(user_id, db, file_id)
        mime = meta.get("mimeType", "")
        name = meta.get("name", "Document")

        async with httpx.AsyncClient(timeout=20.0) as client:
            # 1. Google Workspace Docs -> Export as plain text
            if mime == "application/vnd.google-apps.document":
                res = await client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}/export",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"mimeType": "text/plain"}
                )
                if res.status_code != 200:
                    raise HTTPException(status_code=res.status_code, detail="Unable to export Google Doc as text.")
                text = res.text[:max_bytes]
                return {
                    "fileId": file_id,
                    "name": name,
                    "mimeType": mime,
                    "content": text,
                    "charCount": len(text),
                    "isTruncated": len(res.text) > max_bytes
                }

            # 2. Google Workspace Sheets -> Export as CSV
            elif mime == "application/vnd.google-apps.spreadsheet":
                res = await client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}/export",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"mimeType": "text/csv"}
                )
                if res.status_code != 200:
                    raise HTTPException(status_code=res.status_code, detail="Unable to export Google Sheet as CSV.")
                text = res.text[:max_bytes]
                return {
                    "fileId": file_id,
                    "name": name,
                    "mimeType": mime,
                    "content": text,
                    "charCount": len(text),
                    "isTruncated": len(res.text) > max_bytes
                }

            # 3. Standard Text, Markdown, CSV, JSON
            elif any(t in mime for t in ["text/", "json", "csv", "xml"]):
                res = await client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"alt": "media"}
                )
                if res.status_code != 200:
                    raise HTTPException(status_code=res.status_code, detail="Unable to download file content.")
                text = res.text[:max_bytes]
                return {
                    "fileId": file_id,
                    "name": name,
                    "mimeType": mime,
                    "content": text,
                    "charCount": len(text),
                    "isTruncated": len(res.text) > max_bytes
                }

            # 4. PDF inspection
            elif mime == "application/pdf":
                res = await client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"alt": "media"}
                )
                if res.status_code != 200:
                    raise HTTPException(status_code=res.status_code, detail="Unable to read PDF from Drive.")
                return {
                    "fileId": file_id,
                    "name": name,
                    "mimeType": mime,
                    "content": f"[PDF Document '{name}' retrieved from Google Drive. Binary length: {len(res.content)} bytes. Available for viewing in Google Drive or vector indexing.]",
                    "charCount": len(res.content),
                    "isBinary": True,
                    "webViewLink": meta.get("webViewLink")
                }

            # 5. Unsupported formats
            else:
                return {
                    "fileId": file_id,
                    "name": name,
                    "mimeType": mime,
                    "content": f"[Unsupported binary or multimedia format ({mime}). Direct preview unavailable. View file directly via Google Drive link.]",
                    "webViewLink": meta.get("webViewLink"),
                    "isSupported": False
                }

google_drive_service = GoogleDriveService()
