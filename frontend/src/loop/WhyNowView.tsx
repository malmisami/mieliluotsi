import { useEffect, useRef } from 'react';
import { ArrowLeftIcon, CheckIcon, CrossIcon } from '../icons';
import { flagText, formatDate, formatValue, StatusBadge, SyntheticTag } from './labels';
import type { Observation } from './types';

interface Props {
  observation: Observation;
  onBack: () => void;
  onSummary: (observationId: string) => void;
}

export default function WhyNowView({ observation, onBack, onSummary }: Props) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => headingRef.current?.focus(), []);
  const { finding, event } = observation;

  return (
    <section className="panel why-now" aria-labelledby="why-now-title">
      <button type="button" className="btn-secondary back-button" onClick={onBack}><ArrowLeftIcon size={18} /> Palaa seurantaan</button>
      <h2 id="why-now-title" tabIndex={-1} ref={headingRef}>Miksi nyt?</h2>
      <p>
        {observation.title} <StatusBadge status={observation.status} /> <SyntheticTag />
      </p>

      <p className="disclaimer-box" role="note">
        <strong>{observation.disclaimer}</strong>
      </p>

      <p className="explanation">
        {observation.explanation}
        <br />
        <small className="muted">
          Selitysteksti: {observation.explanationSource === 'llm' ? 'tekoälyn muotoilema rakenteisesta päätöksestä' : 'valmis tekstipohja'}. Päätös on tehty säännöllä.
        </small>
      </p>

      <div className="why-grid">
        <div className="why-block">
          <h3>Geneettinen löydös</h3>
          {finding && (
            <dl className="fact-list">
              <div><dt>Löydös</dt><dd>{finding.title}</dd></div>
              <div><dt>Geeni / variantti</dt><dd>{finding.gene} · {finding.variant}</dd></div>
              <div><dt>Luokitus</dt><dd>{finding.classification}</dd></div>
            </dl>
          )}
        </div>
        <div className="why-block">
          <h3>Uusi terveystapahtuma</h3>
          {event && (
            <dl className="fact-list">
              <div><dt>Tapahtuma</dt><dd>{event.displayName} {formatValue(event)}</dd></div>
              <div><dt>Päivämäärä</dt><dd>{formatDate(event.date)}</dd></div>
              <div><dt>Poikkeamamerkintä</dt><dd>{flagText(event.abnormalFlag) ?? '–'}</dd></div>
              <div><dt>Tapahtuman lähde</dt><dd>{event.source}</dd></div>
            </dl>
          )}
        </div>
      </div>

      <dl className="fact-list why-facts">
        <div><dt>Tietojen välinen yhteys</dt><dd>{observation.connection}</dd></div>
        <div>
          <dt>Käytetty sääntö</dt>
          <dd>
            <code>{observation.rule.id}</code> – {observation.rule.name}
            <br />
            <small>{observation.rule.description}</small>
          </dd>
        </div>
        <div><dt>Käytetty lähde</dt><dd>{observation.source}</dd></div>
        <div><dt>Evidenssin taso</dt><dd>{observation.evidenceLevelLabel}</dd></div>
        <div><dt>Löydöksen vahvistustila</dt><dd>{observation.confirmationLabel}</dd></div>
      </dl>

      <div className="why-grid">
        <div className="why-block">
          <h3>Mitä tietoja puuttuu</h3>
          <ul>{observation.missingInformation.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
        <div className="why-block">
          <h3>Mitä järjestelmä teki</h3>
          <ul className="check-list">
            {observation.systemDid.map((item) => <li key={item}><CheckIcon size={18} className="icon-yes" /><span>{item}</span></li>)}
          </ul>
        </div>
        <div className="why-block">
          <h3>Mitä järjestelmä ei tehnyt</h3>
          <ul className="check-list">
            {observation.systemDidNot.map((item) => <li key={item}><CrossIcon size={18} className="icon-no" /><span>{item}</span></li>)}
          </ul>
        </div>
      </div>

      <div className="row">
        {observation.status !== 'resolved' && observation.status !== 'dismissed' && observation.status !== 'additional_information_needed' && (
          <button type="button" onClick={() => onSummary(observation.id)}>Muodosta yhteenveto ammattilaiselle</button>
        )}
        <button type="button" className="btn-secondary" onClick={onBack}>Palaa takaisin</button>
      </div>
    </section>
  );
}
