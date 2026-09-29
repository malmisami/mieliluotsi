import type { FindingRef, FullSummaryData, LoopDashboard, MonitoringPreview, ProfessionalSummaryData, UserResponse } from './types';

import { API_BASE, post, request } from '../lib/http';

// The HTTP helpers moved to lib/http.ts (shared with the Mieliluotsi app); re-exported for the legacy views.
export { API_BASE, post, request } from '../lib/http';

type WithDashboard = { dashboard: LoopDashboard };

export const loopApi = {
  state: () => request<LoopDashboard>('/api/loop/state'),
  preview: (ref: FindingRef) => post<MonitoringPreview>('/api/loop/monitoring/preview', ref),
  startMonitoring: (ref: FindingRef) => post<WithDashboard>('/api/loop/monitorings', ref),
  stopMonitoring: (id: string) => post<WithDashboard>(`/api/loop/monitorings/${id}/stop`),
  addDemoEvent: (template: string) => post<WithDashboard & { userVisibleAlert: boolean }>('/api/loop/demo/events', { template }),
  addFreeText: (text: string) => post<WithDashboard & { userVisibleAlert: boolean }>('/api/loop/events/free-text', { text }),
  advanceTime: (days: number) => post<WithDashboard>('/api/loop/demo/advance-time', { days }),
  reset: () => post<WithDashboard>('/api/loop/demo/reset'),
  clearAll: () => post<WithDashboard>('/api/loop/data/clear'),
  respond: (taskId: string, response: UserResponse) => post<WithDashboard>(`/api/loop/tasks/${taskId}/respond`, { response }),
  summary: (observationId: string) => request<ProfessionalSummaryData>(`/api/loop/observations/${observationId}/summary`),
  summaryHtmlUrl: (observationId: string) => `${API_BASE}/api/loop/observations/${observationId}/summary.html`,
  share: (observationId: string) => post<WithDashboard>(`/api/loop/observations/${observationId}/share`),
  fullSummary: () => request<FullSummaryData>('/api/loop/summary/full'),
  fullSummaryHtmlUrl: () => `${API_BASE}/api/loop/summary/full.html`,
  sendChat: (text: string) => post<WithDashboard & { intent: string; intentMethod: string }>('/api/loop/companion/messages', { text }),
  chatAction: (actionId: string, args: Record<string, unknown> = {}) =>
    post<WithDashboard & { type: string }>(`/api/loop/companion/actions/${actionId}`, { args }),
  submitLifestyleQuiz: (structuredData: Record<string, unknown>, rawText: string) =>
    post<WithDashboard>('/api/loop/lifestyle-quiz', { structuredData, rawText }),
};
