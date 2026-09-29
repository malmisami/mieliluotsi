import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtShort } from '../format';
import { ArrowRightIcon, CheckIcon, ClockIcon, EditIcon, InfoIcon, QuoteIcon, SendIcon, SparkleIcon } from '../icons';
import { Pill, Segmented } from '../components/ui';
import type { ConsentScope, IntakeProposal, ValitukiView } from '../types';
import { useClientUI } from './ClientApp';


export default function Intake() {
  const { client } = useClientUI();
  switch (client.intake.status) {
    case 'not_started':
    case 'consent':
      return <Welcome />;
    case 'conversation':
      return <Conversation />;
    case 'review':
      return <Review />;
    case 'rhythm':
      return <Rhythm />;
    default:
      return null;
  }
}

function Welcome() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const [consent, setConsent] = useState<ConsentScope>(client.intake.consentDefaults);
  const labels = view.meta.labels.consents;
  return (
    <div className="screen intake-welcome iw">
      <h1 className="display iw-hello">Hei {client.firstName}</h1>
      <p className="lead">Olet terapian jonossa. Normaalisti tästä alkaisi odotus – nyt tuki voi alkaa heti.</p>
      <div className="card wait-card wait-hero">
        <p className="wait-hero-label"><ClockIcon size={16} /> Arvioitu odotus terapiaan</p>
        <p className="wait-hero-value">{client.waiting.estimatedWait}</p>
        <p className="wait-hero-meta">Hait apua {fmtShort(client.waiting.soughtHelpAt)} · {client.waiting.service}</p>
      </div>
      <p className="iw-text">Aloitetaan lyhyellä keskustelulla. Lopuksi näet yhteenvedon ja päätät itse, mitä tallennetaan.</p>
      <div className="card consent-card iw-consent">
        <h3 className="card-title">Tietojesi käyttö</h3>
        {(Object.keys(labels) as (keyof ConsentScope)[]).map((key) => (
          <label key={key} className="switch-row" title={labels[key].description}>
            <span className="switch-title">{labels[key].title}</span>
            <input type="checkbox" className="switch" checked={consent[key]} onChange={(e) => setConsent({ ...consent, [key]: e.target.checked })} />
          </label>
        ))}
        <details className="iw-more">
          <summary>Mitä nämä tarkoittavat?</summary>
          <dl>{(Object.keys(labels) as (keyof ConsentScope)[]).map((key) => (
            <div key={key}><dt>{labels[key].title}</dt><dd>{labels[key].description}</dd></div>
          ))}</dl>
          <p>Voit muuttaa näitä milloin tahansa Tietoni-sivulla.</p>
        </details>
      </div>
      <p className="iw-notice"><InfoIcon size={14} /> Ei terapeutti eikä päivystys – hätätilanteessa soita 112.</p>
      <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy}
        onClick={() => run((s) => api.intakeStart(s, client.id, consent))}>
        Aloita keskustelu <ArrowRightIcon size={18} />
      </button>
    </div>
  );
}

function Conversation() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const intake = client.intake;
  const [text, setText] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const pending = intake.pendingQuestion;

  // Demo mode (not Claude): each question's scripted answer is already typed in the field – press send or edit it first.
  const demoMode = view.meta.ai.configuredMode === 'DEMO_AI_MODE';
  const draftKey = `${pending?.key ?? ''}|${demoMode}`;
  const [draftFor, setDraftFor] = useState<string | null>(null);
  if (draftFor !== draftKey) {
    setDraftFor(draftKey);
    setText(demoMode ? pending?.demoAnswer ?? '' : '');
  }

  // Scroll the phone to the very bottom: scrollIntoView would leave the newest message under the sticky composer.
  useEffect(() => {
    const scroller = endRef.current?.closest('.phone-scroll');
    scroller?.scrollTo({ top: scroller.scrollHeight, behavior: 'smooth' });
  }, [intake.messages.length, busy, pending?.key]);

  async function send(answer: string): Promise<ValitukiView | null> {
    let latest: ValitukiView | null = null;
    await run(async (s) => {
      const response = await api.intakeAnswer(s, client.id, answer);
      latest = response.view;
      return response;
    });
    return latest;
  }

  async function submit() {
    const answer = text.trim();
    if (!answer) return;
    setText('');
    await send(answer);
  }


  const total = intake.plan.length;
  const step = Math.min(total, intake.answeredCount + 1);
  return (
    <div className="chat-screen">
      <div className="chat-progress" aria-label={`Kysymys ${step}/${total}`}>
        {intake.plan.map((q, i) => <span key={q.key} className={i < intake.answeredCount ? 'done' : i === intake.answeredCount ? 'current' : ''} />)}
      </div>
      <div className="chat-log" aria-live="polite">
        {intake.messages.map((m) => (
          <div key={m.id} className={`bubble-row ${m.role === 'client' ? 'me' : 'bot'}`}>
            {m.role === 'assistant' && <span className="bot-mark" aria-hidden="true" />}
            <div className={`bubble ${m.role === 'client' ? 'bubble-me' : m.questionKey ? 'bubble-q' : 'bubble-bot'}`}>{m.text}</div>
          </div>
        ))}
        {busy && <div className="bubble-row bot"><span className="bot-mark" aria-hidden="true" /><div className="bubble bubble-bot typing"><i /><i /><i /></div></div>}
        <div ref={endRef} />
      </div>
      <div className="composer">
        <div className="composer-row">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={Math.min(5, Math.max(2, Math.ceil(text.length / 36)))}
            placeholder="Kirjoita omin sanoin…" aria-label="Vastauksesi"
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void submit(); } }} disabled={busy} />
          <button type="button" className="send-btn" aria-label="Lähetä" disabled={busy || !text.trim()} onClick={submit}><SendIcon size={18} /></button>
        </div>
        <div className="composer-actions">
          {pending && pending.key !== 'reason' && (
            <button type="button" className="link-btn" disabled={busy} onClick={() => run((s) => api.intakeSkip(s, client.id))}>Ohita kysymys</button>
          )}
          {intake.canFinish && (
            <button type="button" className="link-btn" disabled={busy} onClick={() => run((s) => api.intakeFinish(s, client.id))}>Siirry yhteenvetoon</button>
          )}
        </div>
      </div>
    </div>
  );
}

function ProposalChips({ proposal }: { proposal: IntakeProposal }) {
  const { view } = useValituki();
  const labels = view.meta.labels;
  const s = proposal.structured as Record<string, unknown>;
  if (proposal.category === 'practical') {
    const langs = (s.languages as string[] | undefined) ?? [];
    const times = (s.times as string[] | undefined) ?? [];
    const days = (s.days as number[] | undefined) ?? [];
    return (
      <div className="chips">
        <span className="chip-static">{labels.formats[String(s.format ?? 'either')]}</span>
        {langs.map((l) => <span key={l} className="chip-static">{labels.languages[l]}</span>)}
        {times.map((t) => <span key={t} className="chip-static">{labels.times[t]}</span>)}
        {days.map((d) => <span key={d} className="chip-static">{labels.weekdays[d]}</span>)}
      </div>
    );
  }
  return null;
}

function Review() {
  const { run, busy } = useValituki();
  const { client } = useClientUI();
  const intake = client.intake;
  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  // Practical wishes (format, language, times) are saved with the rest but not shown here – the card stays about Sami.
  const main = intake.proposals.filter((p) => ['goal', 'working_style'].includes(p.category));
  const more = intake.proposals.filter((p) => !['goal', 'working_style', 'practical'].includes(p.category));

  async function saveEdits() {
    for (const proposal of intake.proposals) {
      const draft = drafts[proposal.id];
      if (draft !== undefined && draft.trim() && draft.trim() !== proposal.text) {
        await run((s) => api.updateProposal(s, client.id, proposal.id, { text: draft.trim() }));
      }
    }
    setDrafts({});
    setEditing(false);
  }

  function card(proposal: IntakeProposal) {
    return (
      <article key={proposal.id} className={`proposal prop-${proposal.category} ${proposal.included ? '' : 'prop-excluded'}`}>
        <header className="prop-head">
          <span className="prop-title">{proposal.title}</span>
          {proposal.editedByClient ? <Pill tone="brand" icon={<EditIcon size={12} />}>Muokkasit</Pill>
            : <Pill tone="violet" icon={<SparkleIcon size={12} />}>Tulkinta</Pill>}
        </header>
        {editing ? (
          <textarea className="prop-edit" rows={3} value={drafts[proposal.id] ?? proposal.text} aria-label={`Muokkaa: ${proposal.title}`}
            onChange={(e) => setDrafts({ ...drafts, [proposal.id]: e.target.value })} />
        ) : (
          <p className="prop-text">{proposal.text}</p>
        )}
        {!editing && <ProposalChips proposal={proposal} />}
        {proposal.userWords.length > 0 && (
          <div className="prop-quote">
            <p className="prop-quote-label"><QuoteIcon size={13} /> Sanoit keskustelussa</p>
            {proposal.userWords.map((w) => <p key={w} className="prop-quote-text">”{w}”</p>)}
          </div>
        )}
      </article>
    );
  }

  return (
    <div className="screen review-screen">
      <p className="eyebrow">Alkukeskustelun yhteenveto</p>
      <h1 className="display-sm">Ymmärsinkö tilanteesi oikein?</h1>
      <p className="muted">Nämä ovat vasta ehdotuksia. Mitään ei tallenneta eikä käytetä ennen kuin hyväksyt ne.</p>
      <div className="proposals">{[...main, ...more].map(card)}</div>
      <div className="stack-sm sticky-actions">
        {editing ? (
          <>
            <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy} onClick={saveEdits}>Tallenna muutokset</button>
            <button type="button" className="btn btn-quiet btn-block" onClick={() => { setDrafts({}); setEditing(false); }}>Peruuta</button>
          </>
        ) : (
          <>
            <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy}
              onClick={() => run((s) => api.intakeConfirm(s, client.id), () => 'Hyväksyit tulkinnat. Therapy Fit Profile luotiin vain hyväksymistäsi tiedoista.')}>
              <CheckIcon size={18} /> Kyllä, tämä kuvaa tilannettani
            </button>
            <button type="button" className="btn btn-secondary btn-block" disabled={busy} onClick={() => setEditing(true)}>
              <EditIcon size={17} /> Haluan muokata
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function Rhythm() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const options = view.meta.checkInFrequencyOptions;
  const demo = client.intake.demoRhythm;
  const [perWeek, setPerWeek] = useState<number>(demo ? demo.checkInDays.length : 3);
  const [style, setStyle] = useState<'brief' | 'warm'>(demo?.communicationStyle ?? 'brief');
  const days = options.find((o) => o.perWeek === perWeek)?.days ?? [0, 2, 5];
  return (
    <div className="screen rhythm-screen">
      <p className="eyebrow">Viimeinen askel</p>
      <h1 className="display-sm">Miten Mieliluotsi tukee sinua?</h1>
      <section className="card">
        <h3 className="card-title">Millaisia viestejä toivot?</h3>
        <Segmented label="Viestien sävy" value={style} onChange={setStyle}
          options={[{ value: 'brief', label: 'Lyhyitä ja asiallisia' }, { value: 'warm', label: 'Lämpimiä ja kannustavia' }]} />
      </section>
      <section className="card">
        <h3 className="card-title">Kuinka usein saan kysyä kuulumisiasi?</h3>
        <div className="radio-cards">
          {[...options].sort((a, b) => b.perWeek - a.perWeek).map((option) => (
            <button key={option.perWeek} type="button" className="radio-card" aria-pressed={perWeek === option.perWeek} onClick={() => setPerWeek(option.perWeek)}>
              <strong>{option.label}</strong>
              {option.perWeek === 3 && <span className="muted small">Suositus odotusajalle – muutokset huomataan ajoissa</span>}
            </button>
          ))}
        </div>
      </section>
      <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy}
        onClick={() => run((s) => api.intakeComplete(s, client.id, { checkInDays: days, communicationStyle: style }),
          () => 'Mieliluotsi on käytössä. Agentit loivat tukisuunnitelman ja valitsivat päivän ensimmäisen askeleen.')}>
        Aloita Mieliluotsi <ArrowRightIcon size={18} />
      </button>
    </div>
  );
}
