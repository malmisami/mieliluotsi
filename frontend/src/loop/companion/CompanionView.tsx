import { useEffect, useRef, useState } from 'react';
import { ChatIcon } from '../../icons';
import ContinuityPanel from '../../support/ContinuityPanel';
import { loopApi } from '../api';
import FullSummary from '../FullSummary';
import ProfessionalSummary from '../ProfessionalSummary';
import type { ChatAction, LoopDashboard } from '../types';
import KnowledgeCard from './KnowledgeCard';
import MessageBubble from './MessageBubble';

// the continuity engine's own questions first, then the situation and the automated care-need assessment
const SUGGESTIONS = [
  'Mitä olemme sopineet?',
  'Mikä on seuraava askel?',
  'Mitä olen jo kokeillut?',
  'Riittääkö omahoito?',
  'Mikä on tilanteeni?',
  'Minulla on ollut päänsärkyä ja huimausta pari päivää.',
  'Haluan ammattilaisen tekemän arvion.',
];

interface Props {
  dashboard: LoopDashboard;
  setDashboard: (dashboard: LoopDashboard) => void;
}

export default function CompanionView({ dashboard, setDashboard }: Props) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaryTarget, setSummaryTarget] = useState<string | 'full' | null>(null);
  const listRef = useRef<HTMLOListElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messages = dashboard.companion.messages;

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages.length]);

  async function run(call: () => Promise<{ dashboard: LoopDashboard }>) {
    setBusy(true);
    setError(null);
    try {
      const result = await call();
      setDashboard(result.dashboard);
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function send(message: string) {
    if (!message.trim() || busy) return;
    if (await run(() => loopApi.sendChat(message))) setText('');
    inputRef.current?.focus();
  }

  async function onAction(action: ChatAction, args?: Record<string, unknown>) {
    await run(() => loopApi.chatAction(action.id, args));
    inputRef.current?.focus();
  }

  if (summaryTarget === 'full') {
    return <FullSummary onBack={() => setSummaryTarget(null)} />;
  }
  if (summaryTarget) {
    return <ProfessionalSummary observationId={summaryTarget} onBack={() => setSummaryTarget(null)} onShared={setDashboard} />;
  }

  return (
    <div className="loop-layout companion-layout">
    <section className="panel chat-panel" aria-labelledby="companion-title">
      <div className="chat-head">
        <div className="panel-heading">
          <span className="panel-heading-icon" aria-hidden="true"><ChatIcon size={48} /></span>
          <h2 id="companion-title">Hyvinvointikumppani</h2>
        </div>
        <p className="muted small">
          Pidän omahoitosi käynnissä arjessa myös vastaanottojen välissä: muistan sovitut asiat, otan itse yhteyttä, ehdotan yhden
          askeleen kerrallaan ja huomaan, milloin tarvitaan ammattilaista. Voit myös kuvata oireesi – hoidon tarpeen arvio tehdään
          sääntöjen perusteella, ja ammattilaisen arvion voi aina pyytää.
        </p>
      </div>

      <ol className="chat-list" ref={listRef} role="log" aria-live="polite" aria-label="Keskustelu Hyvinvointikumppanin kanssa">
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            dashboard={dashboard}
            busy={busy}
            onAction={onAction}
            onOpenSummary={(id) => setSummaryTarget(id ?? 'full')}
          />
        ))}
      </ol>

      {error && <p className="form-error" role="alert">{error}</p>}

      <form
        className="chat-composer"
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
        }}
      >
        <label htmlFor="chat-input">Kirjoita viesti</label>
        <div className="composer-row">
          <textarea
            id="chat-input"
            ref={inputRef}
            rows={2}
            maxLength={1000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send(text);
              }
            }}
            placeholder="Esim. Mikä on tilanteeni?"
          />
          <button type="submit" disabled={busy || !text.trim()}>{busy ? 'Odota…' : 'Lähetä'}</button>
        </div>
      </form>

      <div className="suggestions" role="group" aria-label="Esimerkkiviestejä demoa varten">
        {SUGGESTIONS.map((suggestion) => (
          <button key={suggestion} type="button" className="chip-button" disabled={busy} onClick={() => send(suggestion)}>
            {suggestion}
          </button>
        ))}
      </div>
    </section>
    <aside className="loop-side" aria-label="Omahoidon jatkuvuus ja Hyvinvointikumppanin käyttämät tiedot">
      <ContinuityPanel dashboard={dashboard} setDashboard={setDashboard} />
      <KnowledgeCard dashboard={dashboard} />
    </aside>
    </div>
  );
}
