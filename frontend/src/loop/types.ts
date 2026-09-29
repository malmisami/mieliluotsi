import type { AssessmentMode, AssessmentUrgency, SupportView } from '../support/types';

export type ConfirmationStatus = 'raw_candidate' | 'synthetic_demo_confirmed' | 'professionally_confirmed';

export type AgentState =
  | 'monitoring'
  | 'no_action'
  | 'additional_information_needed'
  | 'professional_review_recommended'
  | 'waiting_for_user'
  | 'waiting_for_professional_review'
  | 'resolved'
  | 'dismissed';

export type UserResponse = 'yes' | 'not_yet' | 'no_reminder' | 'not_relevant';

export interface GenomicFinding {
  id: string;
  gene: string | null;
  variant: string;
  title: string;
  description: string;
  classification: string;
  confirmationStatus: ConfirmationStatus;
  evidenceLevel: string;
  monitoringEligible: boolean;
  relevantEventTypes: string[];
  source: string;
  lastReviewedAt: string | null;
  synthetic: boolean;
  relatedConditions: string[];
  healthArea: string | null;
}

export interface HealthEvent {
  id: string;
  date: string;
  type: string;
  code: string | null;
  displayName: string;
  value: string | number | null;
  unit: string | null;
  abnormalFlag: 'high' | 'low' | 'normal' | 'unknown' | null;
  source: string;
  rawText: string | null;
  extractedData: Record<string, unknown>;
  structuredData: Record<string, unknown>;
  confirmedByUser: boolean;
  synthetic: boolean;
}

export interface FollowUpTask {
  id: string;
  observationId: string;
  createdAt: string;
  dueAt: string;
  status: 'open' | 'awaiting_response' | 'completed' | 'cancelled';
  userResponse: UserResponse | null;
}

export interface Observation {
  id: string;
  monitoringId: string;
  findingId: string;
  eventId: string;
  ruleId: string;
  status: AgentState;
  createdAt: string;
  title: string;
  explanation: string;
  explanationSource: 'llm' | 'template';
  connection: string;
  missingInformation: string[];
  systemDid: string[];
  systemDidNot: string[];
  sharedAt: string | null;
  remindersDisabled: boolean;
  finding: GenomicFinding | null;
  event: HealthEvent | null;
  rule: { id: string; name: string; description: string };
  source: string;
  evidenceLevelLabel: string | null;
  confirmationLabel: string | null;
  task: FollowUpTask | null;
  disclaimer: string;
  ruleIds: string[];
  rules: RuleView[];
  supportingEventIds: string[];
  supportingEvents: HealthEvent[];
  previousEvents: HealthEvent[];
  confirmedFamilyHistory: HealthEvent[];
  updatedAt: string | null;
  summaryCreatedAt: string | null;
}

export interface RuleView {
  id: string;
  name: string;
  description: string;
  demoNotice: string | null;
}

export interface MonitoringView {
  id: string;
  findingId: string;
  active: boolean;
  status: AgentState;
  consentedAt: string;
  nextReviewAt: string;
  lastRelevantEventId: string | null;
  currentAssessment: string;
  openObservationId: string | null;
  stoppedAt: string | null;
  finding: GenomicFinding;
  confirmationLabel: string;
  evidenceLevelLabel: string;
  monitoredEvents: string[];
  latestRelevantEvent: HealthEvent | null;
  observations: Observation[];
}

export interface AgentLogEntry {
  id: string;
  date: string;
  kind: string;
  detectedEvent: Record<string, unknown> | null;
  extractedData: Record<string, unknown> | null;
  extractionMethod: string | null;
  watchlistMatches: Record<string, unknown>[];
  ruleApplied: Record<string, unknown> | null;
  evidenceCheck: Record<string, unknown> | null;
  safetyCheck: Record<string, unknown> | null;
  decision: string;
  decisionDetail: string;
  userVisibleAlert: boolean;
  userApprovalStatus: string;
}

export interface LoopDashboard {
  synthetic: true;
  syntheticNotice: string;
  disclaimer: string;
  profile: { id: string; name: string; notice_fi: string; birthYear: number; heightCm: number; weightKg: number };
  currentDate: string;
  llm: { provider: string; enabled: boolean; model: string | null; lastCallFailed: boolean };
  counts: { activeMonitorings: number; openObservations: number; nextReviewDate: string | null };
  findings: (GenomicFinding & { monitored: boolean; confirmationLabel: string })[];
  monitorings: MonitoringView[];
  observations: Observation[];
  openObservationIds: string[];
  pendingQuestions: (FollowUpTask & { question: string; observation: Observation })[];
  tasks: FollowUpTask[];
  events: HealthEvent[];
  eventTypeLabels: Record<string, string>;
  agentLog: AgentLogEntry[];
  demoTemplates: { key: string; label: string }[];
  companion: CompanionState;
  support: SupportView;
}

export interface ChatAction {
  id: string;
  label: string;
  type: string;
  args: Record<string, unknown>;
  used: boolean;
  style: 'primary' | 'secondary';
}

export interface MessageBasis {
  monitorings: { id: string; finding: string; status: string }[];
  events: string[];
  userProvided: string[];
  evidenceSource: string | null;
  rules: { id: string; name: string; demoNotice: string | null }[];
  decisionBy: string;
  textBy: string;
  statement: string;
  /** Only on messages that carry an automated assessment. */
  assessmentId?: string;
  urgency?: AssessmentUrgency;
  urgencyLabel?: string;
  legalNotice?: string;
}

export interface ChatMessage {
  id: string;
  role: 'agent' | 'user';
  kind: string;
  text: string;
  date: string;
  initiatedByAgent: boolean;
  intent: string | null;
  actions: ChatAction[];
  basis: MessageBasis | null;
  whyNowObservationId: string | null;
  summaryObservationId: string | null;
  pendingActionId: string | null;
  textSource: 'llm' | 'template' | 'fixed';
  aiUnavailable: boolean;
  /** Present when the message carries an automated care-need assessment (urgency set by the rule engine). */
  assessment?: ChatAssessmentRef | null;
}

export interface ChatAssessmentRef {
  id: string;
  urgency: AssessmentUrgency;
  urgencyLabel: string;
  mode?: AssessmentMode;
  status?: string;
}

export interface ChatLogEntry {
  id: string;
  date: string;
  userMessage: string | null;
  trigger: string;
  intent: string | null;
  intentMethod: string | null;
  contextUsed: string[];
  extraction: Record<string, unknown> | null;
  userConfirmation: string;
  toolInvoked: string | null;
  ruleApplied: Record<string, unknown>[];
  safetyCheck: Record<string, unknown> | null;
  finalState: string | null;
  llmRole: string;
}

export interface PendingAction {
  id: string;
  type: string;
  payload: { kind?: string; data?: Record<string, unknown>; observationId?: string };
  status: string;
}

export interface CompanionState {
  messages: ChatMessage[];
  pendingActions: PendingAction[];
  chatLog: ChatLogEntry[];
  knowledge: {
    activePlans: number;
    activePlansLabel: string;
    planStates: { name: string; status: string; version: number }[];
    activeMonitorings: number;
    activeMonitoringsLabel: string;
    openObservations: number;
    openObservationsLabel: string;
    missingInformation: string[];
    nextTask: string | null;
    latestRelevantEvent: string | null;
    monitoringStates: { finding: string; status: AgentState }[];
  };
  userContext: Record<string, unknown[]>;
  awaitingMissingInfoId: string | null;
  unansweredProactive: number;
  disclaimers: { whyNow: string; aiUnavailable: string };
  familyHistoryOptions: { relations: Record<string, string>; conditions: Record<string, string> };
}

export interface MonitoringPreview {
  finding: GenomicFinding;
  eligible: boolean;
  reasonNotEligible: string | null;
  alreadyMonitored: boolean;
  monitoringId: string | null;
  monitoredEvents: string[];
  confirmationStatus: ConfirmationStatus;
  confirmationLabel: string;
  evidenceLevel: string;
  evidenceLevelLabel: string;
  source: string;
  disclaimer: string;
  responsibilityNotes: string[];
}

export interface ProfessionalSummaryData {
  syntheticPersonName: string;
  generatedAt: string;
  observationId: string;
  status: AgentState;
  sharedAt: string | null;
  intro: string;
  introSource: 'llm' | 'template';
  finding: GenomicFinding;
  confirmationStatus: ConfirmationStatus;
  confirmationLabel: string;
  evidenceLevelLabel: string;
  event: HealthEvent | null;
  dates: { findingLastReviewedAt: string | null; monitoringConsentedAt: string; eventDate: string | null; observationCreatedAt: string };
  source: string;
  rule: { id: string; name: string; description: string };
  reason: string;
  missingInformation: string[];
  disclaimer: string;
  limitations: string[];
  rules: RuleView[];
  relevantEvents: HealthEvent[];
  userConfirmedFamilyHistory: HealthEvent[];
  questionsForProfessional: string[];
  summaryCreatedAt: string | null;
}

export interface TrackedMetric {
  code: string;
  label: string;
  unit: string;
  points: { date: string; value: string | number | null; abnormalFlag: 'high' | 'low' | 'normal' | 'unknown' | null }[];
}

export interface FullSummaryFinding {
  finding: GenomicFinding;
  confirmationLabel: string;
  evidenceLevelLabel: string;
  monitoringStatus: AgentState;
  relatedEvents: HealthEvent[];
  trackedMetrics: TrackedMetric[];
  hasDefinedMetric: boolean;
  missingInformation: string[];
}

export interface FullSummaryData {
  syntheticPersonName: string;
  generatedAt: string;
  intro: string;
  introSource: 'llm' | 'template';
  findings: FullSummaryFinding[];
  unrelatedEvents: HealthEvent[];
  suggestedNextSteps: string[];
  missingInformation: string[];
  questionsForProfessional: string[];
  disclaimer: string;
  limitations: string[];
}

export interface FindingRef {
  findingId: string;
  sessionId?: string | null;
}
