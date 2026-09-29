import type { ReactNode } from 'react';
import { StethoscopeIcon } from '../../icons';
import { formatDate } from '../../loop/labels';
import { escalationTone, ToneBadge } from '../labels';
import type { Escalation } from '../types';

interface Props {
  escalation: Escalation;
  /** The oversight card of the linked automated assessment (AssessmentReview), when it resolves. */
  assessmentReview?: ReactNode;
}

export default function EscalationSummary({ escalation, assessmentReview }: Props) {
  const tone = escalationTone(escalation.urgency);
  return (
    <section className={`escalation-summary ${escalation.status === 'open' ? 'is-open' : ''}`} aria-labelledby={`esc-${escalation.id}`}>
      <div className="escalation-head">
        <h3 id={`esc-${escalation.id}`}>Automaattinen hoidon tarpeen arvio ja ohjaus · {formatDate(escalation.createdAt)}</h3>
        <ToneBadge tone={escalation.status === 'open' ? tone : 'neutral'}>
          {escalation.status === 'open' ? `${escalation.urgencyLabel} · käsittely ${escalation.handlingTime}` : 'Käsitelty'}
        </ToneBadge>
      </div>
      {escalation.humanReviewRequested && escalation.status === 'open' && (
        <p className="assessment-banner" role="note"><StethoscopeIcon size={18} /> <strong>Asiakas pyysi ammattilaisen tekemän arvion</strong></p>
      )}
      <p className="escalation-decision"><strong>Avoin päätös:</strong> {escalation.openDecision}</p>
      <p>{escalation.summaryText}</p>
      <dl className="fact-list">
        <div><dt>Syy (sääntö)</dt><dd>{escalation.rulesApplied.map((r) => <span key={r.id}><code>{r.id}</code> – {r.description}</span>)}</dd></div>
        <div><dt>Havaittu muutos</dt><dd><ul>{escalation.observedChange.map((line) => <li key={line}>{line}</li>)}</ul></dd></div>
        <div>
          <dt>Aikajana</dt>
          <dd><ol className="history-list">{escalation.timeline.map((item, i) => <li key={`${item.date}-${i}`}>{formatDate(item.date)} – {item.text}</li>)}</ol></dd>
        </div>
        <div><dt>Agentin aiemmat toimet</dt><dd><ul>{escalation.agentActions.map((a, i) => <li key={i}>{formatDate(a.date)} – {a.text}</li>)}</ul></dd></div>
        <div>
          <dt>Asiakkaan vastaukset</dt>
          <dd><ul>{escalation.userResponses.map((r, i) => <li key={i}>{formatDate(r.date)} – {r.question} <strong>{r.answer}</strong></li>)}</ul></dd>
        </div>
        <div><dt>Tietolähteet</dt><dd>{escalation.sources.map((s) => s.label).join('; ')}</dd></div>
      </dl>
      <p className="muted small">
        Kiireellisyysluokka on sääntömoottorin automaattinen arvio (ei kielimallin). Tiivistelmän muotoili {escalation.summarySource === 'llm' ? 'kielimalli rajatuista faktoista (turvatarkistettu)' : 'valmis tekstipohja'}.
      </p>
      {assessmentReview}
      {escalation.decision && (
        <p className="escalation-resolution">
          {escalation.decision.byRole}: {escalation.decision.label} ({formatDate(escalation.decision.date)}).
          {escalation.appropriate !== null && ` Automaattinen kiireellisyysarvio oli oikea: ${escalation.appropriate ? 'kyllä' : 'ei'}.`}
          {escalation.decision.note && ` ${escalation.decision.note}`}
        </p>
      )}
    </section>
  );
}
