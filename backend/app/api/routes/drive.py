from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, OAuthAccount
from app.middleware.auth_middleware import get_current_user
from app.core.config import settings
from app.services.google_services.drive_service import google_drive_service

router = APIRouter(prefix="/drive", tags=["Google Drive"])

@router.get("/files")
async def list_drive_files(
    query: Optional[str] = Query(None),
    pageSize: int = Query(20, le=50),
    pageToken: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Searches and lists relevant files from the authenticated user's Google Drive.
    """
    oauth = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == user.id,
        OAuthAccount.provider.in_(["drive", "google_all", "google"])
    ).first()

    if oauth:
        return await google_drive_service.search_files(
            user_id=user.id,
            db=db,
            query=query,
            page_size=pageSize,
            page_token=pageToken
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Google Drive is not connected. Please connect Drive in Workspace Settings."
    )

@router.get("/files/{file_id}")
async def get_drive_file_meta(
    file_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves metadata for a specific file in Google Drive.
    """
    return await google_drive_service.get_file_metadata(
        user_id=user.id,
        db=db,
        file_id=file_id
    )

@router.get("/files/{file_id}/content")
async def get_drive_file_content(
    file_id: str,
    maxBytes: int = Query(100_000, le=500_000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reads text content from supported Drive files (Google Docs export, text, PDF preview).
    """
    return await google_drive_service.read_file_content(
        user_id=user.id,
        db=db,
        file_id=file_id,
        max_bytes=maxBytes
    )
