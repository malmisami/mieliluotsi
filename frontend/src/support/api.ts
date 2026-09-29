import { post, request } from '../loop/api';
import type { LoopDashboard } from '../loop/types';
import type {
  AssessmentReviewRequest,
  CareAssessment,
  CohortAggregate,
  CohortPage,
  DecisionRequest,
  GeneticLinkingView,
  HomeMonitoringPeriod,
} from './types';

type WithDashboard<T = unknown> = { result: T; dashboard: LoopDashboard };

export const supportApi = {
  runCycle: () => post<WithDashboard<{ plans: { plan: string; action: string; reason: string; blockedBy?: string }[] }>>('/api/support/cycle'),
  simulateWeek: () => post<WithDashboard>('/api/support/simulate/week'),
  addMeasurement: (systolic: number, diastolic: number) => post<WithDashboard>('/api/support/measurements', { systolic, diastolic }),
  simulateMeasurement: () => post<WithDashboard>('/api/support/simulate/measurement'),
  simulateUserResponse: () => post<WithDashboard>('/api/support/simulate/user-response'),
  /** The user decides whether the home monitoring period the agent offered on its own starts. */
  respondHomeMonitoring: (periodId: string, accept: boolean) =>
    post<WithDashboard<HomeMonitoringPeriod>>(`/api/support/home-monitoring/${periodId}/respond`, { accept }),
  simulateHomeMonitoring: () =>
    post<WithDashboard<{ periodId: string; readings: string[]; status: string }>>('/api/support/simulate/home-monitoring'),
  simulateSymptomReport: () => post<WithDashboard<{ assessment: CareAssessment; intent: string | null; text: string }>>('/api/support/simulate/symptom-report'),
  /** The user's right to an assessment made by a healthcare professional. */
  requestHumanReview: (assessmentId: string) => post<WithDashboard<CareAssessment>>(`/api/support/assessments/${assessmentId}/request-human-review`),
  /** Professional oversight of an automated assessment: confirm, change the urgency class or make the assessment. */
  reviewAssessment: (assessmentId: string, body: AssessmentReviewRequest) =>
    post<WithDashboard<CareAssessment>>(`/api/support/assessments/${assessmentId}/review`, body),
  simulateProfessionalDecision: () => post<WithDashboard<{ planId: string; decision: string }>>('/api/support/simulate/professional-decision'),
  answer: (checkInId: string, questionId: string, optionId: string | null, skip = false) =>
    post<WithDashboard>(`/api/support/checkins/${checkInId}/answer`, { questionId, optionId, skip }),
  decide: (planId: string, body: DecisionRequest) => post<WithDashboard>(`/api/support/plans/${planId}/decision`, body),
  pausePlan: (planId: string, until?: string) => post<WithDashboard>(`/api/support/plans/${planId}/pause`, { until: until || null }),
  resumePlan: (planId: string) => post<WithDashboard>(`/api/support/plans/${planId}/resume`),
  /** Accepts any ConsentSettings field, incl. `automatedAssessment` (explicit consent to the automated assessment). */
  updateConsent: (changes: Record<string, unknown>) =>
    request<WithDashboard>('/api/support/consent', { method: 'PUT', body: JSON.stringify(changes) }),
  /** Link health records to DNA-analysis findings by health theme; the user's own DNA analysis is included when run. */
  linkGenetics: (sessionId?: string | null) => post<WithDashboard<GeneticLinkingView>>('/api/support/genetic-links', { sessionId: sessionId ?? null }),
  unlinkGenetics: () => request<WithDashboard>('/api/support/genetic-links', { method: 'DELETE' }),
  requestReview: (sessionId: string, findingId: string) => post<WithDashboard>('/api/support/insights/request-review', { sessionId, findingId }),
  decideInsight: (insightId: string, body: { decision: 'approve' | 'reject' | 'refer' | 'request_info'; role: string; note?: string; ownerRole?: string }) =>
    post<WithDashboard>(`/api/support/insights/${insightId}/decision`, body),
  cohort: (params: { page: number; pageSize: number; status?: string; theme?: string; ageBand?: string }) => {
    const query = new URLSearchParams({ page: String(params.page), pageSize: String(params.pageSize) });
    if (params.status) query.set('status', params.status);
    if (params.theme) query.set('theme', params.theme);
    if (params.ageBand) query.set('ageBand', params.ageBand);
    return request<CohortPage>(`/api/support/cohort?${query.toString()}`);
  },
  cohortImpact: () => request<CohortAggregate>('/api/support/impact/cohort'),
  previewAdapter: (body: { format: 'csv' | 'json'; content: string; table?: string }) =>
    post<{ target: string; items: unknown; stats: Record<string, number> }>('/api/support/adapters/preview', body),
};
