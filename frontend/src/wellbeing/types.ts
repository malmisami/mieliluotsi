/** Hyvinvointidata (Apple Health): daily summaries around the personal baseline. Mirrors backend/app/wellbeing/view.py. */

export type ChangeKind = 'concern' | 'positive' | 'neutral';

export interface HealthConnection {
  status: 'not_connected' | 'connected' | 'disconnected';
  source: 'apple_health' | 'synthetic_demo' | null;
  sourceLabel: string;
  synthetic: boolean;
  connectedAt: string | null;
  lastSyncAt: string | null;
  devices: { id: string; name: string; pairedAt: string; lastSyncAt: string | null }[];
  pairingExpiresAt: string | null;
  permissions: Record<string, boolean>;
  history: { date: string; change: string }[];
}

export interface ObservationLine {
  label: string;
  current: string;
  baseline: string;
  delta: string;
  consecutive: string | null;
}

export interface HealthObservation {
  id: string;
  kind: 'change' | 'positive';
  areaId: string;
  areaLabel: string;
  title: string;
  summary: string;
  areaNote: string;
  why: { reason: string; basis: string; lines: ObservationLine[]; period: string; rules: string[]; source: string };
  priority: 'high' | 'normal' | 'low';
  status: 'new' | 'discussed' | 'dismissed';
  createdAt: string;
  periodEnd: string;
  followUpAt: string | null;
  outcome: string | null;
}

export interface TrendSeries {
  metric: string;
  label: string;
  unit: string | null;
  format: 'integer' | 'duration' | 'decimal1';
  monitored: boolean;
  points: { date: string; value: number }[];
  baseline: number | null;
  baselineText: string | null;
  current: number | null;
  currentText: string | null;
  change: ChangeKind | null;
  weekly: boolean;
}

export interface WellbeingSummary {
  available: boolean;
  demoMode: boolean;
  permissionText: string;
  consentAllowed: boolean;
  inUse: boolean;
  connection: HealthConnection;
  metrics: { id: string; label: string; unit: string | null; healthKit: string; permitted: boolean }[];
  monitoring: { id: string; label: string; active: boolean; selectable: boolean; basis: string; metrics: string[] }[];
  observations: HealthObservation[];
  periods: { days: number; label: string }[];
  period: number;
  dataRange: { from: string; to: string; days: number } | null;
  today: { metric: string; label: string; date: string; value: string; comparisonLabel: string; comparison: string | null; kind: ChangeKind | null }[];
  trends: TrendSeries[];
  changes: { metric: string; label: string; kind: ChangeKind; text: string; delta: string; area: string | null; consecutiveDays: number }[];
  /** Exactly what the agent (and the optional LLM) gets from Hyvinvointidata: a compact summary, never the history. */
  agentContext: Record<string, unknown> | null;
}

/** The small block of the main dashboard (navigation badge, connection state). */
export interface WellbeingDashboardBlock {
  status: HealthConnection['status'];
  synthetic: boolean;
  sourceLabel: string;
  lastSyncAt: string | null;
  newObservations: number;
  inUse: boolean;
}
