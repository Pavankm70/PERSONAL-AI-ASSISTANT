from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

# --- User & Auth Schemas ---
class UserProfileResponse(BaseModel):
    id: str
    email: str
    fullName: str
    avatarUrl: Optional[str] = None
    timezone: str = "UTC"
    onboardingComplete: bool = False
    createdAt: datetime

class DevLoginRequest(BaseModel):
    email: str
    fullName: str

class AuthTokenResponse(BaseModel):
    user: UserProfileResponse
    token: str

# --- Chat & Agent Schemas ---
class ToolExecutionSchema(BaseModel):
    id: str
    toolName: str
    status: str # running, success, failed
    timestamp: str
    parameters: Optional[Dict[str, Any]] = None
    resultSummary: Optional[str] = None

class CitationSchema(BaseModel):
    id: str
    sourceType: str # document, calendar, email, web
    title: str
    snippet: str
    url: Optional[str] = None
    documentId: Optional[str] = None
    page: Optional[int] = None

class SuggestedActionSchema(BaseModel):
    id: str
    actionType: str # create_event, modify_event, delete_event, create_plan
    title: str
    details: Dict[str, Any]
    status: str = "pending" # pending, approved, confirmed, failed, rejected
    confirmationToken: Optional[str] = None

class ChatMessageRequest(BaseModel):
    message: str
    conversationId: Optional[str] = None

class ChatMessageResponse(BaseModel):
    id: str
    conversationId: str
    role: str
    content: str
    createdAt: str
    toolExecutions: List[ToolExecutionSchema] = []
    citations: List[CitationSchema] = []
    suggestedAction: Optional[SuggestedActionSchema] = None

# --- Calendar Schemas ---
class CalendarEventSchema(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    startTime: str
    endTime: str
    location: Optional[str] = None
    attendees: List[str] = []
    category: Optional[str] = "event"
    source: str = "google_calendar"

class CalendarPreviewRequest(BaseModel):
    query: str

class CalendarConfirmRequest(BaseModel):
    confirmationToken: str
    event: Dict[str, Any] = {}
    actionId: Optional[str] = None

# --- Gmail Schemas ---
class EmailMessageSchema(BaseModel):
    id: str
    threadId: str
    fromName: str
    fromEmail: str
    subject: str
    snippet: str
    date: str
    isUnread: bool
    isImportant: bool
    aiPriority: str
    summary: Optional[str] = None
    actionItems: List[str] = []
    gmailLink: Optional[str] = None

class GmailSummarizeRequest(BaseModel):
    messageId: str

class GmailDraftRequest(BaseModel):
    to: str
    subject: str
    body: str

class GmailPrepareSendRequest(BaseModel):
    to: str
    subject: str
    body: str

class GmailConfirmSendRequest(BaseModel):
    confirmationToken: str

# --- Drive Schemas ---
class DriveFileSchema(BaseModel):
    id: str
    name: str
    mimeType: str
    sizeBytes: Optional[int] = None
    modifiedTime: Optional[str] = None
    webViewLink: Optional[str] = None
    iconLink: Optional[str] = None
    isGoogleDoc: bool = False

# --- Knowledge & RAG Schemas ---
class KnowledgeDocumentSchema(BaseModel):
    id: str
    filename: str
    fileSize: int
    mimeType: str
    pageCount: Optional[int] = 1
    chunkCount: int = 0
    category: str
    status: str
    uploadedAt: str
    errorMessage: Optional[str] = None

class KnowledgeQueryRequest(BaseModel):
    query: str

class KnowledgeQueryResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]] = []
    timetableMatches: List[Dict[str, Any]] = []

# --- Plans Schemas ---
class PlanTaskSchema(BaseModel):
    id: str
    title: str
    durationMinutes: int = 45
    priority: str = "high"
    completed: bool = False
    scheduledTime: Optional[str] = None
    scheduledDate: Optional[str] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    timezone: Optional[str] = None
    googleCalendarEventId: Optional[str] = None

class TaskCreateRequest(BaseModel):
    title: str
    durationMinutes: int = 45
    priority: str = "high"
    completed: bool = False
    scheduledDate: Optional[str] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    timezone: Optional[str] = None
    googleCalendarEventId: Optional[str] = None

class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    durationMinutes: Optional[int] = None
    priority: Optional[str] = None
    completed: Optional[bool] = None
    scheduledDate: Optional[str] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    timezone: Optional[str] = None
    googleCalendarEventId: Optional[str] = None

class PlanCreateRequest(BaseModel):
    title: str
    period: str = "Current Sprint"
    goals: List[str] = []
    tasks: List[TaskCreateRequest] = []
    suggestedStudyBlocks: List[Dict[str, Any]] = []

class PlanUpdateRequest(BaseModel):
    title: Optional[str] = None
    period: Optional[str] = None
    goals: Optional[List[str]] = None
    suggestedStudyBlocks: Optional[List[Dict[str, Any]]] = None

class PlanSchema(BaseModel):
    id: str
    title: str
    period: str
    goals: List[str] = []
    tasks: List[PlanTaskSchema] = []
    suggestedStudyBlocks: List[Dict[str, Any]] = []
    createdAt: str
    updatedAt: str

# --- Integrations Schemas ---
class IntegrationInfoSchema(BaseModel):
    id: str
    provider: str
    name: str
    description: str
    category: str
    icon: str
    status: str
    scopes: List[str] = []
    accountEmail: Optional[str] = None
    errorMessage: Optional[str] = None

# --- Dashboard Overview Schema ---
class DashboardOverviewResponse(BaseModel):
    user: UserProfileResponse
    todayAgenda: List[CalendarEventSchema] = []
    importantEmails: List[EmailMessageSchema] = []
    recentDocuments: List[KnowledgeDocumentSchema] = []
    pendingActions: List[SuggestedActionSchema] = []
    integrationsStatus: Dict[str, str] = {}
    systemStats: Dict[str, Any] = {}

# --- Structured Timetable & Academic Calendar Schemas ---
class TimetableMetadata(BaseModel):
    institution: Optional[str] = None
    department: Optional[str] = None
    class_name: Optional[str] = None
    academic_year: Optional[str] = None
    semester: Optional[str] = None
    section: Optional[str] = None

class TimeSlotItem(BaseModel):
    start_time: str
    end_time: str
    label: Optional[str] = None

class SubjectReferenceItem(BaseModel):
    code: str
    name: Optional[str] = None
    faculty: Optional[str] = None
    room: Optional[str] = None
    class_type: Optional[str] = None

class TimetableEntryItem(BaseModel):
    id: Optional[str] = None
    day_of_week: str = Field(..., description="Day of the week (Monday, Tuesday, etc.)")
    subject_name: str = Field(..., description="Name of the course or subject")
    subject_code: Optional[str] = Field(None, description="Course code or subject identifier")
    start_time: str = Field(..., description="Class start time in 12h or 24h format (e.g. 09:00 AM or 09:00)")
    end_time: str = Field(..., description="Class end time in 12h or 24h format (e.g. 10:00 AM or 10:00)")
    room_number: Optional[str] = Field(None, description="Room number, hall, or lab")
    faculty_name: Optional[str] = Field(None, description="Instructor or professor name")
    class_type: Optional[str] = Field("Theory", description="Type of period: Theory, Lab, Practical, Tutorial, Break")
    academic_year: Optional[str] = Field(None, description="Academic year if identified")
    semester: Optional[str] = Field(None, description="Semester if identified")
    source_page: Optional[int] = Field(1, description="1-based page number")
    source_row: Optional[int] = Field(None, description="1-based row number")
    confidence: Optional[float] = Field(1.0, description="Extraction confidence score (0.0 to 1.0)")
    is_uncertain: Optional[bool] = Field(False, description="Flag indicating uncertainty or ambiguity requiring review")

class TimetableExtractionResult(BaseModel):
    document_type: str = "TIMETABLE"
    pdf_format: Optional[str] = Field("TEXT_BASED", description="TEXT_BASED, IMAGE_BASED, or MIXED")
    metadata: Optional[TimetableMetadata] = None
    time_slots: Optional[List[TimeSlotItem]] = []
    reference_table: Optional[List[SubjectReferenceItem]] = []
    entries: List[TimetableEntryItem] = []
    total_valid_entries: Optional[int] = 0
    uncertain_entries_count: Optional[int] = 0
    warnings: Optional[List[str]] = []

class AcademicEventItem(BaseModel):
    id: Optional[str] = None
    event_name: str = Field(..., description="Name of the academic activity, exam, or holiday")
    category: str = Field("OTHER", description="Category: SEMESTER, EXAM, INTERNAL_ASSESSMENT, PRACTICAL_EXAM, HOLIDAY, COLLEGE_EVENT, REGISTRATION, ACADEMIC_DEADLINE, RESULT, OTHER")
    start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    end_date: Optional[str] = Field(None, description="End date in YYYY-MM-DD format if date range, else null")
    description: Optional[str] = Field(None, description="Detailed description or notes")
    academic_year: Optional[str] = Field(None, description="Academic year if identified")
    semester: Optional[str] = Field(None, description="Semester if identified")
    source_page: Optional[int] = Field(None, description="1-based page number")
    source_row: Optional[int] = Field(None, description="1-based row number")

class AcademicCalendarExtractionResult(BaseModel):
    document_type: str = "ACADEMIC_CALENDAR"
    events: List[AcademicEventItem] = []

class DocumentConfirmRequest(BaseModel):
    document_type: Optional[str] = None
    entries: Optional[List[Dict[str, Any]]] = None
    events: Optional[List[Dict[str, Any]]] = None

# --- Manual Timetable Schemas ---
class PeriodCreateSchema(BaseModel):
    day_of_week: str = Field(..., description="Day of the week (Monday, Tuesday, etc.)")
    subject_name: str = Field(..., description="Subject or course name")
    subject_code: Optional[str] = Field(None, description="Course code")
    start_time: str = Field(..., description="Period start time (e.g. 09:00 AM)")
    end_time: str = Field(..., description="Period end time (e.g. 10:00 AM)")
    period_number: Optional[int] = Field(None, description="Period number or slot index (1, 2, 3...)")
    room: Optional[str] = Field(None, description="Room number or lab")
    faculty: Optional[str] = Field(None, description="Faculty or instructor name")
    class_type: Optional[str] = Field("Theory", description="Theory, Lab, Tutorial, Break, Other")
    notes: Optional[str] = Field(None, description="Additional notes")

class PeriodUpdateSchema(BaseModel):
    day_of_week: Optional[str] = None
    subject_name: Optional[str] = None
    subject_code: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    period_number: Optional[int] = None
    room: Optional[str] = None
    faculty: Optional[str] = None
    class_type: Optional[str] = None
    notes: Optional[str] = None

class PeriodResponseSchema(BaseModel):
    id: str
    timetable_id: str
    user_id: str
    day_of_week: str
    subject_name: str
    subject_code: Optional[str] = None
    start_time: str
    end_time: str
    period_number: Optional[int] = None
    room: Optional[str] = None
    faculty: Optional[str] = None
    class_type: Optional[str] = "Theory"
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class TimetableCreateSchema(BaseModel):
    name: str = Field("My Timetable", description="Timetable title/name")
    academic_year: Optional[str] = Field(None, description="Academic year")
    semester: Optional[str] = Field(None, description="Semester")
    section: Optional[str] = Field(None, description="Section or class")
    periods: List[PeriodCreateSchema] = []

class TimetableUpdateSchema(BaseModel):
    name: Optional[str] = None
    academic_year: Optional[str] = None
    semester: Optional[str] = None
    section: Optional[str] = None
    periods: Optional[List[PeriodCreateSchema]] = None

class TimetableResponseSchema(BaseModel):
    id: str
    user_id: str
    name: str
    academic_year: Optional[str] = None
    semester: Optional[str] = None
    section: Optional[str] = None
    periods: List[PeriodResponseSchema] = []
    created_at: datetime
    updated_at: datetime
