import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtDate, fmtDateTime, fmtNum, fmtShort } from '../format';
import { CalendarIcon, CheckIcon, ChevronDownIcon, FlagIcon, LockIcon, PlayIcon, PulseIcon, QuoteIcon, SparkleIcon, StethoscopeIcon,
  VideoIcon } from '../icons';
import { MoodAnxietyChart, Sparkline } from '../components/charts';
import { HandoverDoc } from '../components/HandoverDoc';
import { Milestones } from '../components/Milestones';
import { Empty, Pill, Segmented, TypeTag } from '../components/ui';
import type { AftercareInput, PlanInput, PracticeStats, TherapistClientRow } from '../types';

export default function TherapistApp() {
  const { view } = useValituki();
  const therapist = view.therapist.selected;
  const clients = therapist?.clients ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const current = clients.find((c) => c.clientId === selectedId) ?? clients.find((c) => c.clientId === 'cl-aino') ?? clients[0];
  return (
    <div className="therapist">
      <aside className="th-side">
        {current && current.milestones.length > 0 && (
          <section className="th-milestones">
            <p className="section-label">Merkkipaalut – {current.firstName}</p>
            <Milestones items={current.milestones} compact />
          </section>
        )}
      </aside>
      <main className="th-main">
        {current ? <ClientSummary row={current} clients={clients} onSelect={setSelectedId} /> : <Empty title="Ei valittua asiakasta">Valitse terapeutti, jolla on Mieliluotsin kautta tulleita asiakkaita.</Empty>}
      </main>
    </div>
  );
}

function ClientSummary({ row, clients, onSelect }: { row: TherapistClientRow; clients: TherapistClientRow[]; onSelect: (id: string) => void }) {
  const { run, busy, scope } = useValituki();
  const therapistId = scope.therapistId ?? 'th-anna';
  const status = row.therapy.episodeStatus;
  const active = status === 'active';
  const ended = status === 'ended';
  return (
    <div className="th-summary">
      <section className="session-banner">
        <p className="eyebrow"><CalendarIcon size={14} /> {ended ? 'Terapia päättynyt – seuranta' : active ? 'Terapia käynnissä' : 'Ensimmäinen tapaaminen'}</p>
        {clients.length > 1 && (
          <div className="th-switch" role="group" aria-label="Asiakkaat">
            {clients.map((c) => (
              <button key={c.clientId} type="button" aria-pressed={c.clientId === row.clientId} onClick={() => onSelect(c.clientId)}>{c.clientName}</button>
            ))}
          </div>
        )}
        <h1 className="pro-title">{row.clientName} – {ended ? `terapia päättyi ${fmtDate(row.therapy.endedAt)}`
          : active ? `terapia alkoi ${fmtDateTime(row.firstSession)}` : `ensimmäinen tapaaminen ${fmtDateTime(row.firstSession)}`}</h1>
        <p className="muted"><VideoIcon size={15} /> {row.format === 'remote' ? 'Etävastaanotto' : 'Lähivastaanotto'} · {row.age} v
          {row.therapy.sessionsHeld > 0 && ` · ${row.therapy.sessionsHeld} tapaamista`}</p>
        {row.therapy.canHoldFirstSession && (
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
            onClick={() => run((s) => api.holdFirstSession(s, therapistId, row.clientId), (r) =>
              `Ensimmäinen tapaaminen pidettiin (demo: ${r.days} pv eteenpäin). Mieliluotsi siirtyi terapian välitueksi.`)}>
            <PlayIcon size={14} /> Merkitse ensimmäinen tapaaminen pidetyksi (demo)
          </button>
        )}
      </section>

      <HandoverCard row={row} />

      {(active || ended) && <PracticePanel row={row} />}

      {!ended && <TherapyPlan key={`${row.clientId}-${status}-${row.therapy.config?.version ?? 0}`} row={row} therapistId={therapistId} />}
      {active && row.therapy.config && <EndTherapy key={`end-${row.clientId}`} row={row} therapistId={therapistId} />}
      {ended && <AftercareSummary row={row} />}
    </div>
  );
}

const LEGEND = ['user_said', 'measured', 'ai_summary', 'professional_note'] as const;
const DIRECTION_ARROWS: Record<string, string> = { improving: '↑', stable: '→', declining: '↓', insufficient: '·' };

type GoalRow = { id: string; text: string; priority: 'primary' | 'secondary' };
type WellbeingFacts = { baseline: number | null; recent: number | null; direction: string; directionLabel: string; checkIns: number;
  points: { date: string; mood: number | null }[] };
type PracticeFacts = { stats: PracticeStats; ladders: { goal: string; done: number; total: number }[] };
type HelpedFacts = { activities: { title: string; rating: number | null }[]; ownWords: string | null };

/** The first-session summary at a glance – goals, the direction of wellbeing and practice while waiting, the three things the
    first session builds on. The whole summary the client approved opens below. */
function HandoverCard({ row }: { row: TherapistClientRow }) {
  const [full, setFull] = useState(false);
  const shared = (row.sections ?? []).filter((s) => s.available && !s.removed);
  const facts = <T,>(key: string) => shared.find((s) => s.key === key)?.content as T | undefined;
  const goals = facts<GoalRow[]>('goals') ?? [];
  const primary = goals.find((g) => g.priority === 'primary') ?? goals[0];
  const wellbeing = facts<WellbeingFacts>('wellbeing');
  const practiced = facts<PracticeFacts>('practice');
  const helped = facts<HelpedFacts>('helped');
  const practice = [
    practiced && practiced.stats.thoughtRecords > 0
      ? `Ajatusten tutkiminen ${practiced.stats.thoughtRecords}×${practiced.stats.avgDrop ? ` – tunne laski ${fmtNum(practiced.stats.avgDrop)}` : ''}` : null,
    ...(practiced?.ladders ?? []).slice(0, 1).map((l) => `Altistusporras ${l.done}/${l.total} askelta`),
    ...(helped?.activities ?? []).slice(0, 1).map((a) => `Auttanut: ${a.title}${a.rating ? ` (${a.rating}/5)` : ''}`),
  ].filter((line): line is string => Boolean(line));
  const count = shared.filter((s) => s.infoType !== 'system').length;

  return (
    <section className="card doc-card">
      <div className="card-row">
        <h2 className="card-title-lg">Yhteenveto ensimmäistä tapaamista varten</h2>
        {row.handoverStatus === 'approved' ? <Pill tone="ok" icon={<CheckIcon size={13} />}>Hyväksytty {fmtDateTime(row.approvedAt)}</Pill>
          : <Pill tone="neutral">{row.handoverStatus === 'withdrawn' ? 'Jakaminen peruttu' : 'Luonnos – odottaa asiakkaan hyväksyntää'}</Pill>}
      </div>
      {row.sections ? (
        <>
          <div className="glance">
            {primary && (
              <div className="glance-tile type-user_said">
                <p className="glance-label"><QuoteIcon size={13} /> Tavoitteet</p>
                <p className="glance-main">{primary.text}</p>
                {goals.filter((g) => g !== primary).map((g) => <p key={g.id} className="glance-sub">{g.text}</p>)}
              </div>
            )}
            {wellbeing && (
              <div className="glance-tile type-measured">
                <p className="glance-label"><PulseIcon size={13} /> Vointi odotusaikana</p>
                <p className={`glance-main glance-dir is-${wellbeing.direction}`}>{DIRECTION_ARROWS[wellbeing.direction]} {wellbeing.directionLabel}</p>
                <p className="glance-sub">Viime päivät {fmtNum(wellbeing.recent)} / 5 · oma taso {fmtNum(wellbeing.baseline)}</p>
                <Sparkline values={wellbeing.points.map((p) => p.mood)} baseline={wellbeing.baseline}
                  label={`Vointi 1–5, ${wellbeing.points.length} check-iniä: ${wellbeing.directionLabel.toLowerCase()}`} />
              </div>
            )}
            {practice.length > 0 && (
              <div className="glance-tile type-measured">
                <p className="glance-label"><PulseIcon size={13} /> Harjoittelu odotusaikana</p>
                <ul className="glance-list">{practice.map((line) => <li key={line}>{line}</li>)}</ul>
              </div>
            )}
          </div>
          <button type="button" className="glance-more" aria-expanded={full} onClick={() => setFull(!full)}>
            {full ? 'Piilota koko yhteenveto' : `Koko yhteenveto · ${count} kohtaa`} <ChevronDownIcon size={15} />
          </button>
          {full && (
            <div className="glance-full">
              <div className="ho-legend">
                {LEGEND.map((type) => <TypeTag key={type} type={type} short />)}
                <span className="ho-legend-note">{row.handoverStatus === 'approved' ? 'Tekoälyn tiivistelmä ei ole kliininen arvio.'
                  : `Luonnos – ${row.firstName} ei ole vielä hyväksynyt yhteenvetoa, ja se voi muuttua.`}</span>
              </div>
              <HandoverDoc sections={row.sections} layout="grid" />
            </div>
          )}
        </>
      ) : (
        <Empty icon={<LockIcon size={22} />} title="Yhteenveto ei ole vielä käytettävissä">
          {row.firstName} päättää, mitä jaetaan. Näet yhteenvedon heti, kun hän hyväksyy sen.
        </Empty>
      )}
    </section>
  );
}

/** Between-session practice: the figures in one line with the client's permission, the details a click away; journal entries
    only when the client shared them. */
function PracticePanel({ row }: { row: TherapistClientRow }) {
  const practice = row.therapy.practice;
  const stats = practice.stats;
  const since = row.therapy.sinceStart;
  const figures = stats ? [
    stats.thoughtRecords > 0 ? `${stats.thoughtRecords}× ajatusten tutkiminen${stats.avgDrop !== null ? ` (tunne laski ${fmtNum(stats.avgDrop)})` : ''}` : null,
    stats.exposureAttempts > 0 ? `${stats.exposureAttempts} altistusaskelta` : null,
    stats.experiments > 0 ? `${stats.experimentsDone}/${stats.experiments} käyttäytymiskoetta` : null,
  ].filter((f): f is string => Boolean(f)) : [];
  const records = practice.sharedRecords;
  return (
    <section className="card th-practice">
      <div className="card-row">
        <h2 className="card-title-lg"><SparkleIcon size={19} /> Harjoittelu tapaamisten välillä</h2>
        {practice.allowed ? <Pill tone="ok">Asiakkaan luvalla</Pill> : <Pill tone="neutral" icon={<LockIcon size={12} />}>Ei lupaa yhteenvetoon</Pill>}
      </div>
      {since.length > 1 && <MoodAnxietyChart points={since.map((p) => ({ date: p.date, at: null, mood: p.mood, anxiety: p.anxiety }))}
        title="Mieliala ja ahdistus terapian alusta" height={140} />}
      {!stats ? <p className="muted">{row.firstName} ei ole sallinut harjoittelun yhteenvetoa. Näet vain merkinnät, jotka hän jakaa itse.</p>
        : <p className="th-figures">{figures.length ? figures.join(' · ') : 'Ei vielä harjoituksia terapian alun jälkeen.'}</p>}
      {stats && stats.traps.length > 0 && (
        <p className="muted small">Tunnistetut ajatusloukut: {stats.traps.map((t) => `${t.label} (${t.count})`).join(', ')}</p>
      )}
      {practice.homework.map((h) => (
        <p key={h.id} className="th-line"><span className="th-line-label">Välitehtävä</span> {h.title} <span className="muted">· {h.status === 'done'
          ? `tehty ${fmtShort(h.completedAt)}` : h.status === 'skipped' ? 'ohitettu' : `avoinna, ${h.dueLabel.toLowerCase()}`}</span></p>
      ))}
      {practice.ladders.map((ladder) => (
        <details key={ladder.id} className="th-more">
          <summary>
            <span className="th-line-label">Altistusporras</span> <span className="th-more-title">{ladder.goal}</span>
            <span className="th-progress" aria-hidden="true"><i style={{ width: `${(ladder.progress.done / Math.max(1, ladder.progress.total)) * 100}%` }} /></span>
            <span className="muted">{ladder.progress.done}/{ladder.progress.total}</span>
          </summary>
          <ol className="th-ladder-steps">
            {ladder.steps.map((s) => {
              const last = s.attempts[s.attempts.length - 1];
              return <li key={s.id} className={`is-${s.status}`}>{s.text} <span className="muted small">({s.expected}/10{last ? ` · viimeksi ${last.peak}→${last.after}` : ''})</span></li>;
            })}
          </ol>
        </details>
      ))}
      {records.length === 0 ? <p className="muted small">Ei jaettuja ajatuspäiväkirjan merkintöjä – ne ovat oletuksena vain asiakkaan omia.</p> : (
        <details className="th-more">
          <summary><span className="th-line-label">Jaetut merkinnät</span> <span className="th-more-title">Ajatuspäiväkirja ({records.length})</span></summary>
          <div className="th-shared">
            {records.map((r) => (
              <article key={r.id} className="th-record">
                <p className="muted small">{fmtShort(r.date)} · {r.emotions.join(', ')} {r.intensityBefore ?? '–'} → {r.intensityAfter ?? '–'} / 10</p>
                <p><strong>Tilanne:</strong> {r.situation}</p>
                <p><strong>Ajatus:</strong> ”{r.thought}”</p>
                {r.traps.length > 0 && <p><strong>Ajatusloukut:</strong> {r.traps.map((t) => t.label).join(', ')}</p>}
                {r.alternative && <p><strong>Vaihtoehtoinen ajatus:</strong> ”{r.alternative}”</p>}
              </article>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

/** The between-session support the therapist sets once therapy has started: a suggestion built from what the client approved,
    shown as a summary to take into use as is – the form only when the therapist wants to change it. */
function TherapyPlan({ row, therapistId }: { row: TherapistClientRow; therapistId: string }) {
  const { view, run, busy } = useValituki();
  const therapy = row.therapy;
  const config = therapy.config;
  const empty: PlanInput = { primaryGoal: '', allowedActivityIds: [], allowedTools: [], homeworkTool: null, homeworkNote: '', checkInsPerWeek: 2,
    track: '', doNotAddress: '' };
  const initial: PlanInput = config ? { primaryGoal: config.primaryGoal, allowedActivityIds: config.allowedActivityIds, allowedTools: config.allowedTools,
    homeworkTool: config.homeworkTool, homeworkNote: config.homeworkNote, checkInsPerWeek: config.checkInsPerWeek, track: config.track,
    doNotAddress: config.doNotAddress } : therapy.suggestedPlan ?? empty;
  const [plan, setPlan] = useState<PlanInput>(initial);
  const [editing, setEditing] = useState(!config && !therapy.suggestedPlan);
  const library = view.therapist.library;
  const tools = view.therapist.tools;

  if (therapy.episodeStatus !== 'active') {
    return (
      <section className="card plan-card plan-locked">
        <h2 className="card-title-lg"><StethoscopeIcon size={20} /> Mieliluotsi tapaamisten välillä</h2>
        <p className="muted">Kun terapia alkaa, määrität tässä, miten Mieliluotsi tukee asiakasta tapaamisten välillä.</p>
      </section>
    );
  }

  function toggle(key: 'allowedActivityIds' | 'allowedTools', id: string) {
    setPlan((p) => ({ ...p, [key]: p[key].includes(id) ? p[key].filter((a) => a !== id) : [...p[key], id] }));
  }

  async function save() {
    const result = await run((s) => api.savePlan(s, therapistId, row.clientId, plan),
      () => 'Mieliluotsi toimii nyt vain määrittämissäsi rajoissa. Asiakkaalle ilmoitettiin.');
    if (result) setEditing(false);
  }

  const toolTitle = (id: string | null) => tools.find((t) => t.id === id)?.title ?? '–';
  const shown = config ?? plan;
  const canSave = !busy && Boolean(plan.primaryGoal.trim()) && plan.allowedActivityIds.length > 0;
  return (
    <section className="card plan-card">
      <div className="card-row">
        <h2 className="card-title-lg"><StethoscopeIcon size={20} /> Mieliluotsi tapaamisten välillä</h2>
        {!editing && (config ? <Pill tone="violet">Voimassa · v{config.version}</Pill> : <Pill tone="neutral">Ehdotus</Pill>)}
      </div>
      <p className="muted">{config ? 'Tekoäly toimii vain näissä rajoissa.' : 'Ehdotus on koottu asiakkaan hyväksymistä tiedoista. Tekoäly toimii vain näissä rajoissa.'}</p>
      {editing ? (
        <div className="plan-form">
          <label className="field"><span className="field-label">Päätavoite</span>
            <input value={plan.primaryGoal} onChange={(e) => setPlan({ ...plan, primaryGoal: e.target.value })} /></label>
          <div className="field"><span className="field-label">Ohjatut KKT-harjoitukset chatissa</span>
            <div className="chips">{tools.map((t) => (
              <button key={t.id} type="button" className="chip" aria-pressed={plan.allowedTools.includes(t.id)} onClick={() => toggle('allowedTools', t.id)}>{t.title}</button>
            ))}</div>
          </div>
          <div className="field"><span className="field-label">Välitehtävä (viikoittain)</span>
            <Segmented label="Välitehtävä" value={plan.homeworkTool ?? 'none'} onChange={(v) => setPlan({ ...plan, homeworkTool: v === 'none' ? null : v })}
              options={[{ value: 'none', label: 'Ei välitehtävää' }, ...tools.map((t) => ({ value: t.id, label: t.title }))]} />
            {plan.homeworkTool && (
              <textarea rows={2} value={plan.homeworkNote} aria-label="Välitehtävän ohje" onChange={(e) => setPlan({ ...plan, homeworkNote: e.target.value })}
                placeholder="Esim. kirjaa yksi palaveritilanne ennen seuraavaa tapaamista" />
            )}
          </div>
          <div className="field"><span className="field-label">Sallitut omahoitoharjoitukset</span>
            <div className="chips">{library.map((a) => (
              <button key={a.id} type="button" className="chip" aria-pressed={plan.allowedActivityIds.includes(a.id)} onClick={() => toggle('allowedActivityIds', a.id)}>{a.title}</button>
            ))}</div>
          </div>
          <div className="field"><span className="field-label">Check-in-tiheys (mieliala ja ahdistus)</span>
            <Segmented label="Check-in-tiheys" value={plan.checkInsPerWeek} onChange={(v) => setPlan({ ...plan, checkInsPerWeek: v })}
              options={[{ value: 1, label: '1× / vko' }, { value: 2, label: '2× / vko' }, { value: 3, label: '3× / vko' }]} />
          </div>
          <label className="field"><span className="field-label">Seurataan</span>
            <input value={plan.track} onChange={(e) => setPlan({ ...plan, track: e.target.value })} /></label>
          <label className="field"><span className="field-label">Älä käsittele (vapaa teksti)</span>
            <textarea rows={2} value={plan.doNotAddress} onChange={(e) => setPlan({ ...plan, doNotAddress: e.target.value })}
              placeholder="Esim. työpaikan henkilöristiriidat käsitellään tapaamisissa" /></label>
          <div className="row-gap">
            <button type="button" className="btn btn-primary" disabled={!canSave} onClick={save}><CheckIcon size={16} /> Tallenna ja ota käyttöön</button>
            {(config || therapy.suggestedPlan) && (
              <button type="button" className="btn btn-quiet" onClick={() => { setPlan(initial); setEditing(false); }}>Peruuta</button>
            )}
          </div>
        </div>
      ) : (
        <>
          <dl className="plan-dl plan-dl-grid">
            <div className="plan-dl-wide"><dt>Päätavoite</dt><dd>{shown.primaryGoal}</dd></div>
            <div><dt>Välitehtävä</dt><dd>{shown.homeworkTool ? `${toolTitle(shown.homeworkTool)}${shown.homeworkNote ? ` – ${shown.homeworkNote}` : ''}` : 'Ei välitehtävää'}</dd></div>
            <div><dt>Check-in</dt><dd>{shown.checkInsPerWeek}× / viikko{shown.track ? ` · seurataan: ${shown.track}` : ''}</dd></div>
            <div className="plan-dl-wide"><dt>Sallitut harjoitukset</dt><dd className="chips">
              {shown.allowedTools.map((t) => <span key={t} className="chip-static chip-tool">{toolTitle(t)}</span>)}
              {library.filter((a) => shown.allowedActivityIds.includes(a.id)).map((a) => <span key={a.id} className="chip-static">{a.title}</span>)}
            </dd></div>
            {shown.doNotAddress && <div className="plan-dl-wide"><dt>Älä käsittele</dt><dd>{shown.doNotAddress}</dd></div>}
          </dl>
          {config && <p className="statement"><CheckIcon size={16} /> Asiakkaalle näytetään: ”{therapy.mode.statement}”</p>}
          <div className="row-gap">
            {!config && <button type="button" className="btn btn-primary" disabled={!canSave} onClick={save}><CheckIcon size={16} /> Ota käyttöön</button>}
            <button type="button" className={`btn ${config ? 'btn-secondary btn-sm' : 'btn-quiet'}`} onClick={() => setEditing(true)}>
              {config ? 'Muokkaa määritystä' : 'Muokkaa ehdotusta'}
            </button>
          </div>
        </>
      )}
    </section>
  );
}

/** Ending therapy starts the follow-up: mood and anxiety weekly, a maintenance plan, and a change goes back to the care team. */
function EndTherapy({ row, therapistId }: { row: TherapistClientRow; therapistId: string }) {
  const { view, run, busy } = useValituki();
  const suggested = row.therapy.suggestedAftercare ?? { checkInsPerWeek: 1, allowedTools: [], maintenance: '', warningSigns: '' };
  const [plan, setPlan] = useState<AftercareInput>(suggested);
  const [open, setOpen] = useState(false);
  const tools = view.therapist.tools;
  return (
    <section className="card plan-card th-end">
      <div className="card-row">
        <h2 className="card-title-lg"><FlagIcon size={19} /> Terapian päättäminen ja seuranta</h2>
        {!open && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(true)}>Laadi ylläpitosuunnitelma</button>}
      </div>
      <p className="muted">Terapian jälkeen Mieliluotsi seuraa vointia sovitussa rytmissä. Jos vointi laskee, hoitotiimi saa tarkistuspyynnön.</p>
      {open && (
        <div className="plan-form">
          <label className="field"><span className="field-label">Ylläpitosuunnitelma – mitä jatkaa</span>
            <textarea rows={3} value={plan.maintenance} onChange={(e) => setPlan({ ...plan, maintenance: e.target.value })} /></label>
          <label className="field"><span className="field-label">Merkit, joihin reagoida</span>
            <textarea rows={2} value={plan.warningSigns} onChange={(e) => setPlan({ ...plan, warningSigns: e.target.value })} /></label>
          <div className="field"><span className="field-label">Harjoitukset seurannassa</span>
            <div className="chips">{tools.map((t) => (
              <button key={t.id} type="button" className="chip" aria-pressed={plan.allowedTools.includes(t.id)}
                onClick={() => setPlan({ ...plan, allowedTools: plan.allowedTools.includes(t.id) ? plan.allowedTools.filter((x) => x !== t.id) : [...plan.allowedTools, t.id] })}>{t.title}</button>
            ))}</div>
          </div>
          <div className="field"><span className="field-label">Check-in seurannassa</span>
            <Segmented label="Check-in seurannassa" value={plan.checkInsPerWeek} onChange={(v) => setPlan({ ...plan, checkInsPerWeek: v })}
              options={[{ value: 1, label: '1× / vko' }, { value: 2, label: '2× / vko' }]} />
          </div>
          <div className="row-gap">
            <button type="button" className="btn btn-primary" disabled={busy || !plan.maintenance.trim()}
              onClick={() => run((s) => api.endTherapy(s, therapistId, row.clientId, plan), () => 'Terapia päättyi. Seuranta terapian jälkeen alkoi, ja asiakkaalle ilmoitettiin.')}>
              <CheckIcon size={16} /> Päätä terapia ja siirrä seurantaan
            </button>
            <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)}>Peruuta</button>
          </div>
          <p className="muted small">Ehdotus on koottu asiakkaan harjoittelusta ja hyödylliseksi arvioiduista harjoituksista. Muokkaa vapaasti.</p>
        </div>
      )}
    </section>
  );
}

function AftercareSummary({ row }: { row: TherapistClientRow }) {
  const plan = row.therapy.aftercare;
  if (!plan) return null;
  return (
    <section className="card plan-card">
      <div className="card-row">
        <h2 className="card-title-lg"><FlagIcon size={19} /> Seuranta terapian jälkeen</h2>
        <Pill tone="brand">Alkoi {fmtDate(plan.createdAt)}</Pill>
      </div>
      <dl className="plan-dl">
        <div><dt>Ylläpitosuunnitelma</dt><dd>{plan.maintenance}</dd></div>
        {plan.warningSigns && <div><dt>Merkit, joihin reagoida</dt><dd>{plan.warningSigns}</dd></div>}
        <div><dt>Check-in</dt><dd>{plan.checkInsPerWeek}× / viikko – mieliala ja ahdistus</dd></div>
      </dl>
      <p className="muted small">Jos vointi laskee, hoitotiimi saa tarkistuspyynnön. Asiakas voi aina pyytää yhteydenottoa.</p>
    </section>
  );
}
