import { useId, useState } from 'react';
import { ClipboardIcon, StethoscopeIcon } from '../icons';
import { formatDate } from '../loop/labels';
import AutomationNotice from './AutomationNotice';
import { OWNER_POSSESSIVE, UrgencyBadge } from './labels';
import type { AutomationPolicy, CareAssessment, Escalation, SupportPlan } from './types';

/** Fixed statement (§2): the rule engine made the assessment, not the language model. */
export const ASSESSMENT_BASIS_STATEMENT =
  'Hoidon tarpeen ja kiireellisyyden arvion teki sääntömoottori ammattilaisen hyväksymän suunnitelman ja demo-policyn sääntöjen mukaan. Kielimalli ei tehnyt arviota.';

/** "Ammattilaisen arvio pyydetty – {owner} tekee arvion {handling}." with the same owner/handling the backend uses. */
export function humanReviewRequestedText(
  assessment: CareAssessment,
  plans: SupportPlan[],
  escalations: Escalation[],
  automation: AutomationPolicy,
): string {
  const plan = plans.find((p) => p.id === assessment.planId);
  const linked = escalations.find((e) => e.id === assessment.escalationId && e.status === 'open')
    ?? escalations.find((e) => e.status === 'open' && e.humanReviewRequested && (!plan || e.planId === plan.id));
  const role = linked?.ownerRole ?? plan?.owner.role ?? 'other';
  const handling = linked?.handlingTime ?? automation.urgencyClasses.find((c) => c.id === 'within_3_days')?.handlingTime ?? '3 arkipäivän kuluessa';
  return `Ammattilaisen arvio pyydetty – ${OWNER_POSSESSIVE[role] ?? OWNER_POSSESSIVE.other} tekee arvion ${handling}.`;
}

interface Props {
  assessment: CareAssessment;
  automation: AutomationPolicy;
  /** Shown once the user has asked for an assessment made by a professional. */
  requestedText: string;
  busy: boolean;
  onRequestHuman: (assessmentId: string) => void;
}

/** The client's view of one automated assessment: class, what happens next, how it was made and the right to a human assessment. */
export default function AssessmentCard({ assessment, automation, requestedText, busy, onRequestHuman }: Props) {
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const review = assessment.professionalReview;
  const emergency = assessment.mode === 'excluded_emergency';
  const requested = assessment.status === 'human_review_requested';

  return (
    <section className={`panel assessment-card assessment-urgency-${assessment.urgency}`} aria-labelledby={`${detailsId}-title`}>
      <header className="assessment-head">
        <h2 id={`${detailsId}-title`}><ClipboardIcon size={24} /> Automaattinen hoidon tarpeen arvio</h2>
        <UrgencyBadge urgency={assessment.urgency} label={assessment.urgencyLabel} />
      </header>
      <p className="assessment-care-need">{assessment.careNeedLabel}</p>
      <p className="muted small">Tehty {formatDate(assessment.createdAt)} · {assessment.modeLabel}</p>

      {requested && (
        <p className="assessment-status is-requested" role="status">
          <StethoscopeIcon size={18} /> <span>{requestedText}</span>
        </p>
      )}
      {review && (
        <p className="assessment-status is-reviewed" role="status">
          <StethoscopeIcon size={18} />
          <span>
            {assessment.statusLabel}: {review.byRole}, {formatDate(review.date)}.
            {review.newUrgencyLabel ? ` Uusi luokka: ${review.newUrgencyLabel}.` : ''}
            {review.note ? ` ${review.note}` : ''}
          </span>
        </p>
      )}

      <div className="row">
        {!emergency && (
          <button type="button" disabled={busy || !assessment.canRequestHuman} onClick={() => onRequestHuman(assessment.id)}>
            <StethoscopeIcon size={18} /> Pyydä ammattilaisen arvio
          </button>
        )}
        <button type="button" className="btn-secondary" aria-expanded={open} aria-controls={detailsId} onClick={() => setOpen(!open)}>
          {open ? 'Piilota perustelut' : 'Näin arvio tehtiin'}
        </button>
      </div>
      <p className="assessment-rights">{assessment.rightsSentence}</p>

      {open && (
        <div id={detailsId} className="assessment-details">
          <p><strong>{ASSESSMENT_BASIS_STATEMENT}</strong></p>
          <dl className="fact-list">
            <div><dt>Peruste</dt><dd>{assessment.reason}</dd></div>
            {assessment.basis.length > 0 && (
              <div><dt>Käytetyt tiedot</dt><dd><ul>{assessment.basis.map((line) => <li key={line}>{line}</li>)}</ul></dd></div>
            )}
            {assessment.symptoms.length > 0 && <div><dt>Kuvatut oireet</dt><dd>{assessment.symptoms.join(', ')}</dd></div>}
            {assessment.rulesApplied.length > 0 && (
              <div>
                <dt>Säännöt</dt>
                <dd><ul>{assessment.rulesApplied.map((rule) => <li key={rule.id}><code>{rule.id}</code> – {rule.name}</li>)}</ul></dd>
              </div>
            )}
            {assessment.responsiblePerson && <div><dt>Vastuu</dt><dd>{assessment.responsiblePerson}</dd></div>}
          </dl>
          <AutomationNotice automation={automation} />
        </div>
      )}
      <p className="assessment-legal muted small">{assessment.legalNotice}</p>
    </section>
  );
}
