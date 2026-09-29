import { useId, useState } from 'react';
import { flagText, formatDate, formatValue, StatusBadge, SyntheticTag } from './labels';
import type { MonitoringView } from './types';

interface Props {
  monitoring: MonitoringView;
  onWhyNow: (observationId: string) => void;
  onStop: (monitoringId: string) => void;
  busy: boolean;
}

export default function MonitoringCard({ monitoring, onWhyNow, onStop, busy }: Props) {
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const { finding, latestRelevantEvent: latest } = monitoring;
  const hasOpenObservation = Boolean(monitoring.openObservationId);

  return (
    <article className={`monitoring-card ${hasOpenObservation ? 'has-observation' : ''}`} aria-labelledby={`${detailsId}-title`}>
      <header className="monitoring-card-head">
        <h3 id={`${detailsId}-title`}>{finding.title}</h3>
        <SyntheticTag />
      </header>
      <p className="monitoring-status">
        <span className="visually-hidden">Tila: </span>
        {monitoring.active ? <StatusBadge status={monitoring.status} /> : <span className="status-badge tone-neutral">Seuranta lopetettu</span>}
      </p>

      <dl className="fact-list">
        <div>
          <dt>Nykyinen arvio</dt>
          <dd>{monitoring.active ? monitoring.currentAssessment : `Seuranta lopetettu ${formatDate(monitoring.stoppedAt)}.`}</dd>
        </div>
        <div>
          <dt>Viimeisin merkityksellinen tapahtuma</dt>
          <dd>
            {latest ? (
              <>
                {latest.displayName} {formatValue(latest)} ({formatDate(latest.date)})
                {flagText(latest.abnormalFlag) && <> · {flagText(latest.abnormalFlag)}</>}
              </>
            ) : (
              'Ei vielä seurantaan liittyviä tapahtumia.'
            )}
          </dd>
        </div>
        <div>
          <dt>Seurattavat tapahtumatyypit</dt>
          <dd>
            <ul className="chip-list">
              {monitoring.monitoredEvents.map((item) => <li key={item} className="chip">{item}</li>)}
            </ul>
          </dd>
        </div>
      </dl>

      <div className="row">
        <button type="button" className="btn-secondary" aria-expanded={open} aria-controls={detailsId} onClick={() => setOpen(!open)}>
          {open ? 'Piilota lisätiedot' : 'Näytä lisätiedot'}
        </button>
        {monitoring.openObservationId && (
          <button type="button" onClick={() => onWhyNow(monitoring.openObservationId!)}>Miksi nyt?</button>
        )}
      </div>

      {open && (
        <div id={detailsId} className="monitoring-details">
          <p>{finding.description}</p>
          <dl className="fact-list two-col">
            <div><dt>Geeni / variantti</dt><dd>{finding.gene} · {finding.variant}</dd></div>
            <div><dt>Luokitus</dt><dd>{finding.classification}</dd></div>
            <div><dt>Vahvistustila</dt><dd>{monitoring.confirmationLabel}</dd></div>
            <div><dt>Evidenssin taso</dt><dd>{monitoring.evidenceLevelLabel}</dd></div>
            <div><dt>Lähde</dt><dd>{finding.source}</dd></div>
            <div><dt>Evidenssi tarkistettu</dt><dd>{formatDate(finding.lastReviewedAt)}</dd></div>
            <div><dt>Seuranta hyväksytty</dt><dd>{formatDate(monitoring.consentedAt)}</dd></div>
            <div><dt>Seuraava määräaikainen tarkistus</dt><dd>{formatDate(monitoring.nextReviewAt)}</dd></div>
          </dl>
          <h4>Huomiohistoria</h4>
          {monitoring.observations.length ? (
            <ul className="plain-list">
              {monitoring.observations.map((observation) => (
                <li key={observation.id}>
                  {formatDate(observation.createdAt)}: {observation.title} <StatusBadge status={observation.status} />{' '}
                  <button type="button" className="link-button" onClick={() => onWhyNow(observation.id)}>
                    Miksi huomio syntyi?
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p>Ei huomioita.</p>
          )}
          {monitoring.active && (
            <button type="button" className="btn-secondary" disabled={busy} onClick={() => onStop(monitoring.id)}>
              Lopeta seuranta
            </button>
          )}
        </div>
      )}
    </article>
  );
}
