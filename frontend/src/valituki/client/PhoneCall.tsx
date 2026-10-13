import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../api';
import type { ViewScope } from '../api';
import { useValituki } from '../context';
import { LogoMark } from '../components/Logo';
import { MicIcon, MicOffIcon, PhoneIcon, SendIcon, SpeakerIcon, SpeakerOffIcon } from '../icons';
import type { ChatMessage, ClientView, GuidedView, Mutation, ValitukiView } from '../types';
import { useClientUI } from './ClientApp';

/* VOINTIPUHELU – when the client chose calls (contactChannel 'phone'), Mieliluotsi calls on the check-in days: it asks how
   they are and does a short thought exercise by speech. The call runs the same guided tools as the chat (check-in,
   "Ajatusten tutkiminen") through the same API, so the answers, the safety rules and the AI reflections are the same – only
   the medium is the voice. The browser speaks (speechSynthesis, a Finnish voice) and listens (SpeechRecognition, fi-FI)
   where it can; the answer buttons and the text field work everywhere. */

type Phase = 'ringing' | 'live' | 'ended';
type Line = { id: number; who: 'luotsi' | 'me'; text: string };
type Ask =
  | { kind: 'yesno' }
  | { kind: 'scale'; min: number; max: number; labels: string[] }
  | { kind: 'text'; skippable: boolean; placeholder: string }
  | { kind: 'choices'; options: { value: string; label: string }[]; skippable: boolean };
type Answer = { yes: boolean } | { value: number | string } | { skip: true } | { hangup: true };

// Kept short by speech: the steps a call skips (they are skippable in the chat too).
const CALL_SKIPS: Record<string, string[]> = {
  checkin: ['changes', 'note'],
  thought_record: ['emotions', 'behaviour', 'traps', 'evidenceFor'],
};
const MOOD_LABELS = ['Tosi huonosti', 'Huonosti', 'Kohtalaisesti', 'Hyvin', 'Tosi hyvin'];
const ANXIETY_LABELS = ['Ei lainkaan', 'Vähän', 'Jonkin verran', 'Paljon', 'Todella paljon'];
const NUMBER_WORDS: Record<string, number> = {
  nolla: 0, yksi: 1, yks: 1, ykkönen: 1, kaksi: 2, kaks: 2, kakkonen: 2, kolme: 3, kolmonen: 3, neljä: 4, nelonen: 4, viisi: 5,
  viis: 5, vitonen: 5, kuusi: 6, kuus: 6, seitsemän: 7, seittemän: 7, kahdeksan: 8, kaheksan: 8, yhdeksän: 9, yheksän: 9,
  kymmenen: 10, kymppi: 10,
};

function parseNumber(text: string, min: number, max: number): number | null {
  const digits = text.match(/\d+/);
  const candidates = digits ? [Number(digits[0])]
    : text.toLowerCase().split(/[^a-zåäö]+/).map((w) => NUMBER_WORDS[w]).filter((n) => n !== undefined);
  return candidates.find((n) => n >= min && n <= max) ?? null;
}

function parseYesNo(text: string): boolean | null {
  const t = text.toLowerCase().trim();
  if (/^(ei|en|nyt ei|myöhemmin)\b/.test(t) || /\b(ei nyt|myöhemmin|en halua)\b/.test(t)) return false;
  if (/\b(kyllä|joo|juu|jep|okei|ok|sopii|voidaan|tehdään|mennään|hyvä|selvä|toki)\b/.test(t)) return true;
  return null;
}

function hhmm(time: string | null): string {
  return (time ?? '18:30').replace(':', '.');
}

/* The browser's speech recognition, where it has one (Chrome, Edge, Safari). */
interface RecognitionEvent { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }
interface Recognition {
  lang: string; interimResults: boolean; continuous: boolean; maxAlternatives: number;
  start(): void; abort(): void;
  onresult: ((event: RecognitionEvent) => void) | null; onend: (() => void) | null; onerror: (() => void) | null;
}
type RecognitionCtor = new () => Recognition;
const speechWindow = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
const RecognitionImpl: RecognitionCtor | undefined = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;

export default function PhoneCall({ onClose }: { onClose: () => void }) {
  const { view, run } = useValituki();
  const { client } = useClientUI();
  const [phase, setPhase] = useState<Phase>('ringing');
  const [lines, setLines] = useState<Line[]>([]);
  const [asking, setAsking] = useState<Ask | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [heard, setHeard] = useState('');
  const [hint, setHint] = useState('');
  const [typed, setTyped] = useState('');
  const [speakerOn, setSpeakerOn] = useState(true);
  const [micOn, setMicOn] = useState(Boolean(RecognitionImpl));
  const [hasVoice, setHasVoice] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [outcome, setOutcome] = useState('');

  const latest = useRef<ValitukiView>(view);
  latest.current = view;
  const ended = useRef(false);
  const resolver = useRef<((answer: Answer) => void) | null>(null);
  const askingRef = useRef<Ask | null>(null);
  const seen = useRef(new Set<string>());
  const voice = useRef<SpeechSynthesisVoice | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const speakerRef = useRef(speakerOn);
  speakerRef.current = speakerOn;
  const micRef = useRef(micOn);
  micRef.current = micOn;
  const lineId = useRef(0);
  // An answer given while Mieliluotsi still speaks cuts the speech short.
  const interrupted = useRef(false);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const id = client.id;

  // A Finnish voice, when the browser has one – without it the call is shown as text only.
  useEffect(() => {
    if (!('speechSynthesis' in window)) return undefined;
    const pick = () => {
      const voices = window.speechSynthesis.getVoices();
      voice.current = voices.find((v) => v.lang === 'fi-FI') ?? voices.find((v) => v.lang.toLowerCase().startsWith('fi')) ?? null;
      setHasVoice(Boolean(voice.current));
    };
    pick();
    window.speechSynthesis.addEventListener('voiceschanged', pick);
    return () => window.speechSynthesis.removeEventListener('voiceschanged', pick);
  }, []);

  // The call's clock, and everything stops when the screen closes.
  useEffect(() => {
    if (phase !== 'live') return undefined;
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [phase]);
  // (React's development mode mounts twice: the first cleanup must not end the call for good.)
  useEffect(() => {
    ended.current = false;
    return () => hangUpQuietly();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'smooth' }); }, [lines, asking, heard]);

  function addLine(who: Line['who'], text: string) {
    lineId.current += 1;
    const next = { id: lineId.current, who, text };
    setLines((all) => [...all, next]);
  }

  function pause(ms: number) {
    return new Promise<void>((resolve) => window.setTimeout(resolve, ms));
  }

  function speak(text: string): Promise<void> {
    if (!speakerRef.current || !voice.current || !('speechSynthesis' in window)) return pause(Math.min(1400, 300 + text.length * 12));
    return new Promise((resolve) => {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.voice = voice.current;
      utterance.lang = voice.current?.lang ?? 'fi-FI';
      utterance.rate = 1.02;
      const done = () => resolve();
      utterance.onend = done;
      utterance.onerror = done;
      window.speechSynthesis.speak(utterance);
      window.setTimeout(done, 25000);
    });
  }

  /* The lines go to the transcript at once – the question is on the screen before the answer – and are then spoken in
     turn, unless an answer cuts the speech short. */
  async function say(text: string | string[]) {
    interrupted.current = false;
    const all = (Array.isArray(text) ? text : [text]).map((l) => l.trim()).filter(Boolean);
    if (ended.current) return;
    all.forEach((line) => addLine('luotsi', line));
    for (const line of all) {
      if (ended.current || interrupted.current) break;
      setSpeaking(true);
      await speak(line);
      setSpeaking(false);
    }
  }

  function stopListening() {
    recognition.current?.abort();
    recognition.current = null;
    setListening(false);
  }

  function listen() {
    if (!RecognitionImpl || !micRef.current || ended.current || !askingRef.current) return;
    stopListening();
    const rec = new RecognitionImpl();
    rec.lang = 'fi-FI';
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    rec.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) {
          setHeard('');
          onSpeech(result[0].transcript.trim());
          return;
        }
        interim += result[0].transcript;
      }
      setHeard(interim);
    };
    rec.onend = () => { if (recognition.current === rec) { recognition.current = null; setListening(false); } };
    rec.onerror = () => { if (recognition.current === rec) { recognition.current = null; setListening(false); } };
    recognition.current = rec;
    setListening(true);
    try {
      rec.start();
    } catch {
      setListening(false);
    }
  }

  function ask(spec: Ask, listenNow = true): Promise<Answer> {
    askingRef.current = spec;
    setAsking(spec);
    setHint('');
    if (listenNow) listen();
    return new Promise((resolve) => { resolver.current = resolve; });
  }

  /* Say the lines and ask: the answers are on the screen at once, the microphone opens when the speech ends. */
  async function question(text: string | string[], spec: Ask): Promise<Answer> {
    const answer = ask(spec, false);
    await say(text);
    if (askingRef.current === spec) listen();
    return answer;
  }

  function give(answer: Answer, display: string | null) {
    if (!resolver.current) return;
    interrupted.current = true;
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    setSpeaking(false);
    stopListening();
    askingRef.current = null;
    setAsking(null);
    setTyped('');
    if (display) addLine('me', display);
    const resolve = resolver.current;
    resolver.current = null;
    resolve(answer);
  }

  // What the client said, for the question on the screen.
  function onSpeech(text: string) {
    const spec = askingRef.current;
    if (!spec || !text) return;
    if (spec.kind === 'yesno') {
      const yes = parseYesNo(text);
      if (yes !== null) return give({ yes }, text);
    } else if (spec.kind === 'scale') {
      const n = parseNumber(text, spec.min, spec.max);
      if (n !== null) return give({ value: n }, text);
    } else if (spec.kind === 'choices') {
      const option = spec.options.find((o) => text.toLowerCase().includes(o.label.toLowerCase().split(/[ ,–]/)[0]));
      if (option) return give({ value: option.value }, option.label);
    } else {
      return give({ value: text }, text);
    }
    setHint(`Kuulin: ”${text}”. Sano uudelleen tai valitse alta.`);
    window.setTimeout(listen, 400);
  }

  async function mutate(call: (s: ViewScope) => Promise<Mutation<unknown>>): Promise<ValitukiView | null> {
    let fresh: ValitukiView | null = null;
    await run(async (s) => {
      const response = await call(s);
      fresh = response.view;
      return response;
    });
    return fresh;
  }

  // Mieliluotsi's new messages in the chat since the call started – what it says now.
  function unseen(c: ClientView): ChatMessage[] {
    const fresh = c.chat.filter((m) => !seen.current.has(m.id));
    fresh.forEach((m) => seen.current.add(m.id));
    return fresh;
  }

  function spoken(messages: ChatMessage[], skipQuestionOf: string | null): string[] {
    return messages.filter((m) => m.role === 'assistant' && ['text', 'question', 'notice'].includes(m.kind) && m.text
      && !(m.kind === 'question' && m.stepKey === skipQuestionOf)).map((m) => m.text);
  }

  function askFor(g: GuidedView): Ask | null {
    const widget = g.widget;
    if (!widget) return null;
    if (widget.type === 'scale5') return { kind: 'scale', min: 1, max: 5, labels: widget.options.map((o) => o.label) };
    if (widget.type === 'scale') return { kind: 'scale', min: widget.min, max: widget.max, labels: [] };
    if (widget.type === 'text') return { kind: 'text', skippable: widget.skippable, placeholder: widget.placeholder };
    if (widget.type === 'choices' || widget.type === 'multi' || widget.type === 'traps') {
      return { kind: 'choices', options: widget.options.map((o) => ({ value: o.value, label: o.label })), skippable: widget.skippable };
    }
    return null;
  }

  /* One guided tool by speech: say what Mieliluotsi says, ask the step, answer it through the same API as the chat. */
  async function guided(tool: string): Promise<'done' | 'stop'> {
    let current = await mutate((s) => api.startPractice(s, id, tool, {}, 'call'));
    if (!current) return 'done';
    while (current && !ended.current) {
      const c: ClientView | null = current.client;
      if (!c) return 'stop';
      const fresh = unseen(c);
      if (c.safety.lockActive || fresh.some((m) => m.safetyLevel >= 3)) {
        await say(spoken(fresh, null));
        finish('Puhelu keskeytettiin turvallisuussyistä. Hätätilanteessa soita 112.');
        return 'stop';
      }
      const g = c.guided;
      if (g && g.tool !== tool) {
        // The exercise led on to another (e.g. a behavioural experiment): it is continued in the app, not on this call.
        await say([...spoken(fresh, g.stepKey).filter((line) => line !== g.questionText),
          `Voit jatkaa harjoitusta ”${g.title}” sovelluksen Keskustelussa, kun sinulle sopii.`]);
        return 'done';
      }
      if (!g || !g.stepKey) {
        await say(spoken(fresh, null));
        return 'done';
      }
      const skip = Boolean(CALL_SKIPS[tool]?.includes(g.stepKey) && g.widget?.skippable);
      const toSay = spoken(fresh, skip ? g.stepKey : null);
      if (!skip && !fresh.some((m) => m.kind === 'question' && m.stepKey === g.stepKey) && g.questionText) toSay.push(g.questionText);
      let answer: Answer = { skip: true };
      if (skip) {
        await say(toSay);
      } else {
        const spec = askFor(g);
        if (!spec) return 'done';
        answer = await question(toSay, spec);
      }
      if (ended.current || 'hangup' in answer) return 'stop';
      const body = 'skip' in answer ? { sessionId: g.id, stepKey: g.stepKey, skip: true }
        : { sessionId: g.id, stepKey: g.stepKey, value: 'value' in answer ? answer.value : null };
      const next = await mutate((s) => api.answerPractice(s, id, body));
      if (next) current = next;
      else await say('Anteeksi, en saanut vastauksesta kiinni. Sanotko uudelleen?');
    }
    return 'stop';
  }

  async function script() {
    const ready = await question(`Hei ${client.firstName}, täällä Mieliluotsi. Onko nyt hyvä hetki jutella pari minuuttia?`,
      { kind: 'yesno' });
    if (ended.current || 'hangup' in ready) return;
    if ('yes' in ready && !ready.yes) {
      await say('Selvä, ei haittaa. Voit pyytää puhelua sovelluksesta, kun sinulle sopii. Hei hei!');
      return finish('Puhelu siirrettiin myöhemmäksi.');
    }
    let did = 'vointisi';
    if (latest.current.client?.checkIn.needsBaseline) {
      const mood = await question('Aloitetaan voinnista. Miten voit tänään asteikolla yhdestä viiteen? Yksi on tosi huonosti ja viisi '
        + 'tosi hyvin.', { kind: 'scale', min: 1, max: 5, labels: MOOD_LABELS });
      if (ended.current || !('value' in mood)) return;
      const anxiety = await question('Entä kuinka paljon ahdistusta tai jännitystä tunnet tänään, yhdestä viiteen?',
        { kind: 'scale', min: 1, max: 5, labels: ANXIETY_LABELS });
      if (ended.current || !('value' in anxiety)) return;
      const saved = await mutate((s) => api.recordBaseline(s, id, { mood: Number(mood.value), anxiety: Number(anxiety.value) }));
      if (!saved) return finish('Vointia ei saatu tallennettua.');
      unseen(saved.client as ClientView);
      await say('Kiitos. Tästä tulee oma lähtötasosi – jatkossa vointiasi verrataan siihen, ei muihin ihmisiin.');
    } else if (await guided('checkin') === 'stop') {
      return;
    }
    const exercise = await question('Tehdäänkö vielä lyhyt ajatusharjoitus? Se vie pari minuuttia.', { kind: 'yesno' });
    if (ended.current || 'hangup' in exercise) return;
    if ('yes' in exercise && exercise.yes) {
      if (await guided('thought_record') === 'stop') return;
      did = 'vointisi ja ajatusharjoituksen';
    }
    const after = latest.current.client?.checkIn;
    const next = after?.nextLabel ? `${after.nextLabel} kello ${hhmm(after.callTime)}` : 'sovittuna päivänä';
    await say(`Kiitos ${client.firstName}. Tallensin ${did} sovellukseen. Soitan seuraavan kerran ${next}. Hei hei!`);
    finish(`Tallennettu: ${did}.`);
  }

  function finish(text: string) {
    if (ended.current) return;
    ended.current = true;
    stopListening();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    setOutcome(text);
    setAsking(null);
    setPhase('ended');
  }

  function hangUpQuietly() {
    ended.current = true;
    stopListening();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    const resolve = resolver.current;
    resolver.current = null;
    resolve?.({ hangup: true });
  }

  function hangUp() {
    const resolve = resolver.current;
    resolver.current = null;
    finish('Puhelu lopetettiin. Keskeneräisen kohdan voit jatkaa Keskustelussa.');
    resolve?.({ hangup: true });
  }

  function answerCall() {
    // Everything already in the chat is history: the call speaks only what is new.
    client.chat.forEach((m) => seen.current.add(m.id));
    setPhase('live');
    void script();
  }

  function submitTyped(event: FormEvent) {
    event.preventDefault();
    const value = typed.trim();
    if (value) onSpeech(value);
  }

  function toggleMic() {
    const next = !micOn;
    setMicOn(next);
    micRef.current = next;
    if (next) listen();
    else stopListening();
  }

  function toggleSpeaker() {
    const next = !speakerOn;
    setSpeakerOn(next);
    speakerRef.current = next;
    if (!next && 'speechSynthesis' in window) window.speechSynthesis.cancel();
  }

  const clock = `${Math.floor(seconds / 60)}.${String(seconds % 60).padStart(2, '0')}`;
  const status = phase === 'ringing' ? 'soittaa…' : speaking ? 'Mieliluotsi puhuu' : listening ? 'Kuuntelen…' : asking ? 'Vastaa puhumalla tai valitse' : clock;

  return (
    <section className={`call call-${phase}`} role="dialog" aria-modal="true" aria-label="Vointipuhelu Mieliluotsilta">
      <header className="call-head">
        <span className={`call-avatar ${speaking ? 'is-speaking' : ''}`} aria-hidden="true"><LogoMark size={phase === 'ringing' ? 64 : 34} /></span>
        <div className="call-who">
          <p className="call-name">Mieliluotsi</p>
          <p className="call-status" aria-live="polite">{phase === 'ringing' ? 'Vointipuhelu · soittaa…' : phase === 'ended' ? `Puhelu päättyi · ${clock}` : status}</p>
        </div>
        {phase === 'live' && <span className="call-clock">{clock}</span>}
      </header>

      {phase === 'ringing' && (
        <div className="call-incoming">
          <p className="call-lead">Mieliluotsi soittaa sovitusti: kysyy vointiasi ja tekee kanssasi lyhyen ajatusharjoituksen.</p>
          <div className="call-answer-row">
            <button type="button" className="call-round call-decline" onClick={() => { hangUpQuietly(); onClose(); }} aria-label="Myöhemmin">
              <PhoneIcon size={26} />
            </button>
            <button type="button" className="call-round call-accept" onClick={answerCall} aria-label="Vastaa">
              <PhoneIcon size={26} />
            </button>
          </div>
          <div className="call-answer-labels"><span>Myöhemmin</span><span>Vastaa</span></div>
        </div>
      )}

      {phase !== 'ringing' && (
        <>
          <div className="call-transcript" ref={transcriptRef}>
            {lines.map((line) => <p key={line.id} className={`call-line is-${line.who}`}>{line.text}</p>)}
            {heard && <p className="call-line is-me is-interim">{heard}…</p>}
          </div>

          {phase === 'live' && asking && (
            <div className="call-answers">
              {hint && <p className="call-hint">{hint}</p>}
              {asking.kind === 'yesno' && (
                <div className="call-chips">
                  <button type="button" onClick={() => give({ yes: true }, 'Kyllä')}>Kyllä</button>
                  <button type="button" onClick={() => give({ yes: false }, 'Ei nyt')}>Ei nyt</button>
                </div>
              )}
              {asking.kind === 'scale' && (
                <div className={`call-scale ${asking.max - asking.min > 4 ? 'is-wide' : ''}`}>
                  {Array.from({ length: asking.max - asking.min + 1 }, (_, i) => asking.min + i).map((n) => (
                    <button key={n} type="button" title={asking.labels[n - asking.min]}
                      onClick={() => give({ value: n }, asking.labels[n - asking.min] ? `${n} – ${asking.labels[n - asking.min]}` : String(n))}>{n}</button>
                  ))}
                </div>
              )}
              {asking.kind === 'choices' && (
                <div className="call-chips">
                  {asking.options.map((o) => <button key={o.value} type="button" onClick={() => give({ value: o.value }, o.label)}>{o.label}</button>)}
                  {asking.skippable && <button type="button" onClick={() => give({ skip: true }, 'Ohitetaan')}>Ohita</button>}
                </div>
              )}
              {asking.kind === 'text' && (
                <form className="call-type" onSubmit={submitTyped}>
                  <input value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Kirjoita vastaus"
                    placeholder={RecognitionImpl && micOn ? 'Puhu tai kirjoita vastaus…' : 'Kirjoita vastaus…'} />
                  <button type="submit" aria-label="Lähetä" disabled={!typed.trim()}><SendIcon size={16} /></button>
                  {asking.skippable && <button type="button" className="call-skip" onClick={() => give({ skip: true }, 'Ohitetaan')}>Ohita</button>}
                </form>
              )}
            </div>
          )}

          {phase === 'live' && (
            <div className="call-controls">
              <button type="button" className={`call-ctrl ${micOn ? 'is-on' : ''}`} onClick={toggleMic} disabled={!RecognitionImpl}
                aria-pressed={micOn} title={RecognitionImpl ? 'Mikrofoni' : 'Puheentunnistus ei ole käytettävissä tässä selaimessa'}>
                {micOn ? <MicIcon size={20} /> : <MicOffIcon size={20} />}<span>{micOn ? 'Mikki' : 'Mykistetty'}</span>
              </button>
              <button type="button" className="call-round call-decline call-end" onClick={hangUp} aria-label="Lopeta puhelu">
                <PhoneIcon size={24} />
              </button>
              <button type="button" className={`call-ctrl ${speakerOn ? 'is-on' : ''}`} onClick={toggleSpeaker} disabled={!hasVoice}
                aria-pressed={speakerOn} title={hasVoice ? 'Kaiutin' : 'Suomenkielistä puheääntä ei löytynyt tästä selaimesta'}>
                {speakerOn && hasVoice ? <SpeakerIcon size={20} /> : <SpeakerOffIcon size={20} />}<span>Kaiutin</span>
              </button>
            </div>
          )}

          {phase === 'ended' && (
            <div className="call-ended">
              <p>{outcome}</p>
              <button type="button" className="cx-btn cx-btn-dark" onClick={onClose}>Sulje</button>
            </div>
          )}
          <p className="call-fine">Ei hätäpuhelu – hätätilanteessa soita 112.</p>
        </>
      )}
    </section>
  );
}
