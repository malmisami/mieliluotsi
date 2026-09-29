import type { ReactNode } from 'react';
import { AlertIcon, CheckIcon, ClockIcon, DotIcon, InfoIcon, MinusIcon } from '../icons';
import type { AssessmentUrgency, PlanStatus, RelevanceCategory, Tone, Urgency } from './types';

const TONE_ICONS: Record<Tone, ReactNode> = {
  calm: <CheckIcon size={16} />,
  attention: <InfoIcon size={16} />,
  waiting: <ClockIcon size={16} />,
  urgent: <AlertIcon size={16} />,
  neutral: <DotIcon size={16} />,
};

export const PLAN_TONES: Record<PlanStatus, Tone> = {
  candidate: 'neutral',
  pending_professional_review: 'neutral',
  active: 'calm',
  paused: 'neutral',
  escalated: 'waiting',
  completed: 'neutral',
  rejected: 'neutral',
};

export function ToneBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`support-badge support-tone-${tone}`}>{TONE_ICONS[tone]} {children}</span>;
}

/** Tone of each urgency class of the automated care-need assessment. */
export const URGENCY_TONES: Record<AssessmentUrgency, Tone> = {
  emergency: 'urgent',
  same_day: 'urgent',
  within_3_days: 'attention',
  routine: 'waiting',
  self_care: 'calm',
};

/** Classes from the most to the least urgent (the professional's class picker). */
export const URGENCY_ORDER: AssessmentUrgency[] = ['emergency', 'same_day', 'within_3_days', 'routine', 'self_care'];

/** Tone of an escalation from the plan rules' urgency vocabulary (routine | soon | same_day). */
export function escalationTone(urgency: Urgency): Tone {
  return urgency === 'same_day' ? 'urgent' : urgency === 'soon' ? 'attention' : 'waiting';
}

/** The urgency class of an automated assessment. The label always comes from the backend policy (rule-based). */
export function UrgencyBadge({ urgency, label, suffix }: { urgency: AssessmentUrgency; label: string; suffix?: string }) {
  return <ToneBadge tone={URGENCY_TONES[urgency] ?? 'neutral'}>{label}{suffix ? ` · ${suffix}` : ''}</ToneBadge>;
}

export const CATEGORY_TONES: Record<RelevanceCategory, Tone> = {
  no_practical_significance: 'neutral',
  uncertain_or_conflicting: 'neutral',
  needs_professional_check: 'attention',
  potentially_actionable: 'attention',
  professionally_approved: 'calm',
};

export function CategoryBadge({ category, label }: { category: RelevanceCategory; label: string }) {
  return <ToneBadge tone={CATEGORY_TONES[category]}>{label}</ToneBadge>;
}

export const ACTOR_LABELS: Record<string, string> = {
  agent: 'Agentti',
  user: 'Käyttäjä',
  professional: 'Ammattilainen',
  system: 'Järjestelmä',
};

/** "hoitajasi" – mirrors backend texts.OWNER_POSSESSIVE for the client's own sentences. */
export const OWNER_POSSESSIVE: Record<string, string> = {
  nurse: 'hoitajasi',
  public_health_nurse: 'terveydenhoitajasi',
  physician: 'lääkärisi',
  genetics: 'perinnöllisyyslääkäri',
  other: 'vastuuammattilaisesi',
};

/** Audit outcomes of the automated assessment (urgency ids are localized from policy.urgencyLabels). */
export const ASSESSMENT_OUTCOME_LABELS: Record<string, string> = {
  human_review_requested: 'Ammattilaisen arvio pyydetty',
  confirmed: 'Arvio vahvistettu',
  changed: 'Arviota muutettu',
  human_reviewed: 'Ammattilainen teki arvion itse',
};

export const SIGNAL_LABELS: Record<string, string> = {
  missing_measurement: 'Sovittu mittaus puuttuu',
  above_target: 'Keskiarvo sovitun tavoitetason yläpuolella',
  trend_rising: 'Mittausten trendi nousussa',
  goal_not_met: 'Sovittu tavoite ei toteutunut',
  repeated_goal_failure: 'Sama tavoite ei ole toteutunut useasti',
  review_due_soon: 'Tarkistuspäivä lähestyy',
  review_overdue: 'Tarkistuspäivä on ohitettu',
  stale_data: 'Tieto on vanhentunut',
  new_concern: 'Käyttäjä ilmoitti uuden huolen',
  repeated_contact: 'Toistuvia yhteydenottoja samasta aiheesta',
  safety_threshold: 'Demo-turvaraja ylittyi',
  rule_engine_observation: 'Sääntömoottorin avoin huomio',
  source_disabled: 'Tietolähde pois käytöstä',
  checkin_due: 'Viikkotarkistus ajankohtainen',
};

export function NoneIcon() {
  return <MinusIcon size={16} />;
}
