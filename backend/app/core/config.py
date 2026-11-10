import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, AliasChoices

class Settings(BaseSettings):
    APP_ENV: str = Field(default="development", validation_alias=AliasChoices("APP_ENV", "ENVIRONMENT"))
    APP_NAME: str = "AURELIA AI"
    APP_SECRET_KEY: str = "dev-secret-key-aurelia-enterprise-2026-safe-for-local"
    BACKEND_PORT: int = 8000
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"

    # Database
    DATABASE_URL: str = "sqlite:///./aurelia.db"

    # Storage
    STORAGE_PROVIDER: str = "local"
    STORAGE_PATH: str = "./storage"

    # Encryption & Tokens
    TOKEN_ENCRYPTION_KEY: str = "dGhpc2lzYXRlc3RrZXlmb3JhZXMyNTZnY21lbmM="
    SESSION_SECRET: str = "aurelia-dev-session-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    ALGORITHM: str = "HS256"

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"

    # LLM & AI
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_API_KEY: Optional[str] = None

    # Embeddings
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL: str = "text-embedding-004"
    VECTOR_STORE: str = "pgvector"

    # External APIs
    WEB_SEARCH_PROVIDER: str = "tavily"
    WEB_SEARCH_API_KEY: Optional[str] = None
    WEATHER_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def ENVIRONMENT(self) -> str:
        return self.APP_ENV

    def check_production_safety(self):
        """
        Validates critical security invariants when running in production mode.
        """
        if self.APP_ENV.lower() == "production":
            insecure_secrets = [
                "dev-secret-key-aurelia-enterprise-2026-safe-for-local",
                "change-this-in-production-to-a-secure-random-32-byte-hex",
                "aurelia-super-secret-session-key-change-in-prod"
            ]
            if self.APP_SECRET_KEY in insecure_secrets or len(self.APP_SECRET_KEY) < 32:
                raise ValueError("Production security error: Insecure or default APP_SECRET_KEY detected. Provide a secure 32+ character key.")

            default_token_key = "dGhpc2lzYXRlc3RrZXlmb3JhZXMyNTZnY21lbmM="
            if self.TOKEN_ENCRYPTION_KEY == default_token_key:
                raise ValueError("Production security error: Default test TOKEN_ENCRYPTION_KEY detected. Provide a unique 32-byte base64 encryption key.")

            if not self.GOOGLE_CLIENT_ID or not self.GOOGLE_CLIENT_SECRET:
                raise ValueError("Production security error: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured.")

settings = Settings()
