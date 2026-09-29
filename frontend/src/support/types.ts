import type { WellbeingDashboardBlock } from '../wellbeing/types';

// Types for the support-plan layer (backend: app/support/view.py). All data is synthetic.

export type PlanStatus =
  | 'candidate'
  | 'pending_professional_review'
  | 'active'
  | 'paused'
  | 'escalated'
  | 'completed'
  | 'rejected';

export type RelevanceCategory =
  | 'no_practical_significance'
  | 'uncertain_or_conflicting'
  | 'needs_professional_check'
  | 'potentially_actionable'
  | 'professionally_approved';

export type ReviewStatus = 'not_requested' | 'pending_professional_review' | 'approved' | 'rejected' | 'info_requested';
export type Urgency = 'routine' | 'soon' | 'same_day';
/** Urgency class of the automated care-need assessment (always set by the rule engine, never by the LLM). */
export type AssessmentUrgency = 'emergency' | 'same_day' | 'within_3_days' | 'routine' | 'self_care';
export type AssessmentStatus = 'issued' | 'confirmed' | 'changed' | 'human_review_requested' | 'human_reviewed';
export type AssessmentMode = 'automated' | 'professional_required' | 'excluded_emergency';
export type AssessmentDecision = 'confirm' | 'change_urgency' | 'take_over';
export type Tone = 'calm' | 'attention' | 'waiting' | 'urgent' | 'neutral';

export interface SourceRef {
  kind: string;
  id: string;
  label: string;
  date: string | null;
}

export interface SourceDetail extends SourceRef {
  kindLabel: string;
  inUse: boolean;
}

export interface Goal {
  id: string;
  label: string;
  activity: string;
  timesPerWeek: number;
  minutes: number | null;
  minTimesPerWeek: number;
  maxTimesPerWeek: number;
  setBy: 'professional' | 'agent_with_user';
  setAt: string;
}

export interface EscalationRule {
  id: string;
  name: string;
  description: string;
  kind: string;
  params: Record<string, unknown>;
  urgency: Urgency;
  urgencyLabel: string;
  handlingTime: string;
}

export interface PlanChange {
  version: number;
  date: string;
  actor: 'system' | 'professional' | 'agent' | 'user';
  actorRole: string | null;
  summary: string;
  changes: string[];
}

export interface CheckInOption {
  id: string;
  label: string;
}

export interface CheckInQuestion {
  id: string;
  kind: string;
  text: string;
  whyAsked: string;
  options: CheckInOption[];
  optional: boolean;
  answer: string | null;
  answerLabel: string | null;
  answeredAt: string | null;
  skipped: boolean;
  context: Record<string, unknown>;
}

export interface CheckIn {
  id: string;
  seq: number;
  planId: string;
  planVersion: number;
  chainId: string;
  createdAt: string;
  deliveredAt: string;
  channel: string;
  status: 'open' | 'completed' | 'cancelled';
  reason: string;
  signals: string[];
  questions: CheckInQuestion[];
  outcome: Record<string, unknown>;
  closingMessage: string | null;
}

export interface AuditEntry {
  id: string;
  seq: number;
  date: string;
  personId: string | null;
  planId: string | null;
  planVersion: number | null;
  chainId: string | null;
  stage: string;
  stageLabel: string;
  actor: 'agent' | 'user' | 'professional' | 'system';
  signal: Record<string, unknown> | null;
  rule: { id?: string; name?: string } | null;
  action: string | null;
  detail: string;
  detailMasked: string;
  llmUsed: boolean;
  llmTask: string | null;
  outcome: string | null;
  userResponse: string | null;
  escalated: boolean;
  professionalDecision: string | null;
}

export interface SignalResult {
  id: string;
  kind: string;
  label: string;
  detected: boolean;
  key: string | null;
  detail: string;
}

export interface SupportPlan {
  id: string;
  theme: string;
  name: string;
  status: PlanStatus;
  statusLabel: string;
  priority: 'low' | 'normal' | 'high';
  rationale: string;
  objective: string;
  sources: SourceRef[];
  sourceDetails: SourceDetail[];
  observationDates: string[];
  measurementCode: string | null;
  measurementsPerWeek: number;
  checkInEveryDays: number;
  demoTarget: { systolic: number; diastolic: number; label: string; setBy: string } | null;
  goal: Goal | null;
  signals: { id: string; kind: string; label: string; params: Record<string, unknown> }[];
  allowedActions: string[];
  forbiddenActions: string[];
  allowedActionLabels: Record<string, string>;
  forbiddenActionLabels: Record<string, string>;
  microInterventions: string[];
  guides: string[];
  escalationRules: EscalationRule[];
  owner: { role: string; label: string };
  approval: { status: string; byRole: string | null; at: string | null; note: string | null };
  userConsent: { given: boolean; at: string | null; how: string | null };
  nextReviewAt: string | null;
  nextCheckInAt: string | null;
  activatedAt: string | null;
  pausedUntil: string | null;
  lastAgentAction: { date: string; action: string; label: string; detail: string } | null;
  lastProfessionalDecision: { decision: string; label: string; byRole: string; date: string; note: string | null; version: number; changes: string[] } | null;
  version: number;
  history: PlanChange[];
  linkedFindingIds: string[];
  professionalInstructions: string[];
  createdAt: string;
  currentSignals: { key: string; label: string }[];
  signalDetails: SignalResult[];
  metrics: Record<string, unknown>;
  checkIns: CheckIn[];
  agentActions: AuditEntry[];
  /** Automated assessments made within this plan, newest first. */
  assessmentIds: string[];
}

export interface Escalation {
  id: string;
  planId: string;
  planVersion: number;
  chainId: string;
  createdAt: string;
  status: 'open' | 'resolved';
  trigger: 'rule' | 'safety_threshold' | 'user_request';
  urgency: Urgency;
  urgencyLabel: string;
  handlingTime: string;
  ownerRole: string;
  reason: string;
  observedChange: string[];
  timeline: { date: string; text: string }[];
  sources: SourceRef[];
  rulesApplied: { id: string; name: string; description: string }[];
  agentActions: { date: string; text: string }[];
  userResponses: { date: string | null; question: string; answer: string }[];
  openDecision: string;
  summaryText: string;
  summarySource: 'llm' | 'template';
  resolvedAt: string | null;
  decision: { label: string; byRole: string; date: string; note: string | null; appropriate: boolean | null } | null;
  appropriate: boolean | null;
  /** The automated care-need assessment this routing is based on. */
  assessmentId: string | null;
  /** The user exercised the right to an assessment made by a professional. */
  humanReviewRequested: boolean;
}

export interface AssessmentProfessionalReview {
  decision: AssessmentDecision;
  label: string;
  byRole: string;
  date: string;
  note: string | null;
  newUrgency: AssessmentUrgency | null;
  newUrgencyLabel: string | null;
}

/** One automated assessment of the need for care and its urgency (backend: support/assessment.py view()). */
export interface CareAssessment {
  id: string;
  planId: string | null;
  planVersion: number | null;
  chainId: string | null;
  createdAt: string;
  trigger: 'rule' | 'safety_threshold' | 'user_request' | 'symptom_report' | 'check_in';
  mode: AssessmentMode;
  modeLabel: string;
  urgency: AssessmentUrgency;
  urgencyLabel: string;
  careNeed: string;
  careNeedLabel: string;
  handlingTime: string;
  reason: string;
  basis: string[];
  rulesApplied: { id: string; name: string; description: string }[];
  sources: SourceRef[];
  symptoms: string[];
  llmUsed: boolean;
  status: AssessmentStatus;
  statusLabel: string;
  escalationId: string | null;
  humanReviewRequestedAt: string | null;
  professionalReview: AssessmentProfessionalReview | null;
  legalNotice: string;
  userNotified: boolean;
  canRequestHuman: boolean;
  rightsSentence: string;
  responsiblePerson: string | null;
  automationVersion: string | null;
}

export interface UrgencyClass {
  id: AssessmentUrgency;
  label: string;
  careNeed: string;
  careNeedLabel: string;
  handlingTime: string;
}

/** Published description of the automation (policies.json `automation`). */
export interface AutomationPolicy {
  name: string;
  legalBasis: string;
  responsiblePerson: string;
  version: string;
  principles: string[];
  urgencyClasses: UrgencyClass[];
  symptomRules: { id: string; name: string; urgency: AssessmentUrgency; reason: string; patterns: string[]; default: boolean }[];
  contextRules: { id: string; description: string }[];
  sampling: { reviewShare?: number; description?: string };
  whatStaysHuman: string[];
  rightsSentence: string;
  legalNotice: string;
}

export interface Insight {
  id: string;
  kind: 'genetic' | 'health_data';
  title: string;
  userTitle: string;
  category: RelevanceCategory;
  categoryLabel: string;
  reason: string;
  userVisible: boolean;
  sources: SourceRef[];
  findingId: string | null;
  gene: string | null;
  variant: string | null;
  significance: string | null;
  confirmation: string | null;
  reviewStatus: ReviewStatus;
  reviewStatusLabel: string;
  reviewOwnerRole: string | null;
  reviewOwnerLabel: string | null;
  decision: { label: string; byRole: string; date: string; note: string | null } | null;
  linkedPlanId: string | null;
  origin: string;
  createdAt: string;
  inUse: boolean;
}

export interface PlanCard {
  id: string;
  name: string;
  status: PlanStatus;
  statusLabel: string;
  tone: Tone;
  sentence: string;
  progress: { label: string; value: number; target: number }[];
  goal: string | null;
  goalSetBy: string | null;
  nextCheckInAt: string | null;
  nextReviewAt: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  version: number;
  instructions: string[];
  canPause: boolean;
  canResume: boolean;
  why: {
    rationale: string;
    objective: string;
    sources: { label: string; date: string | null; kind: string; kindLabel: string; inUse: boolean }[];
    approval: string;
    owner: string;
    userConsent: string;
    target: { label: string; setBy: string } | null;
    agentMay: string[];
    agentMayNot: string[];
    escalationRules: { name: string; urgency: string; handlingTime: string }[];
    rightsSentence?: string;
    history: PlanChange[];
    geneticNote: string | null;
    filteredNote: string | null;
    demoNotice: string;
  };
}

export interface NextStep {
  kind: 'safety' | 'answer_checkin' | 'answer_offer' | 'legacy_followup' | 'record_measurement' | 'instructions' | 'wait' | 'none';
  title: string;
  detail: string;
  checkInId?: string;
  planId?: string;
  /** The home monitoring period the agent offered (answer_offer) or the one in progress (record_measurement). */
  periodId?: string;
}

export interface Situation {
  available: boolean;
  headline: string;
  tone: Tone;
  noImmediateAction: boolean;
  nextStep: NextStep;
  plans: PlanCard[];
  latestProgress: string[];
  nextCheck: string | null;
  legacyOpenObservationIds: string[];
  legacyObservations: { id: string; title: string; status: string; createdAt: string; explanation: string; sharedAt: string | null }[];
  safetyEscalationId: string | null;
  /** The newest automated assessment still under the professional's oversight. */
  assessment: CareAssessment | null;
  whatStaysHuman: string[];
}

export interface ConsentView {
  dataSources: Record<string, boolean>;
  proactiveContact: boolean;
  maxContactsPerWeek: number;
  quietHours: { start: string; end: string };
  channel: 'app' | 'sms' | 'email';
  showGeneticDetails: boolean;
  pausedUntil: string | null;
  automatedAssessment: boolean;
  automatedAssessmentInformedAt: string | null;
  updatedAt: string | null;
  history: { date: string; change: string }[];
  sourceLabels: Record<string, string>;
  channelLabels: Record<string, string>;
  deliveryTime: string;
  contactsLastWeek: number;
  records: { id: string; date: string | null; target: string; status: string; channel: string }[];
}

export interface ImpactMetrics {
  synthetic: true;
  activePlans: number;
  selfCareTasksDone: number;
  selfCareTasksAgreed: number;
  reminders: number;
  microInterventions: number;
  adaptiveFollowUps: number;
  goalAdjustments: number;
  escalations: number;
  escalationsAppropriate: number;
  escalationsDecided: number;
  resolvedWithoutEscalation: number;
  avgDaysSignalToAction: number | null;
  waitingForProfessional: number;
  usefulnessAvg: number | null;
  usefulnessAnswers: number;
  assessments: number;
  assessmentsAutomated: number;
  assessmentsConfirmed: number;
  assessmentsChanged: number;
  humanReviewRequests: number;
  assessmentsByUrgency: Partial<Record<AssessmentUrgency, number>>;
  avgMinutesToAssessment: number | null;
}

export interface CohortAggregate {
  synthetic: true;
  people: number;
  activePlans: number;
  selfCareTasksAgreed: number;
  selfCareTasksDone: number;
  reminders: number;
  microInterventions: number;
  escalations: number;
  escalationsAppropriate: number;
  resolvedWithoutEscalation: number;
  avgDaysSignalToAction: number;
  waitingForProfessional: number;
  usefulnessAvg: number | null;
  usefulnessAnswers: number;
  assessments: number;
  assessmentsConfirmed: number;
  assessmentsConfirmedShare: number | null;
  humanReviewRequests: number;
  byStatus: { status: string; label: string; count: number }[];
  byTheme: { theme: string; count: number }[];
}

export interface CohortRow {
  id: string;
  ageBand: string;
  themes: string[];
  status: string;
  statusLabel: string;
  tasksAgreed: number;
  tasksDone: number;
  escalations: number;
  waitingForProfessional: boolean;
  assessments: number;
  humanReviewRequests: number;
}

export interface CohortPage {
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  rows: CohortRow[];
  filters: { statuses: Record<string, string>; themes: string[]; ageBands: string[] };
  synthetic: true;
}

export type FlowStepKey = 'signal' | 'agent' | 'user' | 'follow' | 'assessment' | 'escalation' | 'professional';

export interface AuditChain {
  id: string;
  planId: string | null;
  plan: string | null;
  date: string;
  entries: number;
  /** Always the seven steps of FLOW_STEPS, in order. */
  flow: { key: FlowStepKey; label: string; date?: string; text?: string }[];
}

/** A DNA finding linked to a health theme; gene names and conditions only with the user's permission. */
export interface GeneticLinkFinding {
  key: string;
  label: string;
  variant: string | null;
  conditions: string[];
  significanceLabel: string | null;
  originLabel: string;
  statusLabel: string;
  /** Only a professional-approved finding the user allows to be used may act as background information. */
  used: boolean;
}

export interface GeneticLinkTheme {
  id: string;
  label: string;
  reason: string;
  eventIds: string[];
  recordCount: number;
  planId: string | null;
  planName: string | null;
  findings: GeneticLinkFinding[];
  /** The specific measurements the DNA findings relate to (e.g. LDL-kolesteroli), one series each, oldest first. */
  keyMeasurements: {
    code: string;
    label: string;
    unit: string | null;
    referenceRange: string | null;
    values: { eventId: string; date: string; value: string; flag: 'high' | 'low' | null }[];
  }[];
}

/** Health records linked to DNA-analysis findings by health theme (rules only, on the user's request). */
export interface GeneticLinkingView {
  linkedAt: string;
  suspended: boolean;
  themes: GeneticLinkTheme[];
  healthOnlyThemes: string[];
  findingCount: number;
  unlinkedFindingCount: number;
  note: string;
}

// --- The self-care continuity engine: remember, reach out, one step at a time, notice when self-care is not enough ---

export type ContinuityTone = 'positive' | 'barrier' | 'neutral' | 'attention';

export interface ContinuityItem {
  text: string;
  detail: string | null;
  source: string | null;
  date: string | null;
  origin: 'plan' | 'record' | 'agent' | 'user';
  tone: ContinuityTone | null;
  /** From a plan that still waits for the professional's approval. */
  pending: boolean;
}

export type MemorySectionKey = 'goals' | 'agreed' | 'monitor' | 'tried' | 'works' | 'recheck';

export interface MemorySection {
  key: MemorySectionKey;
  title: string;
  items: ContinuityItem[];
  empty: string;
}

export type LoopStageId = 'goal' | 'action' | 'feedback' | 'adaptation' | 'next';

export interface LoopStage {
  id: LoopStageId;
  label: string;
  text: string;
  state: 'done' | 'current' | 'upcoming';
}

export interface StepRound {
  date: string;
  checkInId: string;
  planVersion: number;
  step: string;
  feedback: 'met' | 'partial' | 'none';
  feedbackLabel: string;
  tone: ContinuityTone | null;
  barrier: string | null;
  adaptation: 'bigger' | 'smaller' | 'same' | 'professional';
  adaptationLabel: string;
}

export interface ContinuityStep {
  planId: string;
  planName: string;
  status: PlanStatus;
  /** The one thing for seven days, e.g. "30 minuutin kävely kolme kertaa". */
  text: string;
  goalLabel: string;
  startedAt: string | null;
  endsAt: string | null;
  feedbackAt: string | null;
  day: number | null;
  days: number;
  stage: LoopStageId;
  setBy: 'professional' | 'agent_with_user';
  setByLabel: string;
  range: string;
  target: string;
  loop: LoopStage[];
  rounds: StepRound[];
}

export type DirectionKey = 'continue' | 'adjust' | 'professional' | 'pending' | 'paused';

export interface ContinuityDirection {
  planId: string;
  planName: string;
  key: DirectionKey;
  label: string;
  detail: string;
  reasons: string[];
  watch: { label: string; ok: boolean; detail: string }[];
  professionalWhen: { id: string; text: string }[];
  nextEvaluation: string | null;
}

export interface HomeMonitoringPeriod {
  id: string;
  planId: string;
  planVersion: number;
  chainId: string;
  ruleId: string;
  status: 'offered' | 'active' | 'completed' | 'declined' | 'expired';
  offeredAt: string;
  reason: string;
  days: number;
  perDay: number;
  startsAt: string | null;
  endsAt: string | null;
  respondedAt: string | null;
  readingIds: string[];
  completedAt: string | null;
  result: {
    average?: { systolic: number; diastolic: number; n: number } | null;
    direction?: 'continue' | 'adjust' | 'professional' | 'incomplete';
    total?: number;
    complete?: boolean;
  };
  total: number;
  readings: number;
  title: string;
}

export interface ContinuityOutreach {
  recent: { date: string; kind: string; label: string }[];
  upcoming: { date: string; label: string }[];
  rules: { id: string; text: string }[];
  offer: HomeMonitoringPeriod | null;
  active: HomeMonitoringPeriod | null;
  settings: { proactive: boolean; channel: string; maxPerWeek: number; usedThisWeek: number; quietHours: string; pausedUntil: string | null };
}

export interface ContinuityView {
  available: boolean;
  name?: string;
  tagline?: string;
  coreTasks?: { id: 'remember' | 'reach_out' | 'one_step' | 'notice'; title: string; text: string }[];
  memory?: { sections: MemorySection[]; notesAllowed: boolean; notesNotice: string | null; notice: string | null };
  outreach?: ContinuityOutreach;
  step?: ContinuityStep | null;
  steps?: ContinuityStep[];
  direction?: ContinuityDirection | null;
  directions?: ContinuityDirection[];
  homeMonitoring?: { offer: HomeMonitoringPeriod | null; active: HomeMonitoringPeriod | null; latest: HomeMonitoringPeriod | null };
}

export interface SupportView {
  available: boolean;
  currentDate: string;
  person: { id: string; name: string; age: number | null; region: string | null; sourceSystems: { adapter: string; file: string; rows: number; rowsRead?: number; chunks?: number }[] };
  situation: Situation;
  /** The self-care continuity engine (omahoidon jatkuvuuden moottori). */
  continuity: ContinuityView;
  /** Hyvinvointidata (Apple Health): connection and new observations; the trends load from /api/health/summary. */
  wellbeing: WellbeingDashboardBlock;
  plans: SupportPlan[];
  openCheckIns: CheckIn[];
  escalations: Escalation[];
  /** Every automated care-need assessment, newest first. */
  assessments: CareAssessment[];
  insights: Insight[];
  userInsights: Insight[];
  geneticLinking: GeneticLinkingView | null;
  consent: ConsentView;
  professional: {
    pendingPlanIds: string[];
    escalationIds: string[];
    reviewDuePlanIds: string[];
    activePlanIds: string[];
    closedPlanIds: string[];
    insightReviewIds: string[];
    filteredInsightIds: string[];
    sharedObservationIds: string[];
    ownerRoles: Record<string, string>;
    decisionLabels: Record<string, string>;
    /** Oversight queue: assessments linked to an open escalation, sampled, requested by the user or made without consent. */
    assessmentReviewIds: string[];
    humanReviewRequestIds: string[];
    assessmentDecisionLabels: Record<AssessmentDecision, string>;
    assessmentQuestion: string;
  };
  audit: { entries: AuditEntry[]; chains: AuditChain[]; legacy: (Partial<AuditEntry> & { id: string; date: string; detail: string; detailMasked: string; source: string })[] };
  impact: ImpactMetrics;
  policy: {
    notice: string;
    actions: Record<string, string>;
    forbidden: Record<string, string>;
    categoryLabels: Record<string, string>;
    statusLabels: Record<string, string>;
    automation: AutomationPolicy;
    urgencyLabels: Record<AssessmentUrgency, string>;
    assessmentStatusLabels: Record<AssessmentStatus, string>;
    assessmentModeLabels: Record<AssessmentMode, string>;
  };
  demo: {
    openQuestion: boolean;
    pendingProfessional: boolean;
    nextMeasurement: string | null;
    lastCycleAt: string | null;
    symptomReport: string | null;
    homeMonitoringOffer: boolean;
    homeMonitoringActive: boolean;
  };
}

export type DecisionKind =
  | 'approve'
  | 'edit'
  | 'reject'
  | 'request_info'
  | 'continue'
  | 'change_permissions'
  | 'contact_user'
  | 'end'
  | 'set_review_date';

export interface DecisionRequest {
  decision: DecisionKind;
  role: string;
  note?: string;
  changes?: Record<string, unknown>;
  reviewDate?: string;
  allowedActions?: string[];
  escalationAppropriate?: boolean;
  contactUser?: boolean;
}

export interface AssessmentReviewRequest {
  decision: AssessmentDecision;
  role: string;
  note?: string;
  newUrgency?: AssessmentUrgency;
}
