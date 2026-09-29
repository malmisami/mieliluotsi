import { useState } from 'react';
import { CheckIcon, InfoIcon, StethoscopeIcon } from '../icons';
import { UrgencyBadge } from './labels';
import type { AutomationPolicy } from './types';

const SEEN_KEY = 'hta-notice-seen';

function readSeen(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === '1';
  } catch {
    return false;
  }
}

function markSeen() {
  try {
    window.localStorage.setItem(SEEN_KEY, '1');
  } catch {
    // storage unavailable (private window): the notice simply opens again next time
  }
}

interface Props {
  automation: AutomationPolicy;
  /** Open the description the first time this viewer sees it (remembered per browser). */
  openFirstTime?: boolean;
}

/** "Näin automaattinen hoidon tarpeen arvio toimii": the published description of the automation. */
export default function AutomationNotice({ automation, openFirstTime = false }: Props) {
  const [open] = useState(() => openFirstTime && !readSeen());
  return (
    <details className="automation-notice" open={open} onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) markSeen(); }}>
      <summary>Näin automaattinen hoidon tarpeen arvio toimii</summary>
      <div className="automation-notice-body">
        <p className="automation-legal" role="note">
          <InfoIcon size={16} /> <span><strong>Oletus:</strong> {automation.legalBasis}. Lakimuutos on vasta valmistelussa.</span>
        </p>

        <h4>Periaatteet</h4>
        <ul className="check-list">
          {automation.principles.map((line) => <li key={line}><CheckIcon size={16} /> {line}</li>)}
        </ul>

        <h4>Kiireellisyysluokat</h4>
        <div className="table-wrap">
          <table className="urgency-table">
            <caption className="visually-hidden">Automaattisen arvion kiireellisyysluokat</caption>
            <thead>
              <tr><th scope="col">Luokka</th><th scope="col">Mitä tapahtuu</th><th scope="col">Käsittely</th></tr>
            </thead>
            <tbody>
              {automation.urgencyClasses.map((cls) => (
                <tr key={cls.id}>
                  <td><UrgencyBadge urgency={cls.id} label={cls.label} /></td>
                  <td>{cls.careNeedLabel}</td>
                  <td>{cls.handlingTime}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {automation.whatStaysHuman.length > 0 && (
          <>
            <h4><StethoscopeIcon size={18} /> Ammattilainen päättää aina</h4>
            <ul>{automation.whatStaysHuman.map((line) => <li key={line}>{line}</li>)}</ul>
          </>
        )}
        {automation.sampling.description && <p className="muted small">{automation.sampling.description}</p>}
        <p className="small">
          {automation.responsiblePerson} · versio {automation.version}
        </p>
        <p className="small"><strong>{automation.rightsSentence}</strong></p>
      </div>
    </details>
  );
}
