import { useEffect, useState } from 'react';
import { AlertIcon, CheckIcon, InfoIcon, LockIcon, PhoneIcon, PulseIcon, TrashIcon } from '../icons';
import { formatDate } from '../loop/labels';
import type { LoopDashboard } from '../loop/types';
import { wellbeingApi } from './api';
import { formatDateTime } from './format';
import TrendChart from './TrendChart';
import type { HealthObservation, WellbeingSummary } from './types';

interface Props {
  dashboard: LoopDashboard;
  setDashboard: (dashboard: LoopDashboard) => void;
  onOpenCompanion: () => void;
}

/** Hyvinvointidata: Apple Health as one more data source of the same wellbeing agent. Built around change against the
 * user's own baseline and the agreed monitoring areas - not a fitness dashboard. */
export default function WellbeingDataView({ dashboard, setDashboard, onOpenCompanion }: Props) {
  const [period, setPeriod] = useState(30);
  const [summary, setSummary] = useState<WellbeingSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [manage, setManage] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [pairing, setPairing] = useState<{ code: string; expiresAt: string } | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let cancelled = false;
    wellbeingApi.summary(period)
      .then((data) => { if (!cancelled) setSummary(data); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [period, dashboard]);

  async function run<T extends { dashboard: LoopDashboard }>(call: () => Promise<T>, done?: (result: T) => string) {
    setBusy(true);
    setError(null);
    try {
      const result = await call();
      setDashboard(result.dashboard);
      setMessage(done ? done(result) : '');
      return result;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function discuss(observation: HealthObservation) {
    const result = await run(() => wellbeingApi.discuss(observation.id));
    if (result) onOpenCompanion();
  }

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      setPairing(await wellbeingApi.pairingCode());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!summary) {
    return (
      <section className="panel">
        <h2>Hyvinvointidata</h2>
        {error ? <p className="form-error" role="alert">{error}</p> : <p role="status">Ladataan tietoja…</p>}
      </section>
    );
  }

  const connection = summary.connection;
  const connected = connection.status === 'connected';
  const observations = summary.observations;
  const monitoredTrends = summary.trends.filter((t) => t.monitored);
  const otherTrends = summary.trends.filter((t) => !t.monitored);

  return (
    <div className="wellbeing-view">
      <section className="panel wellbeing-head" aria-labelledby="wellbeing-title">
        <div className="panel-heading">
          <span className="panel-heading-icon" aria-hidden="true"><PulseIcon size={48} /></span>
          <h2 id="wellbeing-title">Hyvinvointidata</h2>
        </div>
        <p className="lead">
          Jatkuva tieto puhelimesta ja kellosta on yksi hyvinvointikumppanin tietolähteistä. Se ei korvaa terveystietoja, vaan
          näyttää, miten arkesi muuttuu omaan tasoosi verrattuna.
        </p>

        <div className={`health-source is-${connection.status}`}>
          <div className="health-source-main">
            <span className="health-source-icon" aria-hidden="true"><PhoneIcon size={26} /></span>
            <div>
              <p className="health-source-name">
                Apple Health
                {connected && <span className="support-badge support-tone-calm"><CheckIcon size={14} /> Yhdistetty</span>}
                {connection.status === 'disconnected' && <span className="support-badge support-tone-neutral">Yhteys katkaistu</span>}
                {connection.synthetic && <span className="support-badge support-tone-attention">Synteettinen testidata</span>}
              </p>
              {connected ? (
                <p className="muted small">
                  Viimeisin synkronointi {formatDateTime(connection.lastSyncAt)}
                  {summary.dataRange ? ` · päivittäiset yhteenvedot ${formatDate(summary.dataRange.from)}–${formatDate(summary.dataRange.to)}` : ''}
                  {connection.synthetic ? ' · ei oikeaa Apple Health -dataa' : ''}
                </p>
              ) : connection.status === 'disconnected' ? (
                <p className="muted small">Synkronointi on lopetettu, eikä hyvinvointikumppani käytä tietoja. Tuodut tiedot ovat tallessa, kunnes poistat ne.</p>
              ) : (
                <p className="small">Yhdistä iPhonesi terveystiedot hyvinvointikumppaniin. {summary.permissionText}</p>
              )}
            </div>
          </div>
          <div className="row health-source-actions">
            {connected && (
              <>
                <button type="button" disabled={busy} onClick={() => run(() => wellbeingApi.syncNow(), (r) => r.result.message ?? 'Synkronoitu.')}>
                  Synkronoi nyt
                </button>
                <button type="button" className="btn-secondary" aria-expanded={manage} onClick={() => setManage(!manage)}>Hallinnoi tietoja</button>
              </>
            )}
            {!connected && (
              <button type="button" disabled={busy} onClick={connect}>{connection.status === 'disconnected' ? 'Yhdistä uudelleen' : 'Yhdistä Apple Health'}</button>
            )}
            {!connected && summary.demoMode && (
              <button type="button" className="link-button" disabled={busy}
                onClick={() => run(() => wellbeingApi.useSynthetic(), () => 'Synteettinen testidata otettiin käyttöön.')}>
                Käytä synteettistä testidataa
              </button>
            )}
            {connection.status === 'disconnected' && (
              <button type="button" className="btn-secondary" aria-expanded={manage} onClick={() => setManage(!manage)}>Hallinnoi tietoja</button>
            )}
          </div>
        </div>

        {pairing && !connected && (
          <div className="pairing-box" role="region" aria-label="Apple Healthin yhdistäminen">
            <p><strong>Apple Health luetaan iPhonesta – selain ei pääse terveystietoihin.</strong></p>
            <ol>
              <li>Avaa iPhonessa Hyvinvointikumppani-sovellus (HealthKit-silta).</li>
              <li>Anna yhdistämiskoodi <strong className="pairing-code">{pairing.code.slice(0, 3)} {pairing.code.slice(3)}</strong> (voimassa klo {formatDateTime(pairing.expiresAt).split(' klo ')[1]} asti).</li>
              <li>Apple kysyy luvan jokaiselle tiedolle erikseen. Valitse, mitä saa lukea – vain lukuoikeus.</li>
            </ol>
            <p className="muted small">Puhelin lähettää vain päivittäiset yhteenvedot, ei yksittäisiä mittauksia. Koodi näytetään vain tässä.</p>
          </div>
        )}

        {!summary.consentAllowed && (
          <p className="notice small"><LockIcon size={18} /> Hyvinvointidatan käyttö on estetty Suostumuksissa, joten hyvinvointikumppani ei käytä näitä tietoja.</p>
        )}

        {manage && (
          <div className="manage-box" role="region" aria-label="Hallinnoi tietoja">
            <h3>Synkronoitavat tiedot</h3>
            <p className="muted small">{summary.permissionText} Pois valitut tiedot poistetaan myös tallennetuista yhteenvedoista.</p>
            <ul className="permission-list">
              {summary.metrics.map((metric) => (
                <li key={metric.id}>
                  <label>
                    <input type="checkbox" checked={metric.permitted} disabled={busy}
                      onChange={(e) => run(() => wellbeingApi.setPermissions({ [metric.id]: e.target.checked }))} />
                    {metric.label}
                  </label>
                </li>
              ))}
            </ul>
            {connection.devices.length > 0 && (
              <p className="muted small">Yhdistetyt laitteet: {connection.devices.map((d) => `${d.name} (${formatDateTime(d.pairedAt)})`).join(', ')}</p>
            )}
            <div className="row">
              {connected && (
                <button type="button" className="btn-secondary" disabled={busy}
                  onClick={() => run(() => wellbeingApi.disconnect(), () => 'Yhteys katkaistiin.')}>
                  Katkaise yhteys
                </button>
              )}
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => setConfirmDelete(true)}>
                <TrashIcon size={18} /> Poista Apple Health -tiedot
              </button>
            </div>
            {confirmDelete && (
              <div className="confirm-box" role="alertdialog" aria-labelledby="health-delete-title">
                <p id="health-delete-title" className="confirm-box-title"><AlertIcon size={20} /> Poistetaanko tuodut hyvinvointitiedot?</p>
                <p>Kaikki päivittäiset yhteenvedot ja niistä tehdyt havainnot poistetaan, ja yhteys katkaistaan. Toimintoa ei voi perua.</p>
                <div className="row">
                  <button type="button" className="btn-danger" disabled={busy}
                    onClick={async () => { await run(() => wellbeingApi.deleteData(), (r) => `Poistettiin ${r.result} päivän tiedot.`); setConfirmDelete(false); setManage(false); }}>
                    Kyllä, poista tiedot
                  </button>
                  <button type="button" className="btn-secondary" onClick={() => setConfirmDelete(false)}>Peruuta</button>
                </div>
              </div>
            )}
          </div>
        )}
        <p className="live-message" aria-live="polite">{message}</p>
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>

      {observations.length > 0 && (
        <section className="panel" aria-labelledby="observations-title">
          <h2 id="observations-title">Havainnot seurannastasi</h2>
          <div className="observation-list">
            {observations.map((observation) => (
              <article key={observation.id} className={`health-observation kind-${observation.kind}`}>
                <p className="health-observation-title">
                  {observation.kind === 'change' ? <InfoIcon size={20} /> : <CheckIcon size={20} />} {observation.title}
                  {observation.status === 'discussed' && <span className="support-badge support-tone-neutral">Käyty läpi</span>}
                </p>
                <p>{observation.summary}</p>
                <p className="muted small">{observation.areaNote}{observation.followUpAt ? ` Seuraan tilannetta ${formatDate(observation.followUpAt)} asti.` : ''}</p>
                <div className="row">
                  <button type="button" disabled={busy || !summary.inUse} onClick={() => discuss(observation)}>
                    {observation.status === 'discussed' ? 'Jatka keskustelua' : observation.kind === 'change' ? 'Selvitetään yhdessä' : 'Jatka keskustelua'}
                  </button>
                  {observation.status === 'new' && (
                    <button type="button" className="btn-secondary" disabled={busy} onClick={() => run(() => wellbeingApi.dismiss(observation.id))}>Ei nyt</button>
                  )}
                </div>
                <details className="why-details">
                  <summary>Miksi näen tämän?</summary>
                  <p>{observation.why.reason} <span className="muted">({observation.why.basis})</span></p>
                  <div className="findings-table-wrap">
                    <table className="findings-table why-table">
                      <thead><tr><th scope="col">Mittari</th><th scope="col">Viimeiset 7 päivää</th><th scope="col">Oma tasosi</th><th scope="col">Muutos</th></tr></thead>
                      <tbody>
                        {observation.why.lines.map((line) => (
                          <tr key={line.label}><th scope="row">{line.label}</th><td>{line.current}</td><td>{line.baseline}</td><td>{line.delta}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <ul className="plain-list small">
                    {observation.why.lines.filter((l) => l.consecutive).map((l) => <li key={l.label}>{l.consecutive}</li>)}
                    <li>{observation.why.period}</li>
                    {observation.why.rules.map((rule) => <li key={rule}>{rule}</li>)}
                    <li>{observation.why.source}</li>
                  </ul>
                </details>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="panel" aria-labelledby="monitoring-title">
        <h2 id="monitoring-title">Seurannassa</h2>
        <p className="muted small">Otan itse yhteyttä vain seurannassa olevista asioista. Muut muutokset näkyvät alla, mutta en nosta niitä esiin.</p>
        <ul className="monitoring-list">
          {summary.monitoring.map((area) => (
            <li key={area.id} className={area.active ? 'is-active' : ''}>
              <div>
                <strong>{area.label}</strong>
                <span className="muted small">{area.metrics.join(', ')} · {area.basis}</span>
              </div>
              {area.selectable ? (
                <label className="switch-label">
                  <input type="checkbox" checked={area.active} disabled={busy}
                    onChange={(e) => run(() => wellbeingApi.setMonitoring({ [area.id]: e.target.checked }))} />
                  {area.active ? 'Seurannassa' : 'Ei seurannassa'}
                </label>
              ) : <span className="support-badge support-tone-calm"><CheckIcon size={14} /> Seurannassa</span>}
            </li>
          ))}
        </ul>
      </section>

      {summary.today.length > 0 && (
        <section className="panel" aria-labelledby="today-title">
          <h2 id="today-title">Tänään <span className="muted small">{formatDate(summary.dataRange?.to)}</span></h2>
          <div className="today-grid">
            {summary.today.map((tile) => (
              <div key={tile.metric} className={`today-tile${tile.kind === 'concern' ? ' is-changed' : ''}`}>
                <span className="today-label">{tile.label}</span>
                <span className="today-value">{tile.value}</span>
                <span className="muted small">{tile.comparisonLabel}: {tile.comparison ?? '–'}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {summary.trends.length > 0 && (
        <section className="panel" aria-labelledby="trends-title">
          <div className="trends-head">
            <h2 id="trends-title">Trendit</h2>
            <div className="segmented" role="group" aria-label="Ajanjakso">
              {summary.periods.map((p) => (
                <button key={p.days} type="button" aria-pressed={period === p.days} onClick={() => setPeriod(p.days)}>{p.label}</button>
              ))}
            </div>
          </div>
          <p className="muted small">Katkoviiva on oma tasosi (90 päivää ennen viimeisintä kuukautta). {period >= 365 ? 'Pisteet ovat viikkokeskiarvoja.' : ''}</p>
          <div className="trend-grid-list">
            {(showAll ? [...monitoredTrends, ...otherTrends] : monitoredTrends.length ? monitoredTrends : otherTrends.slice(0, 4)).map((series) => (
              <div key={series.metric} className="trend-card">
                <p className="trend-card-title">
                  {series.label}
                  {series.change === 'concern' && <span className="support-badge direction-badge direction-adjust">Muutos omaan tasoon</span>}
                  {series.change === 'positive' && <span className="support-badge direction-badge direction-continue">Myönteinen muutos</span>}
                </p>
                <p className="muted small">7 pv: {series.currentText ?? '–'} · oma taso: {series.baselineText ?? '–'}</p>
                <TrendChart series={series} />
              </div>
            ))}
          </div>
          {otherTrends.length > 0 && monitoredTrends.length > 0 && (
            <button type="button" className="link-button" aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>
              {showAll ? 'Näytä vain seurannassa olevat' : `Näytä muut mittarit (${otherTrends.length})`}
            </button>
          )}
        </section>
      )}

      {connected && (
        <section className="panel" aria-labelledby="changes-title">
          <h2 id="changes-title">Merkittävät muutokset</h2>
          {summary.changes.length ? (
            <ul className="change-list">
              {summary.changes.map((change) => (
                <li key={change.metric} className={`kind-${change.kind}`}>
                  <span>{change.text} <strong>{change.delta}</strong></span>
                  <span className="muted small">{change.area ? `Seurannassa: ${change.area}` : 'Ei seurannassa'}</span>
                </li>
              ))}
            </ul>
          ) : <p>Ei merkittäviä muutoksia omaan tasoosi verrattuna.</p>}
          <p className="muted small">Muutos poikkeaa omasta tavanomaisesta tasostasi. Se ei ole diagnoosi, vaan syy katsoa tilannetta yhdessä.</p>
        </section>
      )}

      {summary.agentContext && (
        <details className="panel agent-context">
          <summary><h2>Mitä hyvinvointikumppani saa tietää</h2></summary>
          <p className="muted small">
            Agentti ja valinnainen kielimalli saavat hyvinvointidatasta vain tämän tiiviin yhteenvedon – ei päivittäistä historiaa eikä
            yksittäisiä mittauksia. Se yhdistetään terveystietoihin, perimätiedon taustatietoon ja seurantasuunnitelmiin.
          </p>
          <pre className="json">{JSON.stringify(summary.agentContext, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
