import { fmtDate } from '../format';
import { ArrowRightIcon, CheckIcon, GridIcon, StethoscopeIcon } from '../icons';
import { Pill } from '../components/ui';
import { useClientUI } from './ClientApp';
import { PathSteps } from './HomeTab';
import MatchingTab from './MatchingTab';

/* "Hoitopolku": the original pathway stays at the centre – waiting with support, finding the right therapist, therapy with
   therapist-guided support between sessions, and follow-up after therapy. */

export default function PathTab() {
  const { client } = useClientUI();
  return (
    <div className="cx-screen cx-path-screen">
      <h1 className="cx-title">Hoitopolku</h1>
      <PathSteps phase={client.phase} />
      <p className="cx-fine">{client.stateLabel}{client.waiting.daysWaiting !== null ? ` · ${client.waiting.daysWaiting} pv avun hakemisesta` : ''}</p>

      <ModeCard />

      <section className="cx-section">
        <h2 className="cx-h2">Terapeutti</h2>
        <MatchingTab embedded />
      </section>
    </div>
  );
}

function ModeCard() {
  const { client, openTab } = useClientUI();
  const mode = client.mode;
  const therapy = mode.mode === 'therapy_support';
  const aftercare = mode.mode === 'aftercare_support';
  // While waiting there is nothing for Sami to act on here; the card appears once the therapist sets the support.
  if (!therapy && !aftercare) return null;
  return (
    <section className={`cx-modecard ${therapy ? 'is-therapy' : 'is-aftercare'}`}>
      <p className="cx-eyebrow">{therapy ? <StethoscopeIcon size={14} /> : <CheckIcon size={14} />} Nyt</p>
      <p className="cx-modecard-title">{mode.title}</p>
      <p className="cx-fine">Ohjaa: {mode.controlledBy}</p>
      {mode.statement && <p className="cx-modecard-statement">{mode.statement}</p>}
      {therapy && mode.configured && (
        <dl className="cx-dl">
          <div><dt>Päätavoite</dt><dd>{mode.primaryGoal}</dd></div>
          {mode.homework && <div><dt>Välitehtävä</dt><dd>{mode.homework.title}{mode.homework.note ? ` – ${mode.homework.note}` : ''}</dd></div>}
          {mode.allowedTools && mode.allowedTools.length > 0 && (
            <div><dt>Ohjatut harjoitukset</dt><dd className="cx-chips-inline">{mode.allowedTools.map((t) => <span key={t.id} className="cx-tag">{t.title}</span>)}</dd></div>
          )}
          <div><dt>Omahoito</dt><dd className="cx-chips-inline">{mode.allowedActivities?.map((a) => <span key={a.id} className="cx-tag">{a.title}</span>)}</dd></div>
          <div><dt>Check-in</dt><dd>{mode.checkIns} · seurataan: {mode.track}</dd></div>
          {mode.doNotAddress && <div><dt>Käsitellään tapaamisissa</dt><dd>{mode.doNotAddress}</dd></div>}
        </dl>
      )}
      {aftercare && (
        <dl className="cx-dl">
          {mode.maintenance && <div><dt>Ylläpitosuunnitelma</dt><dd>{mode.maintenance}</dd></div>}
          {mode.warningSigns && <div><dt>Merkit, joihin reagoida</dt><dd>{mode.warningSigns}</dd></div>}
          <div><dt>Seuranta</dt><dd>Mieliala ja ahdistus {mode.checkIns}</dd></div>
          {mode.allowedTools && mode.allowedTools.length > 0 && (
            <div><dt>Harjoitukset</dt><dd className="cx-chips-inline">{mode.allowedTools.map((t) => <span key={t.id} className="cx-tag">{t.title}</span>)}</dd></div>
          )}
        </dl>
      )}
      {aftercare && (
        <button type="button" className="cx-btn cx-btn-dark cx-btn-block" onClick={() => openTab('harjoitukset')}>
          <GridIcon size={17} /> Siirry harjoituksiin <ArrowRightIcon size={16} />
        </button>
      )}
      {therapy && mode.configured && <Pill tone="violet">Terapeutin määrittämä · v{mode.version} · {fmtDate(mode.configuredAt)}</Pill>}
    </section>
  );
}
