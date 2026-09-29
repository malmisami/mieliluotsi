import { CheckIcon, CrossIcon } from '../../icons';
import { flagText, formatDate, formatValue, StatusBadge } from '../labels';
import type { HealthEvent, Observation } from '../types';

function eventText(event: HealthEvent) {
  const flag = flagText(event.abnormalFlag);
  return `${event.displayName}${formatValue(event) ? `: ${formatValue(event)}` : ''} (${formatDate(event.date)})${flag ? ` · ${flag}` : ''}${event.confirmedByUser ? ' · käyttäjän vahvistama' : ''}`;
}

export default function WhyNowCard({ observation, disclaimer }: { observation: Observation; disclaimer: string }) {
  const supporting = [...observation.supportingEvents].sort((a, b) => (a.date + a.id).localeCompare(b.date + b.id));
  const newest = supporting[supporting.length - 1];
  const earlier = [
    ...supporting.slice(0, -1),
    ...observation.previousEvents.filter((e) => !supporting.some((s) => s.id === e.id)),
  ];

  return (
    <details className="why-now-card" open>
      <summary>Miksi nyt? – erittely</summary>
      <p className="disclaimer-box" role="note"><strong>{disclaimer}</strong></p>
      <p><StatusBadge status={observation.status} /></p>
      <dl className="fact-list">
        <div>
          <dt>Geneettinen löydös</dt>
          <dd>{observation.finding ? `${observation.finding.title} · ${observation.finding.classification}` : '–'}</dd>
        </div>
        <div>
          <dt>Uusi terveystapahtuma</dt>
          <dd>{newest ? eventText(newest) : '–'}</dd>
        </div>
        <div>
          <dt>Aiempi terveystieto</dt>
          <dd>{earlier.length ? <ul>{earlier.map((e) => <li key={e.id}>{eventText(e)}</li>)}</ul> : 'Ei aiempaa seurantaan liittyvää tietoa.'}</dd>
        </div>
        <div>
          <dt>Sääntö, joka aktivoitui</dt>
          <dd>
            <ul>
              {observation.rules.map((rule) => (
                <li key={rule.id}>
                  <code>{rule.id}</code> – {rule.name}
                  {rule.demoNotice && <><br /><small className="muted">{rule.demoNotice}</small></>}
                </li>
              ))}
            </ul>
          </dd>
        </div>
        <div>
          <dt>Käytetty evidenssi</dt>
          <dd>{observation.source} · {observation.evidenceLevelLabel}</dd>
        </div>
        <div>
          <dt>Löydöksen vahvistustila</dt>
          <dd>{observation.confirmationLabel}</dd>
        </div>
        <div>
          <dt>Puuttuvat tiedot</dt>
          <dd>{observation.missingInformation.length ? <ul>{observation.missingInformation.map((m) => <li key={m}>{m}</li>)}</ul> : 'Ei tiedossa olevia puuttuvia tietoja.'}</dd>
        </div>
        <div>
          <dt>Mitä järjestelmä teki</dt>
          <dd><ul className="check-list">{observation.systemDid.map((item) => <li key={item}><CheckIcon size={18} className="icon-yes" /><span>{item}</span></li>)}</ul></dd>
        </div>
        <div>
          <dt>Mitä järjestelmä ei tehnyt</dt>
          <dd><ul className="check-list">{observation.systemDidNot.map((item) => <li key={item}><CrossIcon size={18} className="icon-no" /><span>{item}</span></li>)}</ul></dd>
        </div>
      </dl>
    </details>
  );
}
