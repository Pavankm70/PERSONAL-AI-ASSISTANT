from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.session import init_db
from app.api.routes import (
    auth,
    dashboard,
    chat,
    gmail,
    calendar,
    drive,
    knowledge,
    timetable,
    plans,
    integrations,
    settings as settings_routes
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enforce production security invariants if in production
    settings.check_production_safety()
    # Initialize database tables on startup
    init_db()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="Aurelia AI — Production Personal Intelligence Platform API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
origins = [
    settings.FRONTEND_URL,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://[::1]:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://[::1]:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://[::1]:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:[0-9]+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Central exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "path": str(request.url.path)}
    )

# Include Routers with /api prefix
api_prefix = "/api"
app.include_router(auth.router, prefix=api_prefix)
app.include_router(dashboard.router, prefix=api_prefix)
app.include_router(chat.router, prefix=api_prefix)
app.include_router(gmail.router, prefix=api_prefix)
app.include_router(calendar.router, prefix=api_prefix)
app.include_router(drive.router, prefix=api_prefix)
app.include_router(knowledge.router, prefix=api_prefix)
app.include_router(timetable.router, prefix=api_prefix)
app.include_router(plans.router, prefix=api_prefix)
app.include_router(integrations.router, prefix=api_prefix)
app.include_router(settings_routes.router, prefix=api_prefix)

# Health & Readiness Endpoints
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}

@app.get("/ready", tags=["Health"])
def ready():
    return {"status": "ready", "database": "connected"}

@app.get("/", tags=["Health"])
def root():
    return {
        "brand": settings.APP_NAME,
        "message": "Aurelia AI Backend Core Online",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT, reload=True)
