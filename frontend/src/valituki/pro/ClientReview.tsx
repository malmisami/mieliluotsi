import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtDate, fmtDateTime, fmtNum, fmtShort, genitive } from '../format';
import { AlertIcon, ArrowLeftIcon, CheckIcon, ChatIcon, CrossIcon, EyeIcon, LockIcon, PuzzleIcon, ShieldIcon, SparkleIcon } from '../icons';
import { Meter, WellbeingChart } from '../components/charts';
import { AgentTimeline } from '../components/Timeline';
import { AgentBadge, Pill, TypeTag } from '../components/ui';
import { FitProfileCard } from '../client/MatchingTab';
import type { ObservationRow, ProfessionalClient } from '../types';

export default function ClientReview({ client }: { client: ProfessionalClient }) {
  const { view, run, busy, setProClientId } = useValituki();
  const review = client.openReview;
  const lastReviewed = client.observations.find((o) => o.status !== 'open' && o.reviewedAt && o.kind !== 'trend_improvement');
  const openTasks = client.tasks.filter((t) => ['open', 'contact_requested'].includes(t.status) && (!review || t.observationId !== review.id));
  const events = client.observations.filter((o) => o.kind === 'trend_decline').map((o) => ({ date: o.createdAt.slice(0, 10), label: 'Tarkistuspyyntö' }));
  return (
    <div className="review-page">
      <button type="button" className="back-link" onClick={() => setProClientId(null)}><ArrowLeftIcon size={16} /> Terapiajono</button>
      <header className="review-head">
        <div className="review-who">
          <span className="review-avatar" aria-hidden="true">{client.firstName[0]}{client.displayName.split(' ').slice(-1)[0]?.[0]}</span>
          <div>
            <h1 className="review-name">{client.displayName}</h1>
            <p className="review-meta">{client.age} v · {client.municipality} · {client.referral?.serviceLabel} · hain apua {fmtDate(client.referral?.soughtHelpAt)}</p>
            <div className="review-chips">
              <span className="review-chip">{client.stateLabel}</span>
              {client.mode === 'therapy_support' && <span className="review-chip">Terapian välituki</span>}
              {client.safetyLockActive && <span className="review-chip is-alert"><AlertIcon size={13} /> Turvallisuusohjeet näkyvissä</span>}
            </div>
          </div>
        </div>
        <dl className="review-stats">
          <div>
            <dt>Odottanut</dt>
            <dd><span className="review-stat">{client.waitingDays ?? '–'}</span> pv</dd>
          </div>
          {client.monitoring && client.trend.recent !== null && (
            <div className={`trend-${client.trend.direction}`}>
              <dt>Vointi nyt</dt>
              <dd><span className="review-stat">{fmtNum(client.trend.recent)}</span> / 5
                {client.trend.baseline !== null && <span className="review-stat-sub">oma lähtötaso {fmtNum(client.trend.baseline)}</span>}</dd>
            </div>
          )}
          {client.urgency && (
            <div className={`urgency-${client.urgency.value}`}>
              <dt>Kiireellisyys</dt>
              <dd><span className="review-stat review-stat-word">{client.urgency.label}</span>
                <span className="review-stat-sub">ammattilaisen päätös</span></dd>
            </div>
          )}
        </dl>
      </header>

      <div className="review-grid">
        <div className="review-main">
          {review ? <WhyCard client={client} observation={review} /> : lastReviewed ? (
            <section className="card reviewed-card">
              <span className="reviewed-mark" aria-hidden="true"><CheckIcon size={20} /></span>
              <div>
                <p className="reviewed-when">Tarkistettu {fmtDateTime(lastReviewed.reviewedAt)}</p>
                <p className="reviewed-what"><strong>{lastReviewed.title}</strong> → {lastReviewed.reviewOutcome}</p>
                <p className="muted small">{lastReviewed.reviewedBy}{lastReviewed.reviewNote ? ` – ${lastReviewed.reviewNote}` : ''}</p>
              </div>
            </section>
          ) : (
            <section className="card calm-card">
              <p className="eyebrow">Ei avoimia tarkistuspyyntöjä</p>
              <p>Mieliluotsi jatkaa tukea. Mitään ei ole nostettu tarkistettavaksi.</p>
            </section>
          )}

          <section className="card">
            {client.monitoring ? (
              <>
                <WellbeingChart title={`${genitive(client.firstName)} vointi suhteessa omaan lähtötasoon`} points={client.trend.series} height={230}
                  baseline={client.trend.baseline} events={events} note="itse raportoitu 1–5 · ei diagnoosi" />
                <p className="small">{client.trend.text}</p>
                <CheckInTable client={client} />
              </>
            ) : <p className="muted"><LockIcon size={15} /> Asiakas ei ole sallinut voinnin seurantaa hoitotiimille.</p>}
          </section>

          <MatchingPanel client={client} />

          <ClientTimeline client={client} />
        </div>

        <aside className="review-side">
          {client.urgency && <UrgencyBox client={client} />}
          {openTasks.length > 0 && (
            <section className="card">
              <h2 className="card-title">Avoimet tehtävät</h2>
              {openTasks.map((task) => (
                <div key={task.id} className="task">
                  <p className="task-title">{task.title} <AgentBadge agent={task.agent} /></p>
                  <p className="small">{task.reason}</p>
                  {typeof task.underlyingData.clientMessage === 'string' && <p className="task-quote">”{task.underlyingData.clientMessage}”</p>}
                  <p className="muted small">{task.suggestedAction}</p>
                  <div className="row-gap">
                    {task.status === 'open' && <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                      onClick={() => run((s) => api.taskAction(s, task.id, 'contact'), () => 'Yhteydenotto sovittu – asiakkaalle ilmoitettiin.')}><ChatIcon size={14} /> Ota yhteyttä</button>}
                    <button type="button" className="btn btn-quiet btn-sm" disabled={busy}
                      onClick={() => run((s) => api.taskAction(s, task.id, 'complete'), () => 'Tehtävä merkittiin käsitellyksi.')}><CheckIcon size={14} /> Käsitelty</button>
                  </div>
                </div>
              ))}
            </section>
          )}

          <section className="card">
            <h2 className="card-title">Asiakkaan jakamat tiedot</h2>
            <p className="muted small">Vain tiedot, joille asiakas on antanut luvan ”Saa näkyä ammattilaiselle”.</p>
            <ul className="shared-list">
              {client.insights.visible.map((i) => (
                <li key={i.id}>
                  <span className="shared-kind">{i.title}</span> {i.text}
                  <span className="shared-meta">{i.sourceLabel}{i.matching ? <> · <PuzzleIcon size={12} /> matching</> : ''}</span>
                </li>
              ))}
            </ul>
            {client.insights.hiddenCount > 0 && <p className="muted small"><LockIcon size={13} /> {client.insights.hiddenCount} tietoa vain asiakkaan nähtävissä</p>}
          </section>

          {client.fitProfile && <FitProfileCard profile={client.fitProfile} />}

          {client.booking && (
            <section className="card">
              <h2 className="card-title">Terapia</h2>
              <p><strong>{client.booking.therapistName}</strong> · {client.booking.startText}</p>
              <p className="small">Yhteenveto: {client.handover?.statusLabel ?? 'ei vielä'}</p>
              <p className="small">Tila: {client.therapy.mode.title}{client.therapy.configured ? ' – terapeutti määrittänyt' : ''}</p>
              {client.matchFeedback.map((f) => (
                <p key={f.id} className={`small ${f.negative ? 'text-warn' : ''}`}>Yhteistyöpalaute: kuulluksi {f.heard}/5 · tavoitteet {f.goalsUnderstood}/5 · työtapa {f.styleFit}/5
                  {f.note ? ` – ”${f.note}”` : ''}</p>
              ))}
            </section>
          )}

          <NoteForm client={client} />
          <p className="muted small">{view.meta.syntheticNotice}</p>
        </aside>
      </div>
    </div>
  );
}

function ClientTimeline({ client }: { client: ProfessionalClient }) {
  const [all, setAll] = useState(false);
  const total = client.timeline.length;
  return (
    <section className="card">
      <div className="card-row">
        <h2 className="card-title">Mitä Mieliluotsi teki? – {client.firstName}</h2>
        {total > 10 && <button type="button" className="link-btn" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? 'Näytä uusimmat' : `Näytä kaikki (${total})`}</button>}
      </div>
      <AgentTimeline items={client.timeline.map((e) => ({ id: e.id, at: e.at, agent: e.agent, title: e.title, detail: e.detail,
        ruleId: e.ruleId, aiSource: e.aiSource, kind: e.kind }))} limit={all ? total : 10} />
    </section>
  );
}

function UrgencyBox({ client }: { client: ProfessionalClient }) {
  const { run, busy } = useValituki();
  const urgency = client.urgency;
  if (!urgency) return null;
  return (
    <section className={`card urgency-box urgency-${urgency.value}`}>
      <p className="eyebrow"><ShieldIcon size={14} /> Hoidon kiireellisyys</p>
      <p className="urgency-value">{urgency.label}</p>
      <p className="small muted">Määrittänyt: {urgency.setBy} · {fmtDate(urgency.setAt)}</p>
      <p className="urgency-note">Mieliluotsi ei ole muuttanut hoidon kiireellisyyttä. Vain ammattilainen voi muuttaa sitä.</p>
      <label className="small">
        <span className="visually-hidden">Muuta kiireellisyyttä (ammattilainen)</span>
        <select value={urgency.value} disabled={busy}
          onChange={(e) => run((s) => api.setUrgency(s, client.id, e.target.value as 'non_urgent' | 'urgent', 'Ammattilaisen arvio'),
            () => 'Ammattilainen muutti hoidon kiireellisyyttä – muutos kirjattiin audit-lokiin.')}>
          <option value="non_urgent">Kiireetön</option>
          <option value="urgent">Kiireellinen</option>
        </select>
      </label>
    </section>
  );
}

function WhyCard({ client, observation }: { client: ProfessionalClient; observation: ObservationRow }) {
  const { run, busy } = useValituki();
  const [showFrequency, setShowFrequency] = useState(false);
  const safety = observation.category === 'safety';
  const describe = (r: { outcome: string }) => `${client.firstName}: ${r.outcome}. Mieliluotsi jatkaa tukea – hoidon kiireellisyys ennallaan.`;
  return (
    <section className={`card why-card ${safety ? 'why-safety' : ''}`}>
      <p className="why-eyebrow"><span className="why-pulse" aria-hidden="true" />{safety ? 'Turvallisuushavainto' : 'Tarkistuspyyntö'} · {fmtDateTime(observation.createdAt)}</p>
      <h2 className="why-title">Miksi {client.firstName} nousi tarkistettavaksi?</h2>
      <ul className="why-list">
        {observation.explanation.map((row, i) => (
          <li key={row.text}><span className="why-num" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>{row.text}</li>
        ))}
      </ul>
      <p className="why-basis">
        <AgentBadge agent={observation.agent} /> Sääntö <code>{observation.ruleId}</code> · deterministinen · itse raportoidut tiedot · ei diagnoosi
      </p>
      {observation.aiSummary && (
        <div className="ai-box">
          <TypeTag type="ai_summary" />
          <p>{observation.aiSummary}</p>
        </div>
      )}
      <div className="action-box">
        <p className="eyebrow">Mieliluotsin toimenpide</p>
        <p className="action-text"><SparkleIcon size={16} /> {observation.suggestedAction || 'Ehdotus: ammattilaisen tarkistus.'}</p>
        <div className="why-actions">
          <button type="button" className="btn btn-primary" disabled={busy}
            onClick={() => run((s) => api.reviewObservation(s, observation.id, 'mark_reviewed'), describe)}><CheckIcon size={16} /> Merkitse tarkistetuksi</button>
          <button type="button" className="btn btn-secondary" disabled={busy}
            onClick={() => run((s) => api.reviewObservation(s, observation.id, 'contact'), describe)}><ChatIcon size={16} /> Ota yhteyttä</button>
          <button type="button" className="btn btn-secondary" disabled={busy}
            onClick={() => run((s) => api.reviewObservation(s, observation.id, 'no_action'), describe)}><CrossIcon size={16} /> Ei toimenpiteitä</button>
          {!safety && (
            <button type="button" className="btn btn-secondary" disabled={busy} aria-expanded={showFrequency} onClick={() => setShowFrequency(!showFrequency)}>
              Muuta check-in tiheyttä
            </button>
          )}
        </div>
        {showFrequency && (
          <div className="row-gap freq-row">
            {[3, 2, 1].map((n) => (
              <button key={n} type="button" className="btn btn-quiet btn-sm" disabled={busy}
                onClick={() => run((s) => api.reviewObservation(s, observation.id, 'frequency', '', n), describe)}>{n}× viikossa</button>
            ))}
          </div>
        )}
      </div>
      <p className="why-statement"><ShieldIcon size={16} /> AI ei muuttanut kiireellisyyttä – se nosti tilanteen tarkistettavaksi. Mieliluotsi ei ole muuttanut hoidon
        kiireellisyyttä. Tämä havainto odottaa ammattilaisen tarkistusta.</p>
    </section>
  );
}

function CheckInTable({ client }: { client: ProfessionalClient }) {
  const { view } = useValituki();
  const domains = view.meta.labels.domains;
  return (
    <details className="checkin-table">
      <summary>Check-init ({client.checkIns.length})</summary>
      <table className="table">
        <thead><tr><th scope="col">Päivä</th><th scope="col">Tila</th><th scope="col">Vointi</th><th scope="col">Ahdistus</th><th scope="col">Muuttunut</th><th scope="col">Merkintä</th></tr></thead>
        <tbody>
          {client.checkIns.map((c) => (
            <tr key={c.id}>
              <td>{fmtShort(c.dueDate)}</td>
              <td>{c.status === 'completed' ? (c.kind === 'client_initiated' ? 'tehty (oma-aloitteinen)' : 'tehty') : c.status === 'missed' ? 'jäi väliin' : 'odottaa'}</td>
              <td className="num">{c.mood ?? '–'}</td>
              <td className="num">{c.anxiety ?? '–'}</td>
              <td className="small">{Object.entries(c.changes).map(([k, v]) => `${domains[k]} ${v === 'worse' ? '↓' : '↑'}`).join(', ') || '–'}</td>
              <td className="small muted">{c.hasNote ? 'vain asiakkaalle' : '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function MatchingPanel({ client }: { client: ProfessionalClient }) {
  const matching = client.matching;
  if (!matching.decision) {
    return (
      <section className="card">
        <h2 className="card-title">Matching</h2>
        <ul className="criteria">
          {matching.readiness.map((c) => <li key={c.key} className={c.passed ? 'ok' : 'todo'}>{c.passed ? <CheckIcon size={15} /> : <span className="dot-todo" />} {c.label}</li>)}
        </ul>
        <p className="muted small">Matching ajetaan automaattisesti, kun terapeutin asiakaspaikka vapautuu.</p>
      </section>
    );
  }
  return (
    <section className="card">
      <div className="card-row">
        <h2 className="card-title">Matching {matching.run ? `· ${fmtDateTime(matching.run.createdAt)}` : ''}</h2>
        <Pill tone="neutral">{matching.decision.status === 'held_for_review' ? 'Odottaa tarkistusta' : matching.decision.status === 'client_selected' ? 'Asiakas valitsi' : 'Asiakkaalla'}</Pill>
      </div>
      <p className="muted small">Deterministinen: kovat ehdot → painotettu sopivuus. Pisteet ovat läpinäkyvä järjestysapu, eivät todennäköisyys – asiakkaalle
        näytetään vain sanallinen yhteensopivuus.</p>
      <div className="pro-cands">
        {matching.candidates.slice(0, 4).map((c) => (
          <details key={c.id} className="pro-cand" open={c.rank === 1}>
            <summary><span className="rank">{c.rank}</span> {c.therapist.name} <span className={`fit-label fit-${c.label}`}>{c.labelText}</span>
              {c.status === 'selected' && <Pill tone="ok">Valittu</Pill>}</summary>
            <div className="meters">
              {(c.components ?? []).map((m) => <Meter key={m.key} label={m.label} value={m.points} max={m.weight} detail={m.explanation} />)}
            </div>
          </details>
        ))}
      </div>
      {matching.excluded.length > 0 && (
        <details className="excluded">
          <summary>Kovissa ehdoissa rajautuneet ({matching.excluded.length})</summary>
          <ul>{matching.excluded.map((x) => <li key={x.therapistId}><strong>{x.name}</strong>: {x.failed.map((f) => f.reason).join(' · ')}</li>)}</ul>
        </details>
      )}
      {matching.candidates[0] && (
        <details className="excluded">
          <summary><EyeIcon size={14} /> Käytetyt tiedot</summary>
          <ul>{matching.candidates[0].dataUsed.map((d) => <li key={d}>{d}</li>)}</ul>
          <p className="section-label">Ei käytetty</p>
          <ul>{matching.candidates[0].dataNotUsed.map((d) => <li key={d}>{d}</li>)}</ul>
        </details>
      )}
    </section>
  );
}

function NoteForm({ client }: { client: ProfessionalClient }) {
  const { run, busy } = useValituki();
  const [text, setText] = useState('');
  const [include, setInclude] = useState(true);
  return (
    <section className="card">
      <h2 className="card-title">Ammattilaisen merkintä</h2>
      {client.notes.map((n) => <p key={n.id} className="small"><TypeTag type="professional_note" short /> {n.text}</p>)}
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Esim. soitettu, sovittu jatkosta…" aria-label="Merkintä" />
      <label className="check-row"><input type="checkbox" checked={include} onChange={(e) => setInclude(e.target.checked)} /> Voi liittää terapeutin yhteenvetoon (asiakas hyväksyy)</label>
      <button type="button" className="btn btn-secondary btn-sm" disabled={busy || !text.trim()}
        onClick={async () => { await run((s) => api.addNote(s, client.id, text, include), () => 'Merkintä tallennettiin.'); setText(''); }}>Tallenna merkintä</button>
    </section>
  );
}
