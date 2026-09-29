import { useMemo, useState } from 'react';
import { formatDate } from '../loop/labels';
import type { LoopDashboard } from '../loop/types';
import { ACTOR_LABELS, ASSESSMENT_OUTCOME_LABELS } from './labels';
import type { AuditEntry } from './types';

interface Props {
  dashboard: LoopDashboard;
  /** The client's copy hides gene names when genetic details are hidden; the professional sees the full line. */
  role: 'client' | 'professional';
}

// actions that are not agent actions of a plan (the policy's action list names the rest)
const ACTION_LABELS: Record<string, string> = {
  link_genetics: 'Linkitys DNA-analyysiin',
  unlink_genetics: 'Linkityksen purku',
  home_monitoring_result: 'Kotiseurannan yhteenveto',
  home_monitoring_reading: 'Kotiseurannan mittaus kirjattu',
  no_response: 'Ei vastausta',
  'answer:home_monitoring': 'Vastaus kotiseurantaehdotukseen',
};

const OUTCOME_LABELS: Record<string, string> = {
  linked: 'Linkitetty DNA-analyysiin',
  unlinked: 'Linkitys purettu',
  deferred: 'Lykätty (suostumus)',
  goal_adjusted: 'Tavoite sovitettu',
  expired: 'Ehdotus vanheni',
  continue: 'Jatketaan omahoitoa',
  adjust: 'Muutetaan suunnitelmaa',
  professional: 'Tarvitaan ammattilaista',
  incomplete: 'Liian vähän mittauksia',
};

/** Audit trail: every observation, decision, action, answer, escalation and professional decision. */
export default function AuditView({ dashboard, role }: Props) {
  const audit = dashboard.support.audit;
  const plans = dashboard.support.plans;
  const policy = dashboard.support.policy;
  const [planFilter, setPlanFilter] = useState('');
  const [actorFilter, setActorFilter] = useState('');
  const [showLegacy, setShowLegacy] = useState(false);
  const entries = useMemo(
    // audit is missing after "Tyhjennä tiedot" (support.available false); the early return below handles that view
    () => (audit?.entries ?? []).filter((e) => (!planFilter || e.planId === planFilter) && (!actorFilter || e.actor === actorFilter)),
    [audit?.entries, planFilter, actorFilter],
  );
  const planName = (id: string | null) => plans.find((p) => p.id === id)?.name ?? '–';
  const text = (entry: { detail: string; detailMasked?: string }) => (role === 'client' ? entry.detailMasked ?? entry.detail : entry.detail);

  function result(entry: AuditEntry) {
    if (entry.userResponse) return entry.userResponse;
    if (entry.professionalDecision) return entry.professionalDecision;
    const outcome = entry.outcome;
    if (!outcome) return '–';
    if (outcome.startsWith('esc-')) return 'Eskalaatio muodostettu';
    const urgencyLabels: Record<string, string> = policy?.urgencyLabels ?? {};
    return OUTCOME_LABELS[outcome] ?? ASSESSMENT_OUTCOME_LABELS[outcome] ?? urgencyLabels[outcome]
      ?? policy?.categoryLabels[outcome] ?? policy?.statusLabels[outcome] ?? outcome;
  }

  if (!dashboard.support.available) {
    return <section className="panel"><h2>Agentin toiminta</h2><p>Seurannan tietoja ei ole ladattu.</p></section>;
  }
  return (
    <div className="audit-view">
      <section className="panel" aria-labelledby="flow-title">
        <h2 id="flow-title">Agentin toiminta</h2>
        <p className="lead">Jokainen havainto, sääntö, toimi, vastaus ja päätös kirjataan – mitään ei tapahdu näkymättömissä.</p>
        <h3>Toimintaketjut</h3>
        {audit.chains.length === 0 && <p>Ei vielä toimintaketjuja. Käynnistä agenttikierros tai simuloi seuraava viikko.</p>}
        <ol className="chain-list">
          {audit.chains.map((chain) => (
            <li key={chain.id} className="chain">
              <p className="chain-title"><strong>{chain.plan ?? 'Seuranta'}</strong> · {formatDate(chain.date)}</p>
              <ol className="chain-flow" aria-label={chain.flow.map((step) => step.label).join(', ')}>
                {chain.flow.map((step) => (
                  <li key={step.key} className={step.text ? 'is-done' : 'is-empty'}>
                    <span className="chain-step-label">{step.label}</span>
                    <span className="chain-step-text">{step.text ? step.text : '–'}</span>
                  </li>
                ))}
              </ol>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel" aria-labelledby="audit-log-title">
        <h2 id="audit-log-title">Audit-loki</h2>
        <div className="filter-row" role="group" aria-label="Suodata lokia">
          <label>
            Seuranta
            <select value={planFilter} onChange={(e) => setPlanFilter(e.target.value)}>
              <option value="">Kaikki</option>
              {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label>
            Toimija
            <select value={actorFilter} onChange={(e) => setActorFilter(e.target.value)}>
              <option value="">Kaikki</option>
              {Object.entries(ACTOR_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </label>
          <span className="muted small" aria-live="polite">{entries.length} merkintää</span>
        </div>
        <div className="table-wrap">
          <table className="audit-table">
            <caption className="visually-hidden">Agentin audit-loki, uusin ensin</caption>
            <thead>
              <tr>
                <th scope="col">Aika</th>
                <th scope="col">Vaihe</th>
                <th scope="col">Toimija</th>
                <th scope="col">Seuranta</th>
                <th scope="col">Kuvaus</th>
                <th scope="col">Sääntö / toimi</th>
                <th scope="col">Kielimalli</th>
                <th scope="col">Tulos</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id} className={entry.escalated ? 'is-escalated' : ''}>
                  <td>{formatDate(entry.date)}<br /><small className="muted">#{entry.seq}</small></td>
                  <td>{entry.stageLabel}</td>
                  <td>{ACTOR_LABELS[entry.actor]}</td>
                  <td>{entry.planId ? `${planName(entry.planId)} v${entry.planVersion}` : '–'}</td>
                  <td>{text(entry)}</td>
                  <td>
                    {entry.rule?.id && <code>{entry.rule.id}</code>}
                    {entry.action && <div className="muted small">{policy?.actions?.[entry.action] ?? ACTION_LABELS[entry.action] ?? entry.action}</div>}
                    {entry.escalated && <div className="chip chip-attention">Eskaloitu</div>}
                  </td>
                  <td>{entry.llmUsed ? `Kyllä – ${entry.llmTask}` : entry.llmTask ? `Yritettiin: ${entry.llmTask}` : 'Ei'}</td>
                  <td>{result(entry)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button type="button" className="link-button" aria-expanded={showLegacy} onClick={() => setShowLegacy(!showLegacy)}>
          {showLegacy ? 'Piilota' : 'Näytä'} perimätiedon sääntömoottorin loki ({audit.legacy.length})
        </button>
        {showLegacy && (
          <ul className="plain-list legacy-log">
            {audit.legacy.map((entry) => (
              <li key={entry.id}>{formatDate(entry.date)} · {entry.rule?.id ? <code>{entry.rule.id}</code> : null} {text(entry)}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
