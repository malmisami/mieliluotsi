import { Fragment, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtWeekday } from '../format';
import { InfoIcon, LifebuoyIcon, SendIcon, SparkleIcon } from '../icons';
import type { ChatMessage, GuidedView, SummaryData, ValitukiView } from '../types';
import { Examples, SummaryCard, WidgetPanel, describeValue } from './ChatWidgets';
import { useClientUI } from './ClientApp';
import { BotFace, toolIcon } from './HomeTab';

const TOOL_LABELS: Record<string, string> = { checkin: 'Tee check-in', thought_record: 'Ajatusten tutkiminen', exposure: 'Altistusporras',
  experiment: 'Käyttäytymiskoe' };

/** The conversation: Mieliluotsi's messages as plain text, the client's as bubbles. A guided exercise shows its current
    question's answer controls above the composer; free text always works too (it answers a text question). */
export default function ChatTab() {
  const { view, run, busy } = useValituki();
  const { client, openSheet, send, pending, withPending } = useClientUI();
  const guided = client.guided;
  const widget = guided?.widget ?? null;
  const [text, setText] = useState('');
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const questionId = guided?.questionId ?? null;

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [client.chat.length, busy, questionId, pending]);

  // Each new question starts with an empty composer – in demo mode (not Claude) a text question's scripted answer is
  // already typed in it: press send or edit it first.
  const demoMode = view.meta.ai.configuredMode === 'DEMO_AI_MODE';
  const demoText = demoMode && widget?.type === 'text' && typeof guided?.demoAnswer === 'string' ? guided.demoAnswer : '';
  // A multiple choice (what changed, emotions, thinking traps) is answered with the send button: the picked options are kept
  // per question.
  const [picked, setPicked] = useState<{ question: string | null; values: string[] }>({ question: null, values: [] });
  const picking = widget?.type === 'multi' || widget?.type === 'traps';
  const multi = picking && picked.question === questionId ? picked.values : [];
  const draftKey = `${questionId ?? ''}|${demoMode}`;
  const [draftFor, setDraftFor] = useState<string | null>(null);
  if (draftFor !== draftKey) {
    setDraftFor(draftKey);
    setText(demoText);
  }

  async function answerWith(current: GuidedView, value: unknown, skip = false): Promise<ValitukiView | null> {
    let latest: ValitukiView | null = null;
    await withPending(skip ? '' : describeValue(value, current.widget), () => run(async (s) => {
      const response = await api.answerPractice(s, client.id, { sessionId: current.id, stepKey: current.stepKey, value, skip });
      latest = response.view;
      return response;
    }));
    return latest;
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const value = text.trim();
    if (busy) return;
    if (!value && guided && picking && multi.length > 0) {
      await answerWith(guided, multi);
      return;
    }
    if (!value) return;
    setText('');
    if (!(await send(value))) setText(value);  // not sent: keep what was written
  }


  const progress = guided ? Math.round(((guided.stepIndex - 1) / Math.max(1, guided.stepCount)) * 100) : 0;
  const tools = client.practice.allowedTools.filter((t) => TOOL_LABELS[t]);

  return (
    <div className="cx-chat">
      <div className="cx-chat-head">
        <span className="cx-bot-avatar" aria-hidden="true"><BotFace size={34} /></span>
        <div className="cx-chat-who">
          <p className="cx-chat-name">{guided ? guided.title : 'Mieliluotsi'}</p>
          <p className="cx-chat-sub">{guided ? `Kysymys ${guided.stepIndex}/${guided.stepCount} · voit ohittaa tai lopettaa` : 'Tekoälyavusteinen tuki – ei terapeutti eikä päivystys'}</p>
        </div>
        {guided && (
          <button type="button" className="cx-stop" disabled={busy}
            onClick={() => run((s) => api.stopPractice(s, client.id, guided.id))}>Lopeta</button>
        )}
        {guided && <span className="cx-chat-progress" aria-hidden="true"><span style={{ width: `${progress}%` }} /></span>}
      </div>

      <div className="cx-chat-log" ref={logRef} aria-live="polite">
        <p className="cx-chat-disclaimer"><InfoIcon size={14} /> Mieliluotsi ei ole terapeutti, eikä keskustelua seurata jatkuvasti. Hätätilanteessa soita 112.</p>
        {client.chat.length === 0 && (
          <p className="cx-msg-bot cx-msg-first">Hei {client.firstName}! Voit kertoa, mitä mielessäsi on – tai aloittaa ohjatun harjoituksen alta.</p>
        )}
        {client.chat.map((m, i) => (
          <Fragment key={m.id}>
            {(i === 0 || client.chat[i - 1].createdAt.slice(0, 10) !== m.createdAt.slice(0, 10)) && (
              <p className="cx-day-sep"><span>{fmtWeekday(m.createdAt)}</span></p>
            )}
            <Message message={m} previous={client.chat[i - 1]} busy={busy}
              onChoose={(option) => run((s) => api.chooseOffer(s, client.id, m.id, option))} onHelp={() => openSheet({ type: 'help' })} />
          </Fragment>
        ))}
        {pending && <div className="cx-msg-me is-pending"><p>{pending}</p></div>}
        {busy && <div className="cx-typing" aria-label="Mieliluotsi kirjoittaa"><i /><i /><i /></div>}
      </div>

      <div className="cx-dock">
        <div className="cx-dock-top">
          {guided && widget && widget.type !== 'text' && (
            <WidgetPanel key={questionId ?? 'none'} widget={widget} busy={busy} selected={multi}
              onSelect={(values) => setPicked({ question: questionId, values })}
              onAnswer={(value) => answerWith(guided, value)} onSkip={() => answerWith(guided, null, true)} />
          )}
          {guided && widget?.type === 'text' && (
            <Examples widget={widget} busy={busy} onUse={(example) => { setText(example); inputRef.current?.focus(); }} />
          )}
          {!guided && (
            <div className="cx-quick" role="group" aria-label="Aloita ohjattu harjoitus">
              {client.demoMessage && (
                <button type="button" className="cx-demo-chip cx-demo-chip-sm" disabled={busy} onClick={() => run((s) => api.sendMessage(s, client.id, client.demoMessage ?? ''))}>
                  <span className="cx-demo-tag">Demoviesti</span><span>{client.demoMessage}</span>
                </button>
              )}
              {tools.map((tool) => (
                <button key={tool} type="button" className="cx-quick-chip" disabled={busy}
                  onClick={() => run((s) => api.startPractice(s, client.id, tool, {}, 'chat'))}>
                  {toolIcon(tool, 15)} {TOOL_LABELS[tool]}
                </button>
              ))}
            </div>
          )}
        </div>
        <form className="cx-composer" onSubmit={submit}>
          <label className="visually-hidden" htmlFor="chat-input">{guided?.questionText ?? 'Viesti Mieliluotsille'}</label>
          <textarea id="chat-input" ref={inputRef} rows={Math.min(4, Math.max(1, Math.ceil(text.length / 34)))} value={text} onChange={(e) => setText(e.target.value)}
            placeholder={widget?.type === 'text' ? widget.placeholder || 'Kirjoita vastaus…'
              : picking ? (multi.length ? `${multi.length} valittu – lähetä` : 'Valitse yksi tai useampi ja lähetä…')
                : guided ? 'Vastaa valitsemalla – tai kirjoita…' : 'Kirjoita viesti…'}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void submit(); } }}  />
          <button type="submit" className="cx-send" aria-label="Lähetä" disabled={busy || (!text.trim() && multi.length === 0)}><SendIcon size={18} /></button>
        </form>
        {guided && widget?.type === 'text' && widget.skippable && (
          <button type="button" className="cw-skip cw-skip-center" disabled={busy} onClick={() => answerWith(guided, null, true)}>
            {widget.skipLabel || 'Ohita kysymys'}
          </button>
        )}
      </div>
    </div>
  );
}

function Message({ message: m, previous, busy, onChoose, onHelp }: {
  message: ChatMessage; previous?: ChatMessage; busy: boolean; onChoose: (option: string) => void; onHelp: () => void;
}) {
  if (m.role === 'client') {
    return (
      <div className={`cx-msg-me ${m.kind === 'skip' ? 'is-skip' : ''}`}>
        <p>{m.text}</p>
      </div>
    );
  }
  if (m.safetyLevel >= 3) {
    return (
      <div className="cx-msg-safety" role="alert">
        <LifebuoyIcon size={18} />
        <div>
          <p>{m.text}</p>
          <button type="button" className="cx-btn cx-btn-rose cx-btn-sm" onClick={onHelp}>Apua nyt</button>
        </div>
      </div>
    );
  }
  if (m.kind === 'summary' && m.widget) return <SummaryCard data={m.widget.data as unknown as SummaryData} />;
  if (m.kind === 'notice') return <p className="cx-msg-notice">{m.text}</p>;
  const grouped = previous && previous.role === 'assistant' && previous.kind !== 'summary' && previous.createdAt.slice(0, 10) === m.createdAt.slice(0, 10);
  return (
    <div className={`cx-msg-bot ${m.kind === 'question' ? 'is-question' : ''} ${grouped ? 'is-grouped' : ''}`}>
      <p>{m.text}</p>
      {m.kind === 'offer' && m.widget && m.actionable && (
        <div className="cx-offer" role="group" aria-label="Vaihtoehdot">
          {m.widget.options.map((o, i) => (
            <button key={o.value} type="button" className={`cx-btn cx-btn-sm ${i === 0 ? 'cx-btn-dark' : 'cx-btn-ghost'}`} disabled={busy}
              onClick={() => onChoose(o.value)}>{o.label}</button>
          ))}
        </div>
      )}
      {m.textSource === 'live' && <span className="cx-source"><SparkleIcon size={11} /> Tekoälyn muotoilema</span>}
      {m.textSource === 'fallback' && <span className="cx-source">Valmis tekstipohja – tekoälyn vastausta ei käytetty</span>}
    </div>
  );
}
