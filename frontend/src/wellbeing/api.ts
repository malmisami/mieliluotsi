import { post, request } from '../loop/api';
import type { LoopDashboard } from '../loop/types';
import type { WellbeingSummary } from './types';

type WithDashboard<T = unknown> = { result: T; dashboard: LoopDashboard };

export const wellbeingApi = {
  summary: (period: number) => request<WellbeingSummary>(`/api/health/summary?period=${period}`),
  /** A one-time code the user types into the iPhone app (the HealthKit bridge). Shown once, stored only as a hash. */
  pairingCode: () => post<{ code: string; expiresAt: string }>('/api/health/pairing-code'),
  useSynthetic: () => post<WithDashboard>('/api/health/demo/synthetic'),
  syncNow: () => post<WithDashboard<{ message?: string; created: number }>>('/api/health/sync-now'),
  setPermissions: (permissions: Record<string, boolean>) =>
    request<WithDashboard>('/api/health/permissions', { method: 'PUT', body: JSON.stringify({ permissions }) }),
  setMonitoring: (areas: Record<string, boolean>) =>
    request<WithDashboard>('/api/health/monitoring', { method: 'PUT', body: JSON.stringify({ areas }) }),
  disconnect: () => post<WithDashboard>('/api/health/disconnect'),
  deleteData: () => request<WithDashboard<number>>('/api/health/data', { method: 'DELETE' }),
  discuss: (observationId: string) => post<WithDashboard>(`/api/health/observations/${observationId}/discuss`),
  dismiss: (observationId: string) => post<WithDashboard>(`/api/health/observations/${observationId}/dismiss`),
};
