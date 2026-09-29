import { useEffect, useState } from 'react';
import { LockIcon, ShieldIcon } from '../icons';
import { formatDate } from '../loop/labels';
import type { LoopDashboard } from '../loop/types';
import { supportApi } from './api';
import AutomationNotice from './AutomationNotice';
import type { ConsentView as ConsentData } from './types';
import { useRunner } from './useRunner';

interface Props {
  dashboard: LoopDashboard;
  setDashboard: (dashboard: LoopDashboard) => void;
}

const SOURCE_HELP: Record<string, string> = {
  diagnoses: 'Seurantateemat perustuvat diagnooseihin.',
  medications: 'Vain taustatietona – lääkitykseen ei oteta kantaa.',
  careEpisodes: 'Kertovat, mitä on jo käsitelty ammattilaisen kanssa.',
  professionalNotes: 'Mitä kanssasi on sovittu.',
  interactionEvents: 'Toistuvat yhteydenotot voivat kertoa tuen tarpeesta.',
  measurements: 'Kotimittaukset ja laboratoriotulokset.',
  selfReportedData: 'Omat ilmoituksesi ja vastauksesi.',
  geneticInsights: 'Vapaaehtoinen. Vain ammattilaisen hyväksymä havainto.',
};

/** Gate 3: the user decides what may be used, how and when the agent may get in touch, and pauses. */
export default function ConsentView({ dashboard, setDashboard }: Props) {
  const consent = dashboard.support.consent;
  const [draft, setDraft] = useState<ConsentData>(consent);
  const { busy, error, message, run } = useRunner(setDashboard);

  useEffect(() => setDraft(consent), [consent]);

  if (!dashboard.support.available) {
    return <section className="panel"><h2>Suostumukset</h2><p>Seurannan tietoja ei ole ladattu.</p></section>;
  }
  const changed = JSON.stringify({ ...draft, history: [] }) !== JSON.stringify({ ...consent, history: [] });

  function save() {
    run(
      () => supportApi.updateConsent({
        dataSources: draft.dataSources,
        proactiveContact: draft.proactiveContact,
        maxContactsPerWeek: draft.maxContactsPerWeek,
        quietHours: draft.quietHours,
        channel: draft.channel,
        showGeneticDetails: draft.showGeneticDetails,
        pausedUntil: draft.pausedUntil || null,
        automatedAssessment: draft.automatedAssessment,
      }),
      () => 'Asetukset tallennettu. Muutos näkyy agentin toimintalokissa.',
    );
  }

  return (
    <div className="consent-layout">
      <section className="panel" aria-labelledby="consent-title">
        <div className="panel-heading">
          <span className="panel-heading-icon" aria-hidden="true"><ShieldIcon size={48} /></span>
          <h2 id="consent-title">Suostumukset</h2>
        </div>
        <p className="lead">Sinä päätät, mitä tietoja käytetään, milloin Hyvinvointikumppani saa ottaa yhteyttä ja saako se tehdä hoidon tarpeen arvion automaattisesti.</p>

        <form noValidate onSubmit={(e) => { e.preventDefault(); save(); }}>
          <fieldset className="consent-group">
            <legend>Tietolähteet, joita saa käyttää</legend>
            {Object.entries(consent.sourceLabels).map(([kind, label]) => (
              <label key={kind} className="toggle-row">
                <input
                  type="checkbox"
                  checked={draft.dataSources[kind] ?? false}
                  onChange={(e) => setDraft({ ...draft, dataSources: { ...draft.dataSources, [kind]: e.target.checked } })}
                />
                <span>
                  <strong>{label}</strong>
                  <small>{SOURCE_HELP[kind]}</small>
                </span>
              </label>
            ))}
          </fieldset>

          <fieldset className="consent-group">
            <legend>Yhteydenotot</legend>
            <label className="toggle-row">
              <input type="checkbox" checked={draft.proactiveContact} onChange={(e) => setDraft({ ...draft, proactiveContact: e.target.checked })} />
              <span>
                <strong>Hyvinvointikumppani saa ottaa yhteyttä oma-aloitteisesti</strong>
                <small>Muistutukset ja lyhyet tarkistukset. Turvaviestit tulevat aina.</small>
              </span>
            </label>
            <div className="consent-fields">
              <label>
                Enintään viikossa
                <select value={draft.maxContactsPerWeek} onChange={(e) => setDraft({ ...draft, maxContactsPerWeek: Number(e.target.value) })}>
                  {[0, 1, 2, 3, 4, 5, 7].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <label>
                Hiljainen aika alkaa
                <input type="time" value={draft.quietHours.start} onChange={(e) => setDraft({ ...draft, quietHours: { ...draft.quietHours, start: e.target.value } })} />
              </label>
              <label>
                Hiljainen aika päättyy
                <input type="time" value={draft.quietHours.end} onChange={(e) => setDraft({ ...draft, quietHours: { ...draft.quietHours, end: e.target.value } })} />
              </label>
              <label>
                Tauko päivään asti
                <input type="date" min={dashboard.currentDate} value={draft.pausedUntil ?? ''} onChange={(e) => setDraft({ ...draft, pausedUntil: e.target.value || null })} />
              </label>
            </div>
            <p className="muted small">
              Viestit lähetetään klo {consent.deliveryTime}. Viimeisen viikon aikana yhteydenottoja: {consent.contactsLastWeek}.
            </p>
          </fieldset>

          <fieldset className="consent-group">
            <legend>Kanava</legend>
            <div className="radio-row">
              {Object.entries(consent.channelLabels).map(([key, label]) => (
                <label key={key}>
                  <input type="radio" name="channel" value={key} checked={draft.channel === key} onChange={() => setDraft({ ...draft, channel: key as ConsentData['channel'] })} />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="consent-group">
            <legend>Automaattinen hoidon tarpeen arvio</legend>
            <label className="toggle-row">
              <input type="checkbox" checked={Boolean(draft.automatedAssessment)} onChange={(e) => setDraft({ ...draft, automatedAssessment: e.target.checked })} />
              <span>
                <strong>Hyväksyn, että hoidon tarpeen ja kiireellisyyden arvio tehdään automaattisesti</strong>
                <small>Arvio perustuu sääntöihin, ei kielimalliin. Saat aina tiedon, että arvio on automaattinen, ja voit milloin tahansa pyytää ammattilaisen tekemän arvion. Hätätilanteet eivät kuulu automaattisen arvion piiriin: soita 112.</small>
              </span>
            </label>
            <p className={`consent-state ${consent.automatedAssessment ? 'is-on' : 'is-off'}`}>
              {consent.automatedAssessment
                ? `Suostumus annettu${consent.automatedAssessmentInformedAt ? ` ${formatDate(consent.automatedAssessmentInformedAt)}` : ''}.`
                : 'Ei suostumusta: arviot ovat esiarvioita (Esiarvio – ammattilainen tekee arvion), ja ne ohjataan aina ammattilaiselle.'}
            </p>
            {dashboard.support.policy.automation && <AutomationNotice automation={dashboard.support.policy.automation} openFirstTime />}
          </fieldset>

          <fieldset className="consent-group">
            <legend>Perimätieto</legend>
            <label className="toggle-row">
              <input type="checkbox" checked={draft.showGeneticDetails} onChange={(e) => setDraft({ ...draft, showGeneticDetails: e.target.checked })} />
              <span>
                <strong>Näytä perimätiedon yksityiskohdat (esim. geenin nimi)</strong>
                <small>Pois päältä näet vain maininnan ”mahdollinen perimään liittyvä tekijä”, eikä tieto mene kielimallille.</small>
              </span>
            </label>
          </fieldset>

          <div className="row">
            <button type="submit" disabled={busy || !changed}>Tallenna asetukset</button>
            <button type="button" className="btn-secondary" disabled={busy || !changed} onClick={() => setDraft(consent)}>Peru muutokset</button>
          </div>
          <p className="live-message" aria-live="polite">{message}</p>
          {error && <p className="form-error" role="alert">{error}</p>}
        </form>
      </section>

      <aside className="panel" aria-labelledby="consent-records-title">
        <h2 id="consent-records-title">Annetut suostumukset</h2>
        <ul className="plain-list">
          {consent.records.map((record) => (
            <li key={record.id}><LockIcon size={16} /> <strong>{record.target}</strong><br /><span className="muted small">{record.status} · {formatDate(record.date)} · {record.channel}</span></li>
          ))}
        </ul>
        <details className="consent-history">
          <summary>Muutoshistoria ({consent.history.length})</summary>
          <ol className="history-list">
            {[...consent.history].reverse().map((item, i) => <li key={`${item.date}-${i}`}>{formatDate(item.date)}: {item.change}</li>)}
          </ol>
        </details>
      </aside>
    </div>
  );
}
