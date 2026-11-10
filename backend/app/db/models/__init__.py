import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, ForeignKey, JSON, Float, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.db.session import Base

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    avatar_url = Column(String(512), nullable=True)
    timezone = Column(String(64), default="UTC", nullable=False)
    onboarding_complete = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    timetables = relationship("Timetable", back_populates="user", cascade="all, delete-orphan")
    timetable_periods = relationship("TimetablePeriod", back_populates="user", cascade="all, delete-orphan")
    timetable_entries = relationship("TimetableEntry", back_populates="user", cascade="all, delete-orphan")
    academic_events = relationship("AcademicEvent", back_populates="user", cascade="all, delete-orphan")
    plans = relationship("Plan", back_populates="user", cascade="all, delete-orphan")
    integrations = relationship("IntegrationConnection", back_populates="user", cascade="all, delete-orphan")
    tool_logs = relationship("ToolExecutionLog", back_populates="user", cascade="all, delete-orphan")


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True) # google, gmail, calendar, drive
    external_user_id = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    # Encrypted tokens at rest with AES-GCM
    encrypted_access_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    scopes = Column(JSON, default=list)
    token_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="oauth_accounts")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), default="New Session", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False) # 'user' | 'assistant' | 'system'
    content = Column(Text, nullable=False)
    tool_executions = Column(JSON, default=list) # Array of tools run
    citations = Column(JSON, default=list) # Grounded sources
    suggested_action = Column(JSON, nullable=True) # Proposed action requiring confirmation
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    conversation = relationship("Conversation", back_populates="messages")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    page_count = Column(Integer, default=1)
    chunk_count = Column(Integer, default=0)
    category = Column(String(50), default="general") # timetable, academic, notes
    document_type = Column(String(50), default="NOTES", nullable=True) # SYLLABUS, NOTES, TIMETABLE, ACADEMIC_CALENDAR
    file_path = Column(String(512), nullable=True)
    status = Column(String(30), default="indexed") # processing, indexed, failed
    processing_status = Column(String(30), default="UPLOADED", nullable=True) # UPLOADED, PROCESSING, REVIEW_REQUIRED, COMPLETED, FAILED
    processing_error = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    document_version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    extracted_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    timetables = relationship("TimetableEntry", back_populates="document", cascade="all, delete-orphan")
    academic_events = relationship("AcademicEvent", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    page_number = Column(Integer, default=1)
    embedding = Column(JSON, nullable=True) # Normalized vector representation
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    document = relationship("Document", back_populates="chunks")


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    course_name = Column(String(255), nullable=False)
    course_code = Column(String(50), nullable=False)
    day_of_week = Column(String(20), nullable=False, index=True) # Monday, Tuesday, etc.
    start_time = Column(String(20), nullable=False) # "10:00 AM" or "10:00"
    end_time = Column(String(20), nullable=False) # "12:00 PM" or "12:00"
    room = Column(String(100), nullable=True)
    instructor = Column(String(255), nullable=True)
    class_type = Column(String(50), nullable=True) # Theory, Lab, Practical, Tutorial
    academic_year = Column(String(50), nullable=True)
    semester = Column(String(50), nullable=True)
    source_page = Column(Integer, default=1, nullable=True)
    source_row = Column(Integer, nullable=True)
    confidence = Column(Float, default=1.0, nullable=True)
    additional_details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="timetable_entries")
    document = relationship("Document", back_populates="timetables")

    @property
    def subject_name(self):
        return self.course_name

    @subject_name.setter
    def subject_name(self, value):
        self.course_name = value

    @property
    def subject_code(self):
        return self.course_code

    @subject_code.setter
    def subject_code(self, value):
        self.course_code = value

    @property
    def room_number(self):
        return self.room

    @room_number.setter
    def room_number(self, value):
        self.room = value

    @property
    def faculty_name(self):
        return self.instructor

    @faculty_name.setter
    def faculty_name(self, value):
        self.instructor = value


class Timetable(Base):
    __tablename__ = "timetables"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), default="My Timetable", nullable=False)
    academic_year = Column(String(50), nullable=True) # e.g. "2026-2027"
    semester = Column(String(50), nullable=True)      # e.g. "5th Sem"
    section = Column(String(50), nullable=True)       # e.g. "Section A"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="timetables")
    periods = relationship("TimetablePeriod", back_populates="timetable", cascade="all, delete-orphan", order_by="TimetablePeriod.day_of_week, TimetablePeriod.start_time")


class TimetablePeriod(Base):
    __tablename__ = "timetable_periods"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    timetable_id = Column(String(36), ForeignKey("timetables.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week = Column(String(20), nullable=False, index=True) # "Monday", "Tuesday", etc.
    subject_name = Column(String(255), nullable=False)
    subject_code = Column(String(50), nullable=True)
    start_time = Column(String(20), nullable=False) # "09:00 AM" or "09:00"
    end_time = Column(String(20), nullable=False)   # "10:00 AM" or "10:00"
    room = Column(String(100), nullable=True)
    faculty = Column(String(255), nullable=True)
    class_type = Column(String(50), default="Theory") # Theory, Lab, Tutorial, Break, Other
    period_number = Column(Integer, nullable=True) # 1, 2, 3...
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    timetable = relationship("Timetable", back_populates="periods")
    user = relationship("User", back_populates="timetable_periods")

    # Compatibility properties for code expecting course_name, instructor, room_number
    @property
    def course_name(self):
        return self.subject_name

    @course_name.setter
    def course_name(self, value):
        self.subject_name = value

    @property
    def course_code(self):
        return self.subject_code

    @course_code.setter
    def course_code(self, value):
        self.subject_code = value

    @property
    def instructor(self):
        return self.faculty

    @instructor.setter
    def instructor(self, value):
        self.faculty = value

    @property
    def room_number(self):
        return self.room

    @room_number.setter
    def room_number(self, value):
        self.room = value


class AcademicEvent(Base):
    __tablename__ = "academic_events"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    event_name = Column(String(255), nullable=False, index=True)
    category = Column(String(50), default="OTHER", nullable=False, index=True)
    # SEMESTER, EXAM, INTERNAL_ASSESSMENT, PRACTICAL_EXAM, HOLIDAY, COLLEGE_EVENT, REGISTRATION, ACADEMIC_DEADLINE, RESULT, OTHER
    start_date = Column(String(10), nullable=False, index=True) # "YYYY-MM-DD"
    end_date = Column(String(10), nullable=True, index=True)   # "YYYY-MM-DD"
    description = Column(Text, nullable=True)
    academic_year = Column(String(50), nullable=True)
    semester = Column(String(50), nullable=True)
    source_page = Column(Integer, nullable=True)
    source_row = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="academic_events")
    document = relationship("Document", back_populates="academic_events")


class Plan(Base):
    __tablename__ = "plans"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    period = Column(String(100), default="Current Week")
    subject = Column(String(255), nullable=True)
    learning_goal = Column(Text, nullable=True)
    start_date = Column(String(10), nullable=True) # "YYYY-MM-DD"
    end_date = Column(String(10), nullable=True)   # "YYYY-MM-DD"
    duration_days = Column(Integer, nullable=True)
    daily_hours_target = Column(Float, default=2.0)
    preferred_study_days = Column(JSON, default=list) # e.g. ["Monday", "Wednesday", "Friday"]
    generation_status = Column(String(30), default="complete") # "pending", "generating", "complete", "failed"
    goals = Column(JSON, default=list)
    suggested_study_blocks = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="plans")
    tasks = relationship("PlanTask", back_populates="plan", cascade="all, delete-orphan", order_by="PlanTask.task_order, PlanTask.scheduled_date, PlanTask.created_at")


class PlanTask(Base):
    __tablename__ = "plan_tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    plan_id = Column(String(36), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    duration_minutes = Column(Integer, default=45)
    priority = Column(String(20), default="high")
    completed = Column(Boolean, default=False)
    scheduled_time = Column(String(100), nullable=True)
    scheduled_date = Column(String(10), nullable=True) # "YYYY-MM-DD"
    start_time = Column(String(30), nullable=True)     # "HH:MM" or ISO
    end_time = Column(String(30), nullable=True)       # "HH:MM" or ISO
    timezone = Column(String(64), nullable=True)       # e.g. "Asia/Kolkata" or "America/Los_Angeles"
    google_calendar_event_id = Column(String(255), nullable=True)
    month_number = Column(Integer, nullable=True)      # 1-based (Month 1, Month 2, ...)
    week_number = Column(Integer, nullable=True)       # 1-based (Week 1, Week 2, ...)
    day_number = Column(Integer, nullable=True)        # 1-based (Day 1, Day 14, ...)
    task_order = Column(Integer, default=0)
    task_type = Column(String(30), default="daily")    # "daily", "milestone", "practice", "revision", "assessment"
    day_label = Column(String(30), nullable=True)      # e.g. "Day 1"
    week_label = Column(String(30), nullable=True)     # e.g. "Week 1"
    month_label = Column(String(30), nullable=True)    # e.g. "Month 1"
    milestone_group = Column(String(255), nullable=True) # e.g. "Month 1 Milestone: Core Foundations"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    plan = relationship("Plan", back_populates="tasks")


class IntegrationConnection(Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_integration_user_provider"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False) # google, gmail, calendar, drive, web_search, weather, rag
    status = Column(String(30), default="not_connected") # connected, not_connected, expired, error
    account_email = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    capabilities = Column(JSON, default=dict) # User application-level capability toggles
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="integrations")


class ToolExecutionLog(Base):
    __tablename__ = "tool_execution_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False) # running, success, failed
    parameters = Column(JSON, nullable=True)
    result_summary = Column(Text, nullable=True)
    execution_duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="tool_logs")
