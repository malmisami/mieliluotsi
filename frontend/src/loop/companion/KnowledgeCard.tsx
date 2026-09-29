import { AlertIcon, ArrowRightIcon, ClockIcon, DotIcon, QuestionIcon } from '../../icons';
import { StatusBadge } from '../labels';
import type { AgentState, LoopDashboard } from '../types';

type MonitoringRow = { finding: string; status: AgentState; count: number };

/** Identical rows (e.g. three masked genetic findings) are shown once with a count. */
function groupMonitorings(states: { finding: string; status: AgentState }[]): MonitoringRow[] {
  const rows = new Map<string, MonitoringRow>();
  for (const state of states) {
    const key = `${state.finding}|${state.status}`;
    const row = rows.get(key);
    if (row) row.count += 1;
    else rows.set(key, { ...state, count: 1 });
  }
  return Array.from(rows.values());
}

export default function KnowledgeCard({ dashboard }: { dashboard: LoopDashboard }) {
  const k = dashboard.companion.knowledge;
  const monitorings = groupMonitorings(k.monitoringStates);
  return (
    // collapsed by default: the four core tasks of the continuity engine come first, the bounded LLM context second
    <details className="panel knowledge-card">
      <summary><h2 id="knowledge-title">Mitä Hyvinvointikumppani tietää nyt</h2></summary>
      <p className="muted small">Vain rakenteiset tiedot sallimistasi lähteistä – ei koko DNA-aineistoa.</p>
      <ul className="knowledge-list">
        <li>
          <span className="knowledge-icon" aria-hidden="true"><DotIcon size={18} /></span>
          <span>
            <strong>{k.activePlansLabel}</strong>
            {k.planStates.map((p) => (
              <span key={p.name} className="knowledge-sub">{p.name} (versio {p.version})</span>
            ))}
          </span>
        </li>
        <li>
          <span className="knowledge-icon" aria-hidden="true"><DotIcon size={18} /></span>
          <span>
            <strong>{k.activeMonitoringsLabel}</strong>
            {monitorings.map((m) => (
              <span key={`${m.finding}-${m.status}`} className="knowledge-sub">
                {m.finding}{m.count > 1 ? ` × ${m.count}` : ''} <StatusBadge status={m.status} />
              </span>
            ))}
          </span>
        </li>
        <li className={k.openObservations ? 'is-attention' : ''}>
          <span className="knowledge-icon" aria-hidden="true"><AlertIcon size={18} /></span>
          <strong>{k.openObservationsLabel}</strong>
        </li>
        <li>
          <span className="knowledge-icon" aria-hidden="true"><QuestionIcon size={18} /></span>
          <span>
            {k.missingInformation.length ? (
              <>
                <strong>Puuttuva tieto:</strong>
                <ul>{k.missingInformation.map((m) => <li key={m}>{m.toLowerCase()}</li>)}</ul>
              </>
            ) : (
              <strong>Ei tiedossa olevia puuttuvia tietoja</strong>
            )}
          </span>
        </li>
        <li>
          <span className="knowledge-icon" aria-hidden="true"><ArrowRightIcon size={18} /></span>
          <span><strong>Seuraava tehtävä:</strong> {k.nextTask ?? 'ei avoimia tehtäviä'}</span>
        </li>
        <li>
          <span className="knowledge-icon" aria-hidden="true"><ClockIcon size={18} /></span>
          <span><strong>Viimeisin merkityksellinen tapahtuma:</strong> {k.latestRelevantEvent ?? 'ei vielä tapahtumia'}</span>
        </li>
      </ul>
      <details className="context-details">
        <summary>Näytä kielimallille annettava rajattu konteksti (JSON)</summary>
        <pre className="json">{JSON.stringify(dashboard.companion.userContext, null, 2)}</pre>
      </details>
    </details>
  );
}
