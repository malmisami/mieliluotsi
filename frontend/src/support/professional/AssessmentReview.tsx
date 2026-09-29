import { useEffect, useState } from 'react';
import { StethoscopeIcon } from '../../icons';
import { formatDate } from '../../loop/labels';
import { URGENCY_ORDER, UrgencyBadge } from '../labels';
import type { AssessmentDecision, AssessmentReviewRequest, AssessmentUrgency, CareAssessment, UrgencyClass } from '../types';

const DECISIONS: AssessmentDecision[] = ['confirm', 'change_urgency', 'take_over'];
const OPEN_STATUSES = ['issued', 'human_review_requested'];

interface Props {
  assessment: CareAssessment;
  urgencyClasses: UrgencyClass[];
  labels: Record<AssessmentDecision, string>;
  role: string;
  busy: boolean;
  onReview: (body: AssessmentReviewRequest) => void;
  /** Link to the plan the assessment belongs to (oversight queue view). */
  onOpenPlan?: (planId: string) => void;
  planName?: string;
}

/** Professional oversight of one automated assessment: confirm it, change the urgency class or make the assessment yourself. */
export default function AssessmentReview({ assessment, urgencyClasses, labels, role, busy, onReview, onOpenPlan, planName }: Props) {
  const [decision, setDecision] = useState<AssessmentDecision | null>(null);
  const [urgency, setUrgency] = useState<AssessmentUrgency | ''>('');
  const [note, setNote] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const isOpen = OPEN_STATUSES.includes(assessment.status);
  const review = assessment.professionalReview;
  const classes = URGENCY_ORDER.map((id) => urgencyClasses.find((c) => c.id === id)).filter((c): c is UrgencyClass => Boolean(c));
  const titleId = `hta-${assessment.id}`;

  useEffect(() => {
    setDecision(null);
    setNote('');
    setFormError(null);
  }, [assessment.id, assessment.status]);

  function choose(next: AssessmentDecision) {
    setDecision(next);
    setFormError(null);
    setUrgency(next === 'take_over' ? assessment.urgency : '');
  }

  function submit() {
    if (!decision) return;
    if (decision === 'change_urgency' && (!urgency || urgency === assessment.urgency)) {
      setFormError('Valitse uusi kiireellisyysluokka (eri kuin nykyinen).');
      return;
    }
    const body: AssessmentReviewRequest = { decision, role, note: note.trim() || undefined };
    if (decision !== 'confirm' && urgency && urgency !== assessment.urgency) body.newUrgency = urgency;
    onReview(body);
  }

  return (
    <section className={`assessment-review ${isOpen ? 'is-open' : ''}`} aria-labelledby={titleId}>
      <div className="escalation-head">
        <h3 id={titleId}>Automaattinen hoidon tarpeen arvio · {formatDate(assessment.createdAt)}</h3>
        <UrgencyBadge urgency={assessment.urgency} label={assessment.urgencyLabel} suffix={assessment.handlingTime} />
      </div>
      <p className="muted small">
        {assessment.modeLabel} · {assessment.statusLabel} · <code>{assessment.id}</code>
        {planName && assessment.planId && onOpenPlan && (
          <> · <button type="button" className="link-button" onClick={() => onOpenPlan(assessment.planId as string)}>Avaa suunnitelma: {planName}</button></>
        )}
      </p>
      {assessment.status === 'human_review_requested' && (
        <p className="assessment-banner" role="note">
          <StethoscopeIcon size={18} /> <strong>Asiakas pyysi ammattilaisen tekemän arvion</strong>
          {assessment.humanReviewRequestedAt && <span className="muted small"> ({formatDate(assessment.humanReviewRequestedAt)})</span>}
        </p>
      )}
      {assessment.mode === 'professional_required' && (
        <p className="assessment-banner" role="note"><strong>Esiarvio – ammattilainen tekee arvion.</strong> Asiakas ei ole antanut suostumusta automaattiseen arvioon.</p>
      )}

      <dl className="fact-list">
        <div><dt>Hoidon tarve</dt><dd>{assessment.careNeedLabel}</dd></div>
        <div><dt>Peruste</dt><dd>{assessment.reason}</dd></div>
        {assessment.basis.length > 0 && <div><dt>Käytetyt tiedot</dt><dd><ul>{assessment.basis.map((line) => <li key={line}>{line}</li>)}</ul></dd></div>}
        {assessment.rulesApplied.length > 0 && (
          <div>
            <dt>Säännöt</dt>
            <dd><ul>{assessment.rulesApplied.map((rule) => <li key={rule.id}><code>{rule.id}</code> – {rule.description || rule.name}</li>)}</ul></dd>
          </div>
        )}
      </dl>
      <p className="muted small">Kiireellisyysluokka on sääntömoottorin automaattinen arvio (ei kielimallin).</p>

      {review && (
        <p className="escalation-resolution">
          {review.byRole}: {review.label} ({formatDate(review.date)}).
          {review.newUrgencyLabel && ` Uusi luokka: ${review.newUrgencyLabel}.`}
          {review.note && ` ${review.note}`}
        </p>
      )}

      {isOpen && (
        <>
          <div className="decision-buttons" role="group" aria-label="Arvion valvonta">
            {DECISIONS.map((option) => (
              <button key={option} type="button" className={decision === option ? '' : 'btn-secondary'} aria-pressed={decision === option}
                disabled={busy} onClick={() => choose(option)}>
                {labels[option]}
              </button>
            ))}
          </div>
          {decision && (
            <form noValidate className="decision-form" onSubmit={(e) => { e.preventDefault(); submit(); }}>
              {decision !== 'confirm' && (
                <label>
                  {decision === 'change_urgency' ? 'Uusi kiireellisyysluokka' : 'Kiireellisyysluokka (ammattihenkilön arvio)'}
                  <select value={urgency} onChange={(e) => setUrgency(e.target.value as AssessmentUrgency | '')} required={decision === 'change_urgency'}>
                    {decision === 'change_urgency' && <option value="">Valitse luokka</option>}
                    {classes.map((cls) => (
                      <option key={cls.id} value={cls.id} disabled={decision === 'change_urgency' && cls.id === assessment.urgency}>
                        {cls.label} ({cls.handlingTime}){cls.id === assessment.urgency ? ' – nykyinen' : ''}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label>
                Perustelu (valinnainen, näytetään asiakkaalle)
                <textarea rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              {formError && <p className="form-error" role="alert">{formError}</p>}
              <div className="row">
                <button type="submit" disabled={busy}>Vahvista: {labels[decision]}</button>
                <button type="button" className="btn-secondary" onClick={() => setDecision(null)}>Peruuta</button>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}
