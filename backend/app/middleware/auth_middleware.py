from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.core.config import settings
from app.core.security import decode_access_token

security_scheme = HTTPBearer(auto_error=False)

def get_current_user(
    auth_header: HTTPAuthorizationCredentials = Security(security_scheme),
    db: Session = Depends(get_db)
) -> User:
    if not auth_header or not auth_header.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.credentials

    # Only permit mock dev token in non-production environments
    if token == "mock_jwt_token_aurelia_dev":
        if settings.APP_ENV == "production":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Development token is disabled in production.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = db.query(User).filter(User.email == "alex.chen@university.edu").first()
        if not user:
            user = User(
                email="alex.chen@university.edu",
                full_name="Alex Chen",
                timezone="America/Los_Angeles",
                onboarding_complete=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject identifier."
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found."
        )
    return user
