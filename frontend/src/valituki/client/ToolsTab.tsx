import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { ClockIcon, LockIcon, SearchIcon, StethoscopeIcon } from '../icons';
import { normalizeText } from '../format';
import type { LadderRow, PracticeTask } from '../types';
import { useClientUI } from './ClientApp';
import { toolIcon } from './HomeTab';

/* "Harjoitukset": the agreed tasks first, then the guided CBT tools and the approved self-care library. */

const TOPICS: { key: string; label: string; tools: string[]; activities: string[] }[] = [
  { key: 'all', label: 'Kaikki', tools: [], activities: [] },
  { key: 'thoughts', label: 'Ajatukset', tools: ['thought_record', 'experiment'], activities: ['act-values'] },
  { key: 'exposure', label: 'Jännittäminen', tools: ['exposure', 'experiment'], activities: ['act-grounding', 'act-paced-breathing'] },
  { key: 'calm', label: 'Rauhoittuminen', tools: [], activities: ['act-grounding', 'act-paced-breathing'] },
  { key: 'worry', label: 'Huolet', tools: ['thought_record'], activities: ['act-worry-time', 'act-small-next-step'] },
  { key: 'sleep', label: 'Uni', tools: [], activities: ['act-sleep-reflection', 'act-paced-breathing'] },
  { key: 'mood', label: 'Mieliala', tools: ['thought_record'], activities: ['act-activity-planning', 'act-values', 'act-support-network'] },
];

export default function ToolsTab() {
  const { view } = useValituki();
  const { client, openSheet, startTool } = useClientUI();
  const [query, setQuery] = useState('');
  const [topic, setTopic] = useState('all');
  const practice = client.practice;
  const selected = TOPICS.find((t) => t.key === topic) ?? TOPICS[0];
  const matches = (text: string) => !query.trim() || normalizeText(text).includes(normalizeText(query));
  const tools = practice.tools.filter((t) => (topic === 'all' || selected.tools.includes(t.id)) && matches(`${t.title} ${t.kind} ${t.description}`));
  const library = client.plan.library.filter((a) => (topic === 'all' || selected.activities.includes(a.id)) && matches(`${a.title} ${a.description}`));
  const mode = client.mode;

  return (
    <div className="cx-screen cx-tools">
      <h1 className="cx-title">Harjoitukset</h1>
      <label className="cx-search">
        <SearchIcon size={18} />
        <span className="visually-hidden">Hae harjoituksia</span>
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Hae harjoituksia…" />
      </label>
      <div className="cx-chips-scroll" role="group" aria-label="Aihe">
        {TOPICS.map((t) => (
          <button key={t.key} type="button" className="cx-filter" aria-pressed={topic === t.key} onClick={() => setTopic(t.key)}>{t.label}</button>
        ))}
      </div>

      {practice.tasks.length > 0 && topic === 'all' && !query && (
        <section className="cx-section">
          <h2 className="cx-h2">Tehtäväsi</h2>
          <div className="cx-stack">{practice.tasks.map((task) => <TaskCard key={task.id} task={task} />)}</div>
        </section>
      )}

      {mode.mode === 'therapy_support' && mode.homework && (
        <p className="cx-note cx-note-brand"><StethoscopeIcon size={17} />
          <span><span className="cx-note-title">Terapeutin välitehtävä: {mode.homework.title}</span>{mode.homework.note}</span></p>
      )}

      {tools.length > 0 && (
        <section className="cx-section">
          <h2 className="cx-h2">Ohjatut harjoitukset</h2>
          <p className="cx-fine">Kognitiivisen käyttäytymisterapian (KKT) työkaluja. Mieliluotsi kysyy kysymys kerrallaan – voit ohittaa tai lopettaa milloin tahansa.</p>
          <div className="cx-tool-grid">
            {tools.map((tool) => (
              <button key={tool.id} type="button" className={`cx-tile cx-tool-${tool.id}`} disabled={!tool.allowed}
                onClick={() => startTool(tool.id, {}, 'library')}>
                <span className="cx-tile-top"><span className="cx-tag cx-tag-light">{tool.kind}</span><span className="cx-tile-min"><ClockIcon size={13} /> {tool.duration} min</span></span>
                <span className="cx-tile-icon" aria-hidden="true">{toolIcon(tool.id, 26)}</span>
                <span className="cx-tile-title">{tool.title}</span>
                <span className="cx-tile-text">{tool.allowed ? tool.description : <><LockIcon size={13} /> {tool.lockedReason}</>}</span>
                {tool.count > 0 && <span className="cx-tile-count">Tehty {tool.count} kertaa</span>}
              </button>
            ))}
          </div>
        </section>
      )}

      {practice.ladders.length > 0 && (topic === 'all' || topic === 'exposure') && !query && (
        <section className="cx-section">
          <h2 className="cx-h2">Altistusportaasi</h2>
          {practice.ladders.map((ladder) => <LadderCard key={ladder.id} ladder={ladder} />)}
        </section>
      )}

      {library.length > 0 && (
        <section className="cx-section">
          <h2 className="cx-h2">Omahoitoharjoitukset</h2>
          <ul className="cx-lib">
            {library.map((a) => (
              <li key={a.id}>
                <button type="button" className="cx-lib-item" disabled={!a.allowed} onClick={() => openSheet({ type: 'activity', activityId: a.id })}>
                  <span className="cx-lib-title">{a.title}</span>
                  <span className="cx-lib-text">{a.description}</span>
                  <span className="cx-lib-meta"><ClockIcon size={13} /> {a.estimatedDuration} min
                    {a.response?.latestRating ? ` · arviosi ${a.response.latestRating}/5` : ''}{a.response?.helpful ? ' · toimiva keino' : ''}
                    {!a.allowed && <> · <LockIcon size={12} /> {mode.mode === 'therapy_support' ? 'ei terapeuttisi sallima' : 'ei juuri nyt'}</>}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {tools.length === 0 && library.length === 0 && <p className="cx-day-empty">Ei hakua vastaavia harjoituksia.</p>}
      <p className="cx-fine">{view.meta.cbt.approvalNote}</p>
    </div>
  );
}

export function TaskCard({ task }: { task: PracticeTask }) {
  const { run, busy } = useValituki();
  const { client, doTask } = useClientUI();
  return (
    <article className={`cx-task ${task.overdue ? 'is-overdue' : ''}`}>
      <div className="cx-task-top">
        <span className="cx-tag">{task.kindLabel}</span>
        <span className={`cx-due ${task.dueLabel === 'Tänään' ? 'is-today' : ''}`}>{task.dueLabel}</span>
      </div>
      <p className="cx-task-title">{task.title}</p>
      {task.detail && <p className="cx-task-text">{task.detail}</p>}
      {task.assignedBy !== 'client' && <p className="cx-fine">Antaja: {task.assignedByLabel}</p>}
      <div className="cx-row">
        <button type="button" className="cx-btn cx-btn-dark cx-btn-sm" disabled={busy} onClick={() => doTask(task.id)}>{task.actionLabel}</button>
        {task.kind !== 'homework' && (
          <>
            <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy}
              onClick={() => run((s) => api.clientTaskAction(s, client.id, task.id, 'later'), () => 'Siirretty huomiseen.')}>Siirrä</button>
            <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy}
              onClick={() => run((s) => api.clientTaskAction(s, client.id, task.id, 'skip'), () => 'Tehtävä ohitettiin – se on aina sallittua.')}>Ohita</button>
          </>
        )}
      </div>
    </article>
  );
}

export function LadderCard({ ladder }: { ladder: LadderRow }) {
  const pct = ladder.progress.total ? Math.round((ladder.progress.done / ladder.progress.total) * 100) : 0;
  return (
    <article className="cx-ladder">
      <div className="cx-ladder-head">
        <p className="cx-ladder-goal">{ladder.goal}</p>
        <span className="cx-fine">{ladder.progress.done}/{ladder.progress.total} askelta{ladder.status === 'completed' ? ' · valmis' : ''}</span>
      </div>
      <span className="cx-progressbar" role="progressbar" aria-valuemin={0} aria-valuemax={ladder.progress.total} aria-valuenow={ladder.progress.done}
        aria-label="Portaan eteneminen"><span style={{ width: `${pct}%` }} /></span>
      <ol className="cx-steps">
        {[...ladder.steps].reverse().map((step) => {
          const last = step.attempts[step.attempts.length - 1];
          return (
            <li key={step.id} className={`cx-step is-${step.status}`}>
              <span className="cx-step-mark" aria-hidden="true">{step.expected}</span>
              <span className="cx-step-text">{step.text}
                <span className="cx-step-meta">{step.status === 'done' ? 'Tehty' : step.status === 'doing' ? 'Työn alla' : 'Tulossa'}
                  {last ? ` · ahdistus ${last.peak ?? '–'} → ${last.after ?? '–'}` : ` · odotettu ${step.expected}/10`}</span>
              </span>
            </li>
          );
        })}
      </ol>
    </article>
  );
}
