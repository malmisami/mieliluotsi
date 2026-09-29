from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.support.models import SupportState

# Bump when the demo state layout changes; an older state file is then rebuilt from the demo data.
STATE_VERSION = '2.0'

ConfirmationStatus = Literal['raw_candidate', 'synthetic_demo_confirmed', 'professionally_confirmed']
MONITORABLE_STATUSES: set[str] = {'synthetic_demo_confirmed', 'professionally_confirmed'}

AgentState = Literal[
    'monitoring',
    'no_action',
    'additional_information_needed',
    'professional_review_recommended',
    'waiting_for_user',
    'waiting_for_professional_review',
    'resolved',
    'dismissed',
]
OPEN_OBSERVATION_STATES: set[str] = {
    'additional_information_needed',
    'professional_review_recommended',
    'waiting_for_user',
    'waiting_for_professional_review',
}

AbnormalFlag = Literal['high', 'low', 'normal', 'unknown']
TaskStatus = Literal['open', 'awaiting_response', 'completed', 'cancelled']
UserResponse = Literal['yes', 'not_yet', 'no_reminder', 'not_relevant']


class GenomicFinding(BaseModel):
    id: str
    gene: str | None
    variant: str
    title: str
    description: str
    classification: str
    confirmationStatus: ConfirmationStatus
    evidenceLevel: str
    monitoringEligible: bool
    relevantEventTypes: list[str] = []
    source: str
    lastReviewedAt: str | None = None
    synthetic: bool = True
    relatedConditions: list[str] = []
    healthArea: str | None = None


class HealthEvent(BaseModel):
    id: str
    date: str
    type: str
    code: str | None = None
    displayName: str
    value: str | float | None = None
    unit: str | None = None
    abnormalFlag: AbnormalFlag | None = None
    source: str
    rawText: str | None = None
    extractedData: dict[str, Any] = {}
    structuredData: dict[str, Any] = {}
    confirmedByUser: bool = False
    synthetic: bool = True


class Monitoring(BaseModel):
    id: str
    findingId: str
    active: bool = True
    status: AgentState = 'monitoring'
    consentedAt: str
    nextReviewAt: str
    lastRelevantEventId: str | None = None
    currentAssessment: str
    openObservationId: str | None = None
    stoppedAt: str | None = None


class Observation(BaseModel):
    id: str
    monitoringId: str
    findingId: str
    eventId: str
    ruleId: str
    status: AgentState
    createdAt: str
    title: str
    explanation: str
    explanationSource: Literal['llm', 'template']
    connection: str
    missingInformation: list[str] = []
    systemDid: list[str] = []
    systemDidNot: list[str] = []
    sharedAt: str | None = None
    remindersDisabled: bool = False
    summaryIntro: str | None = None
    summaryIntroSource: Literal['llm', 'template'] | None = None
    ruleIds: list[str] = []
    supportingEventIds: list[str] = []
    updatedAt: str | None = None
    summaryCreatedAt: str | None = None


class FollowUpTask(BaseModel):
    id: str
    observationId: str
    createdAt: str
    dueAt: str
    status: TaskStatus = 'open'
    userResponse: UserResponse | None = None


class AgentLogEntry(BaseModel):
    id: str
    date: str
    kind: str
    detectedEvent: dict[str, Any] | None = None
    extractedData: dict[str, Any] | None = None
    extractionMethod: str | None = None
    watchlistMatches: list[dict[str, Any]] = []
    ruleApplied: dict[str, Any] | None = None
    evidenceCheck: dict[str, Any] | None = None
    safetyCheck: dict[str, Any] | None = None
    decision: str
    decisionDetail: str
    userVisibleAlert: bool = False
    userApprovalStatus: str = 'not_required'


class MissingInformation(BaseModel):
    id: str
    relatedFinding: str
    type: str
    label: str
    question: str | None = None
    askable: bool = False
    status: Literal['missing', 'answered', 'declined'] = 'missing'
    answeredByEventId: str | None = None


# --- Hyvinvointikumppani (companion chat) -------------------------------------

Intent = Literal[
    'EXPLAIN_FINDING',
    'EXPLAIN_OBSERVATION',
    'GET_STATUS',
    'ADD_CONTEXT',
    'CREATE_SUMMARY',
    'CREATE_FOLLOWUP',
    'RESOLVE_TASK',
    'GENERAL_HEALTH_QUESTION',
    'DIAGNOSIS_REQUEST',
    'MEDICATION_CHANGE_REQUEST',
    'EMERGENCY_OR_URGENT',
    'CARE_NEED_ASSESSMENT',
    'HUMAN_ASSESSMENT_REQUEST',
]


class ChatAction(BaseModel):
    id: str
    label: str
    type: str
    args: dict[str, Any] = {}
    used: bool = False
    style: Literal['primary', 'secondary'] = 'primary'


class ChatMessage(BaseModel):
    id: str
    role: Literal['agent', 'user']
    kind: str = 'text'
    text: str
    date: str
    initiatedByAgent: bool = False
    intent: str | None = None
    actions: list[ChatAction] = []
    basis: dict[str, Any] | None = None
    whyNowObservationId: str | None = None
    summaryObservationId: str | None = None
    pendingActionId: str | None = None
    textSource: Literal['llm', 'template', 'fixed'] = 'template'
    aiUnavailable: bool = False
    assessment: Optional[dict] = None  # {id, urgency, urgencyLabel} when the message carries an automated care-need assessment


class PendingAction(BaseModel):
    id: str
    type: Literal['save_context', 'create_summary', 'create_followup', 'resolve_observation']
    payload: dict[str, Any] = {}
    status: Literal['pending', 'confirmed', 'cancelled'] = 'pending'
    createdAt: str
    messageId: str | None = None


class ChatLogEntry(BaseModel):
    id: str
    date: str
    userMessage: str | None = None
    trigger: str
    intent: str | None = None
    intentMethod: str | None = None
    contextUsed: list[str] = []
    extraction: dict[str, Any] | None = None
    userConfirmation: str = 'not_required'
    toolInvoked: str | None = None
    ruleApplied: list[dict[str, Any]] = []
    safetyCheck: dict[str, Any] | None = None
    finalState: str | None = None
    llmRole: str = 'none'


class LoopState(BaseModel):
    version: str = STATE_VERSION
    synthetic: bool = True
    profile: dict[str, Any]
    currentDate: str
    findings: list[GenomicFinding] = []
    monitorings: list[Monitoring] = []
    events: list[HealthEvent] = []
    observations: list[Observation] = []
    tasks: list[FollowUpTask] = []
    agentLog: list[AgentLogEntry] = []
    missingInformation: list[MissingInformation] = []
    chatMessages: list[ChatMessage] = []
    pendingActions: list[PendingAction] = []
    chatLog: list[ChatLogEntry] = []
    proactiveKeys: list[str] = []
    awaitingMissingInfoId: str | None = None
    counters: dict[str, int] = Field(default_factory=dict)
    support: SupportState = Field(default_factory=SupportState)
