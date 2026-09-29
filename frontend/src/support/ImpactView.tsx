import { useEffect, useState } from 'react';
import type { LoopDashboard } from '../loop/types';
import { supportApi } from './api';
import type { CohortAggregate } from './types';

const fmt = (value: number | null | undefined, digits = 0) =>
  value === null || value === undefined ? '–' : value.toLocaleString('fi-FI', { maximumFractionDigits: digits, minimumFractionDigits: digits });

function Tile({ value, label, note }: { value: string; label: string; note?: string }) {
  return (
    <div className="stat impact-tile" role="listitem">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
      {note && <span className="impact-note">{note}</span>}
    </div>
  );
}

interface Bar {
  key: string;
  label: string;
  count: number;
}

/** Single-series horizontal bars: one hue, value at the tip, hover/focus tooltip, table view for every value. */
function BarList({ title, bars, total }: { title: string; bars: Bar[]; total: number }) {
  const [active, setActive] = useState<string | null>(null);
  const max = Math.max(1, ...bars.map((b) => b.count));
  const titleId = `bars-${title.replace(/\s+/g, '-').toLowerCase()}`;
  return (
    <figure className="bar-figure" aria-labelledby={titleId}>
      <figcaption id={titleId}>{title}</figcaption>
      <ul className="bar-list">
        {bars.map((bar) => {
          const share = total ? (bar.count / total) * 100 : 0;
          return (
            <li key={bar.key} className="bar-row">
              <span className="bar-label">{bar.label}</span>
              <span
                className="bar-track"
                tabIndex={0}
                aria-label={`${bar.label}: ${fmt(bar.count)} (${fmt(share, 1)} %)`}
                onMouseEnter={() => setActive(bar.key)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(bar.key)}
                onBlur={() => setActive(null)}
              >
                <span className="bar-mark" style={{ width: `${(bar.count / max) * 100}%` }} />
                <span className="bar-value">{fmt(bar.count)}</span>
                {active === bar.key && (
                  <span className="bar-tooltip" role="tooltip">
                    <strong>{bar.label}</strong>
                    <span>{fmt(bar.count)} henkilöä · {fmt(share, 1)} %</span>
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      <details className="bar-table">
        <summary>Näytä taulukkona</summary>
        <table>
          <thead><tr><th scope="col">Luokka</th><th scope="col">Henkilöitä</th><th scope="col">Osuus</th></tr></thead>
          <tbody>
            {bars.map((bar) => (
              <tr key={bar.key}><td>{bar.label}</td><td>{fmt(bar.count)}</td><td>{fmt(total ? (bar.count / total) * 100 : 0, 1)} %</td></tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

/** Light impact view for a pilot: simulated figures only, never presented as clinical results. */
export default function ImpactView({ dashboard }: { dashboard: LoopDashboard }) {
  const m = dashboard.support.impact;
  const [cohort, setCohort] = useState<CohortAggregate | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    supportApi.cohortImpact().then(setCohort).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="impact-view">
      <section className="panel" aria-labelledby="impact-title">
        <h2 id="impact-title">Vaikuttavuus</h2>
        <p className="synthetic-banner-inline" role="note">
          Simuloituja lukuja: näin pilotissa mitattaisiin. Ei kliinisiä tuloksia.
        </p>
        {dashboard.support.available && (
          <>
            <h3>Demotapaus: {dashboard.support.person.name}</h3>
            <div className="stat-grid stat-grid-4" role="list">
              <Tile value={fmt(m.activePlans)} label="Aktiiviset seurantasuunnitelmat" />
              <Tile value={`${fmt(m.selfCareTasksDone)}/${fmt(m.selfCareTasksAgreed)}`} label="Toteutuneet / sovitut omahoitotehtävät" />
              <Tile value={fmt(m.reminders)} label="Agentin muistutukset" />
              <Tile value={fmt(m.microInterventions)} label="Mikrointerventiot (check-init)" note={`${fmt(m.adaptiveFollowUps)} mukautettua jatkokysymystä`} />
              <Tile value={fmt(m.assessments)} label="Automaattiset hoidon tarpeen arviot"
                note={m.assessments ? `${fmt(m.assessmentsAutomated)} automaattisesti · ${m.avgMinutesToAssessment === 0 ? 'arvio heti' : `keskim. ${fmt(m.avgMinutesToAssessment)} min`}` : undefined} />
              <Tile value={`${fmt(m.assessmentsConfirmed)} / ${fmt(m.assessmentsChanged)}`} label="Ammattilaisen vahvistamat / muutetut" />
              <Tile value={fmt(m.humanReviewRequests)} label="Pyydetyt ammattilaisen arviot" />
              <Tile value={fmt(m.escalations)} label="Ohjaukset ammattilaiselle" />
              <Tile value={`${fmt(m.escalationsAppropriate)}/${fmt(m.escalationsDecided)}`} label="Oikeiksi vahvistetut kiireellisyysarviot" />
              <Tile value={fmt(m.resolvedWithoutEscalation)} label="Ratkaistu ilman eskalaatiota" />
              <Tile value={m.avgDaysSignalToAction === null ? '–' : `${fmt(m.avgDaysSignalToAction, 1)} pv`} label="Keskim. aika havainnosta toimeen" />
              <Tile value={fmt(m.waitingForProfessional)} label="Odottaa ammattilaisen käsittelyä" />
              <Tile value={m.usefulnessAvg === null ? '–' : `${fmt(m.usefulnessAvg, 1)}/5`} label="Koettu hyödyllisyys" note={`${fmt(m.usefulnessAnswers)} vastausta`} />
              <Tile value={fmt(m.goalAdjustments)} label="Käyttäjän kanssa sovitetut tavoitteet" />
            </div>
          </>
        )}
      </section>

      <section className="panel" aria-labelledby="cohort-title">
        <h2 id="cohort-title">Synteettinen pilottikohortti</h2>
        <p className="muted small">Lasketaan palvelimella paloina. Selaimeen tulevat vain kootut luvut.</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        {!cohort && !error && <p role="status">Lasketaan kohortin lukuja…</p>}
        {cohort && (
          <>
            <div className="stat-grid stat-grid-4" role="list">
              <Tile value={fmt(cohort.people)} label="Henkilöä (synteettinen)" />
              <Tile value={fmt(cohort.activePlans)} label="Aktiiviset suunnitelmat" />
              <Tile value={`${fmt((cohort.selfCareTasksDone / Math.max(1, cohort.selfCareTasksAgreed)) * 100, 0)} %`} label="Sovituista omahoitotehtävistä toteutui" />
              <Tile value={fmt(cohort.microInterventions)} label="Mikrointerventiot" />
              <Tile value={fmt(cohort.assessments)} label="Automaattisia arvioita" />
              <Tile value={cohort.assessmentsConfirmedShare === null || cohort.assessmentsConfirmedShare === undefined ? '–' : `${fmt(cohort.assessmentsConfirmedShare * 100, 0)} %`}
                label="Vahvistettujen osuus" note={`${fmt(cohort.humanReviewRequests)} pyydettyä ammattilaisen arviota`} />
              <Tile value={fmt(cohort.escalations)} label="Eskalaatiot" />
              <Tile value={`${fmt((cohort.escalationsAppropriate / Math.max(1, cohort.escalations)) * 100, 0)} %`} label="Eskalaatioista aiheellisia" />
              <Tile value={fmt(cohort.resolvedWithoutEscalation)} label="Ratkaistu ilman eskalaatiota" />
              <Tile value={`${fmt(cohort.avgDaysSignalToAction, 1)} pv`} label="Keskim. aika havainnosta toimeen" />
            </div>
            <div className="bar-grid">
              <BarList title="Suunnitelmien tila" total={cohort.people} bars={cohort.byStatus.map((s) => ({ key: s.status, label: s.label, count: s.count }))} />
              <BarList title="Seurantateemat" total={cohort.people} bars={cohort.byTheme.map((t) => ({ key: t.theme, label: t.theme, count: t.count }))} />
            </div>
          </>
        )}
      </section>
    </div>
  );
}
