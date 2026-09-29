import type { ReactNode } from 'react';
import { AlertIcon, CheckIcon, ClockIcon, DotIcon, MinusIcon, QuestionIcon } from '../icons';
import type { AgentState, HealthEvent } from './types';

type Tone = 'active' | 'neutral' | 'attention' | 'waiting' | 'done';
type StatusIcon = 'dot' | 'minus' | 'question' | 'alert' | 'clock' | 'check';

const STATUS_ICONS: Record<StatusIcon, ReactNode> = {
  dot: <DotIcon size={16} />,
  minus: <MinusIcon size={16} />,
  question: <QuestionIcon size={16} />,
  alert: <AlertIcon size={16} />,
  clock: <ClockIcon size={16} />,
  check: <CheckIcon size={16} />,
};

export const STATUS_META: Record<AgentState, { label: string; icon: StatusIcon; tone: Tone }> = {
  monitoring: { label: 'Seuranta aktiivinen', icon: 'dot', tone: 'active' },
  no_action: { label: 'Ei toimenpiteitä', icon: 'minus', tone: 'neutral' },
  additional_information_needed: { label: 'Lisätietoa tarvitaan', icon: 'question', tone: 'attention' },
  professional_review_recommended: { label: 'Uusi huomio: ammattilaisen arvio suositeltu', icon: 'alert', tone: 'attention' },
  waiting_for_user: { label: 'Odottaa toimintaasi', icon: 'clock', tone: 'waiting' },
  waiting_for_professional_review: { label: 'Odottaa ammattilaisen arviota', icon: 'clock', tone: 'waiting' },
  resolved: { label: 'Käsitelty', icon: 'check', tone: 'done' },
  dismissed: { label: 'Käsitelty: todettu epäolennaiseksi', icon: 'check', tone: 'done' },
};

export function StatusBadge({ status }: { status: AgentState }) {
  const meta = STATUS_META[status] ?? STATUS_META.monitoring;
  return (
    <span className={`status-badge tone-${meta.tone}`}>
      {STATUS_ICONS[meta.icon]} {meta.label}
    </span>
  );
}

export function SyntheticTag() {
  return <span className="synthetic-tag">Synteettinen</span>;
}

export function formatDate(iso: string | null | undefined) {
  if (!iso) return '–';
  const [y, m, d] = iso.split('-');
  return `${Number(d)}.${Number(m)}.${y}`;
}

export function formatValue(event: Pick<HealthEvent, 'value' | 'unit'>) {
  if (event.value === null || event.value === undefined) return '';
  const value = typeof event.value === 'number' ? event.value.toLocaleString('fi-FI') : event.value;
  return `${value}${event.unit ? ` ${event.unit}` : ''}`;
}

export function flagText(flag: HealthEvent['abnormalFlag']) {
  switch (flag) {
    case 'high':
      return '▲ Viitealueen yläpuolella (H)';
    case 'low':
      return '▼ Viitealueen alapuolella (L)';
    case 'normal':
      return '● Viitealueella';
    case 'unknown':
      return '? Viitealuetieto puuttuu';
    default:
      return null;
  }
}

export const DECISION_LABELS: Record<string, string> = {
  ...Object.fromEntries(Object.entries(STATUS_META).map(([key, meta]) => [key, meta.label])),
  monitoring_stopped: 'Seuranta lopetettu',
};

export const LOG_KIND_LABELS: Record<string, string> = {
  monitoring_started: 'Seuranta aloitettu',
  monitoring_stopped: 'Seuranta lopetettu',
  event_evaluated: 'Terveystapahtuma arvioitu',
  follow_up_due: 'Seurantatehtävä erääntyi',
  periodic_review: 'Määräaikainen tarkistus',
  time_advanced: 'Demon aikaa siirretty',
  user_response: 'Käyttäjän vastaus',
  summary_shared: 'Yhteenveto merkitty jaetuksi',
};

/** Terveystiedot shows the records as a real service would: the "(synteettinen)" markers of the demo data are left out. */
export function withoutSyntheticMarker(value: string): string;
export function withoutSyntheticMarker(value: string | undefined): string | undefined;
export function withoutSyntheticMarker(value: string | undefined) {
  if (!value) return value;
  return value
    .replace(/\s*\((?:synteettinen|synthetic)[^)]*\)/gi, '')
    .replace(/,\s*(?:synteettinen|synthetic)[^),]*\)/gi, ')')
    .replace(/(^|\s)Synteettinen [^.]*\.\s*/g, '$1')
    .trim();
}
