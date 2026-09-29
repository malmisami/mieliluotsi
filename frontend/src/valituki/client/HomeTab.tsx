import { useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtShort } from '../format';
import {
  AlertIcon, ArrowRightIcon, CalendarIcon, ChatIcon, CheckIcon, ChevronRightIcon, CrossIcon, FlaskIcon, LeafIcon, SendIcon,
  SparkleIcon, StairsIcon, StethoscopeIcon, ThoughtIcon,
} from '../icons';
import { Scale5 } from '../components/ui';
import type { PracticeTask } from '../types';
import { useClientUI } from './ClientApp';

const MOODS: { value: number; short: string }[] = [
  { value: 1, short: 'Tosi huonosti' }, { value: 2, short: 'Huonosti' }, { value: 3, short: 'Kohtalaisesti' },
  { value: 4, short: 'Hyvin' }, { value: 5, short: 'Tosi hyvin' },
];

/** Today's mood and anxiety right after the intake – the first point of the client's own baseline, not a comparison with others. */
function BaselineCard() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const [mood, setMood] = useState<number | null>(null);
  const [anxiety, setAnxiety] = useState<number | null>(null);
  const demoMood = client.intake.demoMood;
  return (
    <section className="cx-baseline">
      <Scale5 name="Miten voit tänään?" value={mood} onChange={setMood} labels={view.meta.labels.moodScale} />
      <p className="cx-baseline-q">Kuinka paljon ahdistusta tai jännitystä olet tuntenut tänään?</p>
      <Scale5 name="Kuinka paljon ahdistusta tai jännitystä?" value={anxiety} onChange={setAnxiety} labels={view.meta.labels.anxietyScale} />
      {demoMood && mood === null && (
        <button type="button" className="link-btn" onClick={() => { setMood(demoMood); setAnxiety(3); }}>
          Käytä demovastausta (mieliala {demoMood}, ahdistus 3)
        </button>
      )}
      <button type="button" className="cx-btn cx-btn-dark cx-btn-block" disabled={busy || mood === null}
        onClick={() => mood !== null && run((s) => api.recordBaseline(s, client.id, { mood, anxiety }),
          () => 'Kiitos! Tästä tulee oma lähtötasosi – vointiasi verrataan siihen, ei muihin.')}>
        Tallenna
      </button>
    </section>
  );
}

export default function HomeTab() {
  const { view, run, busy } = useValituki();
  const { client, openSheet, openTab, startTool, send, answerMood, doTask } = useClientUI();
  const [text, setText] = useState('');
  const today = view.meta.currentDate;
  const practice = client.practice;
  const guided = client.guided;
  const due = client.checkIn.due;
  const checkedInToday = client.progress.series.some((p) => p.date === today);
  const mode = client.modeKey;
  const todayTasks = practice.tasks.filter((t) => t.dueDate && t.dueDate <= today);
  const nextTask = practice.tasks.find((t) => t.dueDate && t.dueDate > today);
  const activity = client.today;
  const pattern = client.memory.pending.find((i) => i.kind === 'pattern');
  const feedbackPending = client.matching.feedback.eligible && client.matching.feedback.given.length === 0;
  const featured = practice.tools.find((t) => t.id === 'thought_record' && t.allowed) ?? practice.tools.find((t) => t.allowed);
  // Right after the intake the first "Miten voit tänään?" sets the client's own baseline: mood and anxiety on one card.
  const needsBaseline = client.checkIn.needsBaseline;
  const askMood = needsBaseline || Boolean(due) || !checkedInToday;

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    setText('');
    void send(value);
  }

  return (
    <div className="cx-screen cx-home">
      <p className="cx-mode">
        {mode === 'therapy_support' ? <><StethoscopeIcon size={14} /> Terapian välituki · {client.mode.therapistName}</>
          : mode === 'aftercare_support' ? <><CheckIcon size={14} /> Seuranta terapian jälkeen</>
            : <><SparkleIcon size={14} /> Mieliluotsi · odotusajan tuki</>}
      </p>
      <h1 className="cx-greeting">Hei {client.firstName},<br />{askMood ? 'miten voit tänään?' : 'mitä mielessäsi on?'}</h1>

      {needsBaseline ? <BaselineCard /> : askMood && (
        <div className="cx-moods" role="group" aria-label="Miten voit tänään? Valitse 1–5">
          {MOODS.map((m) => (
            <button key={m.value} type="button" className={`cx-mood cx-mood-${m.value}`} disabled={busy} onClick={() => answerMood(m.value)}>
              <span className="cx-mood-n">{m.value}</span>
              <span className="cx-mood-w">{m.short}</span>
            </button>
          ))}
        </div>
      )}

      <form className="cx-ask" onSubmit={submit}>
        <label className="visually-hidden" htmlFor="home-ask">Kirjoita Mieliluotsille</label>
        <textarea id="home-ask" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Kirjoita, mitä mielessäsi on…"
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e); }} />
        <button type="submit" className="cx-send" aria-label="Lähetä" disabled={busy || !text.trim()}><SendIcon size={18} /></button>
      </form>
      {client.demoMessage && (
        <button type="button" className="cx-demo-chip" disabled={busy} onClick={() => send(client.demoMessage ?? '')}>
          <span className="cx-demo-tag">Demoviesti</span><span>{client.demoMessage}</span>
        </button>
      )}

      {guided && (
        <button type="button" className="cx-continue" onClick={() => openTab('keskustelu')}>
          <span className="cx-bot-avatar" aria-hidden="true"><BotFace /></span>
          <span className="cx-continue-text">
            <strong>Jatka: {guided.title}</strong>
            <span>Kysymys {guided.stepIndex}/{guided.stepCount} odottaa vastaustasi</span>
          </span>
          <ChevronRightIcon size={20} />
        </button>
      )}

      <section className="cx-section">
        <h2 className="cx-h2">Päiväsi</h2>
        <ol className="cx-day">
          {due && (
            <DayItem icon={<ChatIcon size={16} />} tag={due.kind === 'extra' ? 'Lisä-check-in' : 'Check-in'} title="Miten voit tänään?"
              text="Mieliala ja ahdistus – alle minuutin" action={guided?.tool === 'checkin' ? 'Jatka' : 'Aloita'} busy={busy}
              onAction={() => (guided?.tool === 'checkin' ? openTab('keskustelu') : startTool('checkin', {}, 'home'))} />
          )}
          {todayTasks.map((task) => <TaskItem key={task.id} task={task} busy={busy} onAction={() => doTask(task.id)} />)}
          {activity && (
            <DayItem icon={<LeafIcon size={16} />} tag="Päivän askel" title={activity.title}
              text={activity.status === 'completed' ? 'Tehty – kiitos!' : activity.status === 'skipped' ? 'Ohitettu' : `${activity.estimatedDuration} min · hyväksytty harjoitus`}
              action={activity.status === 'suggested' ? 'Avaa' : undefined} done={activity.status !== 'suggested'} busy={busy}
              onAction={() => openSheet({ type: 'activity', activityId: activity.id })} />
          )}
          {!due && todayTasks.length === 0 && !activity && (
            <li className="cx-day-empty">Ei sovittua tälle päivälle. {nextTask ? `Seuraava: ${nextTask.title} (${nextTask.dueLabel.toLowerCase()}).` : 'Voit aloittaa harjoituksen milloin tahansa.'}</li>
          )}
        </ol>
        {client.checkIn.nextLabel && !due && <p className="cx-fine"><CalendarIcon size={13} /> Seuraava check-in {client.checkIn.nextLabel} · {client.checkIn.frequencyText}</p>}
      </section>

      <ProgressTeaser />

      {client.waiting.reviewPending && (
        <section className="cx-note cx-note-warn" role="status">
          <AlertIcon size={18} />
          <div>
            <p className="cx-note-title">Mieliluotsi huomasi muutoksen</p>
            <p>{client.trend.text} {client.waiting.reviewText}</p>
          </div>
        </section>
      )}

      {pattern && (
        <section className="cx-insight">
          <p className="cx-eyebrow"><SparkleIcon size={14} /> Huomasimme jotain</p>
          <p className="cx-insight-text">{pattern.text}</p>
          <p className="cx-fine">Perustuu: {(pattern.evidence.basis ?? []).filter(Boolean).join(' · ')}</p>
          <div className="cx-row">
            <button type="button" className="cx-btn cx-btn-dark cx-btn-sm" disabled={busy}
              onClick={() => run((s) => api.decideInsight(s, client.id, pattern.id, 'approve'), () => 'Havainto tallennettiin Therapy Fit Profileen. Voit muuttaa sen käyttöoikeutta Tietoni-sivulla.')}>
              <CheckIcon size={15} /> Tämä tuntuu oikealta
            </button>
            <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy}
              onClick={() => run((s) => api.decideInsight(s, client.id, pattern.id, 'reject'), () => 'Kiitos – havaintoa ei käytetä mihinkään.')}>
              <CrossIcon size={15} /> Ei kuvaa tilannettani
            </button>
          </div>
        </section>
      )}

      {feedbackPending && (
        <button type="button" className="cx-note cx-note-brand cx-note-btn" onClick={() => openTab('polku')}>
          <ChatIcon size={18} />
          <span><span className="cx-note-title">Miltä yhteistyö terapeutin kanssa tuntuu?</span>Lyhyt palaute – ei vaihda terapeuttia automaattisesti.</span>
          <ChevronRightIcon size={18} />
        </button>
      )}

      <JourneyCard />

      {featured && !guided && (
        <button type="button" className={`cx-guided cx-tool-${featured.id}`} disabled={busy} onClick={() => startTool(featured.id, {}, 'home')}>
          <span className="cx-guided-icon" aria-hidden="true">{toolIcon(featured.id, 22)}</span>
          <span className="cx-guided-text">
            <span className="cx-guided-title">Aloita ohjattu harjoitus <span className="cx-guided-min">{featured.duration} min</span></span>
            <span className="cx-guided-sub">{featured.title}: {featured.description}</span>
          </span>
        </button>
      )}
    </div>
  );
}

function DayItem({ icon, tag, title, text, action, onAction, done = false, busy, secondary }: {
  icon: ReactNode; tag: string; title: string; text: string; action?: string; onAction?: () => void; done?: boolean; busy: boolean;
  secondary?: ReactNode;
}) {
  return (
    <li className={`cx-day-item ${done ? 'is-done' : ''}`}>
      <span className="cx-day-dot" aria-hidden="true">{done ? <CheckIcon size={13} /> : icon}</span>
      <div className="cx-day-card">
        <span className="cx-tag">{tag}</span>
        <p className="cx-day-title">{title}</p>
        <p className="cx-day-text">{text}</p>
        {(action || secondary) && (
          <div className="cx-row">
            {action && onAction && <button type="button" className="cx-btn cx-btn-dark cx-btn-sm" disabled={busy} onClick={onAction}>{action} <ArrowRightIcon size={14} /></button>}
            {secondary}
          </div>
        )}
      </div>
    </li>
  );
}

function TaskItem({ task, busy, onAction }: { task: PracticeTask; busy: boolean; onAction: () => void }) {
  const { run } = useValituki();
  const { client } = useClientUI();
  const icon = task.kind === 'exposure_step' ? <StairsIcon size={16} /> : task.kind === 'experiment' ? <FlaskIcon size={16} />
    : task.kind === 'homework' ? <StethoscopeIcon size={16} /> : <LeafIcon size={16} />;
  return (
    <DayItem icon={icon} tag={`${task.kindLabel}${task.overdue ? ' · myöhässä' : ''}`} title={task.title}
      text={task.kind === 'homework' ? `${task.assignedByLabel}: ${task.detail || 'välitehtävä'}` : task.detail || task.dueLabel}
      action={task.actionLabel} busy={busy} onAction={onAction}
      secondary={task.kind !== 'homework' ? (
        <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy}
          onClick={() => run((s) => api.clientTaskAction(s, client.id, task.id, 'later'), () => 'Siirretty huomiseen.')}>Siirrä huomiseen</button>
      ) : undefined} />
  );
}

const PATH = [
  { key: 'wait', label: 'Odotus' },
  { key: 'therapist', label: 'Terapeutti' },
  { key: 'therapy', label: 'Terapia' },
  { key: 'after', label: 'Seuranta' },
];

export function pathIndex(phase: string): number {
  if (phase === 'AFTERCARE') return 3;
  if (phase === 'THERAPY_ACTIVE') return 2;
  if (['MATCH_PROPOSED', 'MATCH_ACCEPTED'].includes(phase)) return 1;
  return 0;
}

export function PathSteps({ phase }: { phase: string }) {
  const index = pathIndex(phase);
  return (
    <ol className="cx-path" aria-label="Hoitopolku">
      {PATH.map((step, i) => (
        <li key={step.key} className={i < index ? 'done' : i === index ? 'current' : ''} aria-current={i === index ? 'step' : undefined}>
          <span className="cx-path-dot" aria-hidden="true" />
          <span>{step.label}</span>
        </li>
      ))}
    </ol>
  );
}

function JourneyCard() {
  const { client, openTab } = useClientUI();
  const matching = client.matching;
  const text = matching.stage === 'choose' ? `${Math.min(matching.decision?.shownCount ?? 3, matching.candidates.length)} sopivaa terapeuttia odottaa valintaasi`
    : matching.stage === 'booked' && matching.booking ? `Ensimmäinen tapaaminen ${matching.booking.startText} · ${matching.booking.therapist.name}`
      : matching.stage === 'therapy' && matching.booking ? `Terapia käynnissä · ${matching.booking.therapist.name}`
        : matching.stage === 'aftercare' ? 'Terapia päättyi – seuranta jatkuu ylläpitosuunnitelman mukaan'
          : matching.stage === 'on_hold' ? 'Terapeutin etsintä jatkuu ammattilaisen tarkistuksen jälkeen'
            : 'Etsimme tilanteeseesi sopivaa terapeuttia';
  return (
    <button type="button" className="cx-journey" onClick={() => openTab('polku')}>
      <span className="cx-journey-head">
        <span className="cx-eyebrow">Hoitopolku</span>
        {client.waiting.daysWaiting !== null && client.modeKey === 'waiting_support' && (
          <span className="cx-fine">{client.waiting.daysWaiting} pv avun hakemisesta</span>
        )}
      </span>
      <PathSteps phase={client.phase} />
      <span className="cx-journey-text">{text} {matching.stage === 'choose' && <span className="cx-new">Uutta</span>}</span>
    </button>
  );
}

function ProgressTeaser() {
  const { client, openTab } = useClientUI();
  const series = client.progress.series.filter((p) => p.mood !== null);
  const last = series[series.length - 1];
  const stats = client.practice.stats;
  return (
    <button type="button" className="cx-teaser" onClick={() => openTab('edistyminen')}>
      <span className="cx-teaser-head">
        <span className="cx-teaser-title">Edistymisesi</span>
        <ChevronRightIcon size={18} />
      </span>
      <span className="cx-teaser-values">
        <span><i className="ma-swatch ma-mood" />Mieliala {last?.mood ?? '–'}/5</span>
        <span><i className="ma-swatch ma-anx" />Ahdistus {last?.anxiety ?? '–'}/5</span>
      </span>
      <span className="cx-teaser-sub">
        {stats.thoughtRecords + stats.exposureAttempts + stats.experimentsDone > 0
          ? `${stats.thoughtRecords} ajatusten tutkimista · ${stats.exposureAttempts} altistusaskelta · ${stats.experimentsDone} käyttäytymiskoetta`
          : last ? `Viimeisin check-in ${fmtShort(last.date)}` : 'Kaavio piirtyy check-inien myötä'}
      </span>
    </button>
  );
}

export function toolIcon(tool: string, size = 18) {
  if (tool === 'exposure') return <StairsIcon size={size} />;
  if (tool === 'experiment') return <FlaskIcon size={size} />;
  if (tool === 'checkin') return <ChatIcon size={size} />;
  return <ThoughtIcon size={size} />;
}

export function BotFace({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 34 34" aria-hidden="true">
      <rect width="34" height="34" rx="17" fill="var(--brand)" />
      <path d="M10 18.5c2 3 4.3 4.5 7 4.5s5-1.5 7-4.5" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="12.8" cy="13" r="2" fill="#9fe0d0" />
      <circle cx="21.2" cy="13" r="2" fill="#fff" />
    </svg>
  );
}
