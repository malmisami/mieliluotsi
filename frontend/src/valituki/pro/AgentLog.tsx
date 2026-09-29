import { useState } from 'react';
import { useValituki } from '../context';
import { fmtDateTime } from '../format';
import { NodesIcon } from '../icons';
import { AgentTimeline } from '../components/Timeline';
import { AgentBadge, Segmented } from '../components/ui';

/** "Mitä Mieliluotsi teki?" across all clients, the agents' responsibilities and the audit log. */
export default function AgentLog() {
  const { view, setProClientId } = useValituki();
  const pro = view.professional;
  const [agent, setAgent] = useState<string>('all');
  const [mode, setMode] = useState<'actions' | 'audit'>('actions');
  const actions = pro.timeline.filter((a) => agent === 'all' || a.agent === agent);
  return (
    <div className="log-page">
      <section className="agents-grid">
        {pro.agents.filter((a) => a.name !== 'Orchestrator').map((a) => (
          <button key={a.name} type="button" className={`agent-card agent-${a.name}`} aria-pressed={agent === a.name}
            onClick={() => setAgent(agent === a.name ? 'all' : a.name)}>
            <span className="agent-card-head"><AgentBadge agent={a.name} full /><span className="agent-count">{a.actions}</span></span>
            <span className="agent-desc">{a.description}</span>
          </button>
        ))}
      </section>
      <p className="muted small"><NodesIcon size={14} /> Orkestroija päättää, mikä agentti käsittelee kunkin tapahtuman. SafetyAgent voi keskeyttää muut.
        Agentit tekevät havaintoja ja tehtäviä – eivät diagnooseja, hoitopäätöksiä tai kiireellisyysmuutoksia.</p>
      <section className="card">
        <div className="card-row">
          <h2 className="card-title-lg">Mitä Mieliluotsi teki?</h2>
          <Segmented label="Näkymä" value={mode} onChange={setMode}
            options={[{ value: 'actions', label: 'Agenttien toimet' }, { value: 'audit', label: 'Audit-loki' }]} />
        </div>
        {mode === 'actions' ? (
          <AgentTimeline showClient items={actions.map((a) => ({ id: a.id, at: a.createdAt, agent: a.agent, title: a.title, detail: a.detail,
            ruleId: a.ruleId, aiSource: a.aiSource, clientName: a.clientName }))} limit={80} />
        ) : (
          <div className="table-wrap">
            <table className="table audit-table">
              <thead><tr><th scope="col">Aika</th><th scope="col">Toimija</th><th scope="col">Toiminto</th><th scope="col">Asiakas</th><th scope="col">Kuvaus</th></tr></thead>
              <tbody>
                {pro.audit.map((e) => (
                  <tr key={e.id}>
                    <td className="nowrap">{fmtDateTime(e.at)}</td>
                    <td className="small">{e.actor}</td>
                    <td className="small"><code>{e.action}</code></td>
                    <td className="small">{e.clientName ?? '–'}</td>
                    <td className="small">{e.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <button type="button" className="link-btn" onClick={() => setProClientId('cl-aino')}>Avaa Ainon tarkistusnäkymä →</button>
    </div>
  );
}
