"""Data model for support plans, the normalized person profile and the agent's audit trail.

Kept generic on purpose: nothing here is specific to blood pressure, genetics or health care, so the same
plan / consent / escalation structure can later carry social-services use cases as well.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.wellbeing.models import WellbeingDataState

# --- PersonProfile: the internal profile every source adapter normalizes into ----------------------------

SOURCE_KINDS = (
    'diagnoses',
    'medications',
    'careEpisodes',
    'professionalNotes',
    'interactionEvents',
    'measurements',
    'selfReportedData',
    'geneticInsights',
    'wellbeingData',  # Apple Health daily summaries (Hyvinvointidata), optional like genetics
)


class Demographics(BaseModel):
    personId: str
    displayName: str
    birthYear: Optional[int] = None
    sex: Optional[str] = None
    region: Optional[str] = None
    synthetic: bool = True


class Diagnosis(BaseModel):
    id: str
    code: str
    label: str
    diagnosedAt: Optional[str] = None
    status: str = 'active'
    source: str
    synthetic: bool = True


class Medication(BaseModel):
    id: str
    name: str
    purpose: Optional[str] = None
    startedAt: Optional[str] = None
    status: str = 'active'
    source: str
    synthetic: bool = True


class CareEpisode(BaseModel):
    id: str
    date: str
    kind: str
    unit: Optional[str] = None
    professionalRole: Optional[str] = None
    summary: Optional[str] = None
    source: str
    synthetic: bool = True


class ProfessionalNote(BaseModel):
    id: str
    date: str
    authorRole: str
    text: str
    source: str
    synthetic: bool = True


class InteractionEvent(BaseModel):
    id: str
    date: str
    channel: str
    topic: str
    summary: Optional[str] = None
    source: str
    synthetic: bool = True


class Measurement(BaseModel):
    id: str
    date: str
    code: str
    label: str
    value: Any = None
    unit: Optional[str] = None
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    context: Optional[str] = None  # home | clinic | lab
    flag: Optional[str] = None  # flag given by the source system (H/L), never computed by the LLM
    source: str
    synthetic: bool = True
    # laboratory results: one order (tutkimuspyyntö) groups several results, like the lab view of Omakanta
    panelId: Optional[str] = None  # order id, e.g. LAB-2026-05-12-A
    panelName: Optional[str] = None  # e.g. "Lipidit" or "B -Perusverenkuva, minidiff, vieritutkimus"
    abbreviation: Optional[str] = None  # laboratory abbreviation, e.g. "fP -Kol-LDL"
    referenceRange: Optional[str] = None  # as printed by the lab, e.g. "< 3,0" or "117–155"
    resultText: Optional[str] = None  # the result exactly as reported (keeps "0,40" or "Negatiivinen")


class SelfReport(BaseModel):
    id: str
    date: str
    topic: str
    text: str
    source: str
    synthetic: bool = True


class GeneticInsight(BaseModel):
    id: str
    gene: Optional[str] = None
    variant: str
    significance: str
    conditions: list[str] = []
    confirmation: str = 'unconfirmed'  # unconfirmed | lab_confirmed
    findingId: Optional[str] = None  # link to a curated evidence entry (data/loop/evidence.json)
    reportedAt: Optional[str] = None
    source: str
    synthetic: bool = True


class PersonProfile(BaseModel):
    schemaVersion: str = '1.0'
    demographics: Demographics
    diagnoses: list[Diagnosis] = []
    medications: list[Medication] = []
    careEpisodes: list[CareEpisode] = []
    professionalNotes: list[ProfessionalNote] = []
    interactionEvents: list[InteractionEvent] = []
    measurements: list[Measurement] = []
    selfReportedData: list[SelfReport] = []
    geneticInsights: list[GeneticInsight] = []
    consents: list[dict[str, Any]] = []  # consent records as delivered by the source system (informational)
    activeSupportPlans: list[str] = []
    sourceSystems: list[dict[str, Any]] = []  # provenance: which adapter read which file, how many rows


# --- Gate 3: the user's consent and communication settings ------------------------------------------------

class QuietHours(BaseModel):
    start: str = '21:00'
    end: str = '08:00'


class ConsentSettings(BaseModel):
    dataSources: dict[str, bool] = Field(default_factory=lambda: {kind: True for kind in SOURCE_KINDS})
    proactiveContact: bool = True
    maxContactsPerWeek: int = 3
    quietHours: QuietHours = Field(default_factory=QuietHours)
    channel: Literal['app', 'sms', 'email'] = 'app'
    showGeneticDetails: bool = False
    pausedUntil: Optional[str] = None
    # explicit consent to the automated assessment of the need for care and its urgency (terveydenhuoltolaki 51 § 3 mom.,
    # digitaalinen hoidon tarpeen arvio - the prototype assumes the amendment enters into force in 2027)
    automatedAssessment: bool = True
    automatedAssessmentInformedAt: Optional[str] = None
    updatedAt: Optional[str] = None
    history: list[dict[str, Any]] = []


# --- Gate 1: every piece of information the system found, and what it may be used for --------------------

RelevanceCategory = Literal[
    'no_practical_significance',
    'uncertain_or_conflicting',
    'needs_professional_check',
    'potentially_actionable',
    'professionally_approved',
]
ReviewStatus = Literal['not_requested', 'pending_professional_review', 'approved', 'rejected', 'info_requested']


class SourceRef(BaseModel):
    kind: str
    id: str
    label: str
    date: Optional[str] = None


class Insight(BaseModel):
    id: str
    kind: Literal['genetic', 'health_data']
    title: str
    userTitle: str
    category: RelevanceCategory
    reason: str
    userVisible: bool
    sources: list[SourceRef] = []
    findingId: Optional[str] = None
    gene: Optional[str] = None
    variant: Optional[str] = None
    significance: Optional[str] = None
    confirmation: Optional[str] = None
    reviewStatus: ReviewStatus = 'not_requested'
    reviewOwnerRole: Optional[str] = None
    decision: Optional[dict[str, Any]] = None
    linkedPlanId: Optional[str] = None
    origin: str = 'source_record'  # source_record | dna_analysis | rules
    createdAt: str


# --- Gate 2: the professional-approved support plan --------------------------------------------------------

PlanStatus = Literal['candidate', 'pending_professional_review', 'active', 'paused', 'escalated', 'completed', 'rejected']
Urgency = Literal['routine', 'soon', 'same_day']


class Owner(BaseModel):
    role: str
    label: str


class Goal(BaseModel):
    id: str
    label: str
    activity: str
    timesPerWeek: int
    minutes: Optional[int] = None
    minTimesPerWeek: int = 1  # the smallest goal the agent may propose without a professional
    maxTimesPerWeek: int = 3
    setBy: Literal['professional', 'agent_with_user'] = 'professional'
    setAt: str


class EscalationRule(BaseModel):
    id: str
    name: str
    description: str
    kind: str
    params: dict[str, Any] = {}
    urgency: Urgency = 'routine'
    urgencyLabel: str
    handlingTime: str


class Approval(BaseModel):
    status: Literal['not_reviewed', 'approved', 'rejected', 'info_requested'] = 'not_reviewed'
    byRole: Optional[str] = None
    at: Optional[str] = None
    note: Optional[str] = None


class UserConsent(BaseModel):
    given: bool = False
    at: Optional[str] = None
    how: Optional[str] = None


class PlanChange(BaseModel):
    version: int
    date: str
    actor: Literal['system', 'professional', 'agent', 'user']
    actorRole: Optional[str] = None
    summary: str
    changes: list[str] = []


class SupportPlan(BaseModel):
    id: str
    theme: str
    name: str
    status: PlanStatus
    priority: Literal['low', 'normal', 'high'] = 'normal'
    rationale: str
    objective: str
    sources: list[SourceRef] = []
    observationDates: list[str] = []
    measurementCode: Optional[str] = None
    measurementsPerWeek: int = 0
    checkInEveryDays: int = 7
    demoTarget: Optional[dict[str, Any]] = None
    goal: Optional[Goal] = None
    signals: list[dict[str, Any]] = []
    allowedActions: list[str] = []
    forbiddenActions: list[str] = []
    microInterventions: list[str] = []
    guides: list[str] = []
    escalationRules: list[EscalationRule] = []
    owner: Owner
    approval: Approval = Field(default_factory=Approval)
    userConsent: UserConsent = Field(default_factory=UserConsent)
    nextReviewAt: Optional[str] = None
    nextCheckInAt: Optional[str] = None
    activatedAt: Optional[str] = None
    pausedUntil: Optional[str] = None
    lastAgentAction: Optional[dict[str, Any]] = None
    lastProfessionalDecision: Optional[dict[str, Any]] = None
    version: int = 1
    history: list[PlanChange] = []
    linkedFindingIds: list[str] = []  # genetic findings a professional approved as background for this plan
    professionalInstructions: list[str] = []  # plain-language instructions from the latest professional decision
    checkInBaselineSeq: int = 0  # check-ins up to this seq were already reviewed by a professional (not re-counted)
    createdAt: str
    updatedAt: Optional[str] = None
    demoPolicy: bool = True


# --- Micro-interventions (adaptive check-ins) -----------------------------------------------------------------

class CheckInOption(BaseModel):
    id: str
    label: str


class CheckInQuestion(BaseModel):
    id: str
    kind: str
    text: str
    whyAsked: str
    options: list[CheckInOption]
    optional: bool = False
    answer: Optional[str] = None
    answerLabel: Optional[str] = None
    answeredAt: Optional[str] = None
    skipped: bool = False
    context: dict[str, Any] = {}


class CheckIn(BaseModel):
    id: str
    seq: int = 0  # creation order; decisions reset evaluation from a given seq onwards
    planId: str
    planVersion: int
    chainId: str
    createdAt: str
    deliveredAt: str
    channel: str
    status: Literal['open', 'completed', 'cancelled'] = 'open'
    reason: str
    signals: list[str] = []
    questions: list[CheckInQuestion] = []
    outcome: dict[str, Any] = {}
    closingMessage: Optional[str] = None


# --- Structured escalation to a professional ---------------------------------------------------------------------

class Escalation(BaseModel):
    id: str
    planId: str
    planVersion: int
    chainId: str
    createdAt: str
    status: Literal['open', 'resolved'] = 'open'
    trigger: Literal['rule', 'safety_threshold', 'user_request'] = 'rule'
    urgency: Urgency = 'routine'
    urgencyLabel: str
    handlingTime: str
    ownerRole: str
    reason: str
    observedChange: list[str] = []
    timeline: list[dict[str, Any]] = []
    sources: list[SourceRef] = []
    rulesApplied: list[dict[str, Any]] = []
    agentActions: list[dict[str, Any]] = []
    userResponses: list[dict[str, Any]] = []
    openDecision: str
    summaryText: str
    summarySource: Literal['llm', 'template'] = 'template'
    resolvedAt: Optional[str] = None
    decision: Optional[dict[str, Any]] = None
    appropriate: Optional[bool] = None
    assessmentId: Optional[str] = None  # the automated care-need assessment this routing is based on
    humanReviewRequested: bool = False  # the user exercised the right to an assessment made by a professional


# --- Automated assessment of the need for care and its urgency (hoidon tarpeen ja kiireellisyyden arvio) -----------

AssessmentUrgency = Literal['emergency', 'same_day', 'within_3_days', 'routine', 'self_care']
AssessmentStatus = Literal['issued', 'confirmed', 'changed', 'human_review_requested', 'human_reviewed']


class CareAssessment(BaseModel):
    """One automated (rule-based) assessment. The LLM never sets the class; a professional confirms, changes or
    replaces it, and the user can always ask for an assessment made by a professional."""
    id: str
    planId: Optional[str] = None
    planVersion: Optional[int] = None
    chainId: Optional[str] = None
    createdAt: str
    trigger: Literal['rule', 'safety_threshold', 'user_request', 'symptom_report', 'check_in']
    # professional_required when consent.automatedAssessment is False; excluded_emergency for 112 cases
    mode: Literal['automated', 'professional_required', 'excluded_emergency'] = 'automated'
    urgency: AssessmentUrgency
    urgencyLabel: str
    careNeed: str
    careNeedLabel: str
    handlingTime: str
    reason: str  # one sentence, deterministic
    basis: list[str] = []  # facts used (masked, no gene names when hidden)
    rulesApplied: list[dict[str, Any]] = []  # {id, name, description}
    sources: list[SourceRef] = []
    symptoms: list[str] = []  # matched symptom keywords (symptom_report)
    llmUsed: bool = False
    status: AssessmentStatus = 'issued'
    escalationId: Optional[str] = None
    humanReviewRequestedAt: Optional[str] = None
    professionalReview: Optional[dict[str, Any]] = None  # {decision, label, byRole, date, note, newUrgency, newUrgencyLabel}
    legalNotice: str
    userNotified: bool = True


# --- The self-care continuity engine: a short home monitoring period the agent offers on its own --------------------

class HomeMonitoringPeriod(BaseModel):
    """A short home monitoring period (e.g. three days, morning and evening) that the agent offers on its own when an
    outreach rule of the plan holds. The user decides whether to start it; the result is read with the plan's rules
    (continue self-care / change the plan / a professional is needed)."""
    id: str
    planId: str
    planVersion: int
    chainId: str
    ruleId: str
    status: Literal['offered', 'active', 'completed', 'declined', 'expired'] = 'offered'
    offeredAt: str
    reason: str  # the observed change behind the offer, e.g. the rise of the home readings' average
    days: int = 3
    perDay: int = 2
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    respondedAt: Optional[str] = None
    readingIds: list[str] = []  # home readings recorded while the period was active
    completedAt: Optional[str] = None
    result: dict[str, Any] = {}  # {average: {systolic, diastolic, n}, direction, ruleId, complete}


# --- Audit trail -------------------------------------------------------------------------------------------------------

AuditStage = Literal[
    'data', 'gate', 'observe', 'compare', 'detect', 'decide', 'act', 'wait', 'evaluate', 'update', 'assess', 'escalate',
    'professional_decision', 'consent',
]


class AuditEntry(BaseModel):
    id: str
    seq: int
    date: str
    personId: Optional[str] = None
    planId: Optional[str] = None
    planVersion: Optional[int] = None
    chainId: Optional[str] = None
    stage: AuditStage
    actor: Literal['agent', 'user', 'professional', 'system']
    signal: Optional[dict[str, Any]] = None
    rule: Optional[dict[str, Any]] = None
    action: Optional[str] = None
    detail: str
    llmUsed: bool = False
    llmTask: Optional[str] = None
    outcome: Optional[str] = None
    userResponse: Optional[str] = None
    escalated: bool = False
    professionalDecision: Optional[str] = None


# --- Linking health records to DNA-analysis findings (on the user's request, deterministic) --------------------------

class GeneticLinkFinding(BaseModel):
    key: str  # GENE:rsid, so the same variant from the source record and the user's own DNA analysis is one finding
    gene: Optional[str] = None
    variant: Optional[str] = None
    conditions: list[str] = []  # translated conditions that belong to the theme (never e.g. Alzheimer under cholesterol)
    significanceLabel: Optional[str] = None
    origin: str  # source_record | dna_analysis
    insightId: Optional[str] = None
    category: str  # gate 1 category
    statusLabel: str  # e.g. "Hyväksytty seurannan taustatiedoksi (Kolesteroliarvojen seuranta)"
    used: bool  # True only for a professional-approved finding the user allows to be used (gates 2 and 3)


class GeneticLinkTheme(BaseModel):
    id: str
    label: str  # e.g. "Kohonnut kolesteroli"
    reason: str
    eventIds: list[str]  # the linked health care records (timeline events)
    recordCount: int  # as the Terveystiedot view shows them: one lab order or one visit with its notes = one record
    findings: list[GeneticLinkFinding]
    planId: Optional[str] = None
    planName: Optional[str] = None


class GeneticLinking(BaseModel):
    linkedAt: str
    sessionId: Optional[str] = None  # the user's own DNA analysis, when it was run
    themes: list[GeneticLinkTheme] = []  # themes with both health records and DNA findings
    healthOnlyThemes: list[str] = []  # themes with health records but no DNA finding (e.g. blood pressure)
    findingCount: int = 0
    unlinkedFindingCount: int = 0  # DNA findings with no related health records: not linked, not named


class SupportState(BaseModel):
    person: Optional[PersonProfile] = None
    consent: ConsentSettings = Field(default_factory=ConsentSettings)
    plans: list[SupportPlan] = []
    insights: list[Insight] = []
    checkIns: list[CheckIn] = []
    escalations: list[Escalation] = []
    assessments: list[CareAssessment] = []
    audit: list[AuditEntry] = []
    contacts: list[dict[str, Any]] = []  # agent-initiated contacts, for the weekly contact limit and metrics
    feedback: list[dict[str, Any]] = []  # the user's own rating of how useful the support was
    scriptCursor: dict[str, int] = {}  # position in scripted demo sequences (measurements etc.)
    geneticLinking: Optional[GeneticLinking] = None  # health records linked to DNA findings (Terveystiedot)
    homeMonitoring: list[HomeMonitoringPeriod] = []  # home monitoring periods the agent offered (continuity engine)
    wellbeing: WellbeingDataState = Field(default_factory=WellbeingDataState)  # Hyvinvointidata (Apple Health)
    lastCycleAt: Optional[str] = None
