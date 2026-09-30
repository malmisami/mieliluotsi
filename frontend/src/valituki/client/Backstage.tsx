import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode, RefObject } from 'react';
import { fmtNum } from '../format';
import { AlertIcon, CheckIcon, ChevronDownIcon, EyeIcon, LayersIcon, LeafIcon, ListIcon, PuzzleIcon, PulseIcon, SlidersIcon, TargetIcon } from '../icons';
import { AISwitch } from '../components/DemoDock';
import { AgentTimeline } from '../components/Timeline';
import type { BackstageMatch, BackstageModality, ClientView, InsightRow } from '../types';
import { DataFlow } from './DataFlow';
import type { Flow } from './DataFlow';

interface ProfileRow { key: string; icon: ReactNode; label: string; hint: string; value: string | null; pro: boolean; match: boolean }

function sharing(items: InsightRow[]) {
  return { pro: items.some((i) => i.sharing.professional), match: items.some((i) => i.sharing.matching) };
}

/** What the future therapist's profile holds right now – one row per kind of information, with who may use it. */
function profileRows(client: ClientView): ProfileRow[] {
  const profile = client.fitProfile;
  const groups = Object.fromEntries(client.memory.groups.map((g) => [g.key, g.items]));
  const checkins = client.progress.series.filter((p) => p.mood !== null);
  const moods = checkins.slice(-7).map((p) => p.mood ?? 0);
  const name = client.firstName;
  return [
    { key: 'goals', icon: <TargetIcon size={14} />, label: 'Tavoitteet', hint: `Mitä ${name} toivoo terapian muuttavan`, value: profile?.goals.primary[0]?.text ?? null, ...sharing(groups.goal ?? []) },
    { key: 'wellbeing', icon: <PulseIcon size={14} />, label: 'Vointi odotusaikana', hint: 'Mieliala ja ahdistus check-ineistä odotuksen aikana',
      value: checkins.length ? `${checkins.length} check-iniä · mieliala ka. ${fmtNum(moods.reduce((a, b) => a + b, 0) / moods.length)}/5` : null,
      pro: client.memory.consent.storeHistory, match: false },
    { key: 'helpful', icon: <LeafIcon size={14} />, label: 'Mikä auttaa', hint: `Keinot, jotka ${name} on todennut toimiviksi`,
      value: (groups.helpful ?? []).map((i) => i.text).join(' ') || null, ...sharing(groups.helpful ?? []) },
    { key: 'challenge', icon: <AlertIcon size={14} />, label: 'Vaikeat hetket', hint: 'Tilanteet, joissa olo on vaikeimmillaan',
      value: (groups.challenge ?? []).map((i) => i.text).join(' ') || null, ...sharing(groups.challenge ?? []) },
  ];
}

function matchSignature(match: BackstageMatch): string {
  return `${match.ran}|${match.candidates.map((c) => `${c.name}:${c.total}:${c.status}`).join(',')}`;
}

function modalitySignature(modality: BackstageModality): string {
  return modality.rows.map((r) => `${r.id}:${r.total}`).join(',');
}

const MODALITY_CHANGES: [string, string][] = [
  ['experience', 'Harjoittelu odotusaikana'], ['workingStyle', 'Työskentelytapatoiveet'], ['goals', 'Tavoitteet'],
];

/** What moved the therapy approach table: the practice during the wait first, then the working style, then the goals. */
function modalityChange(before: BackstageModality, after: BackstageModality): string {
  const old = new Map(before.rows.flatMap((r) => r.components.map((c) => [`${r.id}.${c.key}`, c.score] as const)));
  const moved = MODALITY_CHANGES.find(([key]) => after.rows.some((r) => r.components.some((c) => c.key === key
    && old.get(`${r.id}.${key}`) !== c.score)));
  return moved ? moved[1] : 'Terapiamuodon sopivuus';
}

/** Next to the phone on wide screens: the therapist profile and matching, both always visible. When the client's data
    changes, it visibly travels from the phone to the rows it updates. */
export default function Backstage({ client }: { client: ClientView }) {
  const asideRef = useRef<HTMLElement>(null);
  const rows = profileRows(client);
  const match = client.backstage.match;
  const values = Object.fromEntries(rows.map((r) => [r.key, r.value ?? '']));
  const rowSig = rows.map((r) => `${r.key}=${r.value ?? ''}`).join('|');
  const matchSig = matchSignature(match);
  const modality = client.backstage.modality;
  const modSig = modalitySignature(modality);

  const [seen, setSeen] = useState({ clientId: client.id, rowSig, matchSig, modSig, modality, values, ran: match.ran, seq: 0 });
  const [flows, setFlows] = useState<Flow[]>([]);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  if (seen.clientId !== client.id || seen.rowSig !== rowSig || seen.matchSig !== matchSig || seen.modSig !== modSig) {
    const seq = seen.seq + 1;
    if (seen.clientId === client.id) {
      // Only approved, stored information moves: each changed row flies to the profile, and to matching when allowed there.
      const changed = rows.filter((r) => r.value && r.value !== seen.values[r.key]);
      const next: Omit<Flow, 'id'>[] = [];
      for (const r of changed) {
        next.push({ label: r.label, target: 'profile', row: r.key });
        if (r.match) next.push({ label: r.label, target: 'match' });
      }
      if (seen.matchSig !== matchSig && !next.some((f) => f.target === 'match')) {
        next.push({ label: match.ran && !seen.ran ? 'Terapeutin vapaa aika' : 'Pisteytys päivittyi', target: 'match' });
      }
      if (seen.modSig !== modSig) next.push({ label: modalityChange(seen.modality, modality), target: 'modality' });
      setFlows(next.slice(0, 7).map((f, i) => ({ ...f, id: `${seq}-${i}` })));
      setFresh(new Set([...changed.map((r) => r.key), ...(seen.matchSig !== matchSig ? ['match'] : []),
        ...(seen.modSig !== modSig ? ['modality'] : [])]));
    } else {
      setFlows([]);
      setFresh(new Set());
    }
    setSeen({ clientId: client.id, rowSig, matchSig, modSig, modality, values, ran: match.ran, seq });
  }
  useEffect(() => {
    if (!fresh.size) return undefined;
    const timer = window.setTimeout(() => setFresh(new Set()), 3600);
    return () => window.clearTimeout(timer);
  }, [fresh]);

  // Beside the phone the panel fits the screen like the phone does: it is zoomed down until the AI switch, the two
  // matching tables, the profile and the log's heading fit under the demo dock (an opened log scrolls inside).
  useLayoutEffect(() => {
    const aside = asideRef.current;
    if (!aside) return undefined;
    const fit = () => {
      if (window.innerWidth <= 1100) {
        aside.style.removeProperty('--bs-zoom');
        return;
      }
      const zoom = Number.parseFloat(aside.style.getPropertyValue('--bs-zoom')) || 1;
      const parts = [aside.querySelector('.bs-ai'), ...aside.querySelectorAll('.bm-card'), aside.querySelector('.bp-doc'),
        aside.querySelector('.bs-log summary')];
      const natural = parts.reduce((sum, el) => sum + (el ? el.getBoundingClientRect().height / zoom : 0), 0)
        + (parts.length - 1) * 12 + 8;
      const stageTop = Number.parseFloat(getComputedStyle(aside).getPropertyValue('--stage-top')) || 110;
      const room = Math.max(360, window.innerHeight - stageTop - 28);
      const next = Math.max(0.55, Math.min(1, room / natural));
      if (Math.abs(next - zoom) > 0.01) aside.style.setProperty('--bs-zoom', next.toFixed(3));
    };
    fit();
    const observer = new ResizeObserver(fit);
    aside.querySelectorAll('.bm-card, .bp-doc').forEach((el) => observer.observe(el));
    window.addEventListener('resize', fit);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', fit);
    };
  }, []);

  return (
    <aside className="backstage" ref={asideRef} aria-label="Mieliluotsi taustalla">
      <div className="stage-ai bs-ai"><AISwitch /></div>
      <MatchCard match={match} fresh={fresh.has('match')} />
      <ModalityCard modality={modality} fresh={fresh.has('modality')} />
      <ProfileCard client={client} rows={rows} fresh={fresh} />
      <details className="bs-log">
        <summary><ListIcon size={14} /> Agenttien loki – mitä Mieliluotsi teki</summary>
        <Log client={client} />
      </details>
      <DataFlow flows={flows} asideRef={asideRef} />
    </aside>
  );
}

/* ---------- Profile for the future therapist ---------- */

function ProfileCard({ client, rows, fresh }: { client: ClientView; rows: ProfileRow[]; fresh: Set<string> }) {
  const filled = rows.filter((r) => r.value).length;
  const handover = client.matching.handover;
  return (
    <section className={`bp-doc ${[...fresh].some((k) => k !== 'match' && k !== 'modality') ? 'is-fresh' : ''}`} aria-label="Profiili terapeutille">
      <div className="bp-head">
        <p className="bs-title"><LayersIcon size={15} /> Profiili terapeutille</p>
        <span className="bp-meter" title={`${filled}/${rows.length} osiota`} aria-label={`${filled}/${rows.length} osiota`}>
          {rows.map((r) => <i key={r.key} className={r.value ? 'on' : ''} />)}
        </span>
      </div>
      <ul className="bp-rows">
        {rows.map((r) => (
          <li key={r.key} data-row={r.key} className={`${r.value ? 'is-filled' : ''} ${fresh.has(r.key) ? 'is-fresh' : ''}`}>
            <span className="bp-icon" aria-hidden="true">{r.icon}</span>
            <span className="bp-text">
              <span className="bp-label">{r.label}</span>
              <span className="bp-value" title={r.value ?? undefined}>{r.value ?? r.hint}</span>
            </span>
            <span className="bp-flags">
              <span className={r.value && r.pro ? 'on' : ''} title={r.value && r.pro ? 'Näkyy terapeutille' : 'Ei näy terapeutille'}><EyeIcon size={13} /></span>
              <span className={r.value && r.match ? 'on' : ''} title={r.value && r.match ? 'Käytetään matchingissa' : 'Ei käytetä matchingissa'}><PuzzleIcon size={13} /></span>
            </span>
          </li>
        ))}
      </ul>
      <p className="bp-legend">
        <span><EyeIcon size={12} /> näkyy terapeutille</span><span><PuzzleIcon size={12} /> käytetään matchingissa</span>
        {handover?.status === 'approved' && (
          <span className="bp-shared"><CheckIcon size={12} /> yhteenveto jaettu: {handover.therapistName}</span>
        )}
      </p>
    </section>
  );
}

/* ---------- Matching: the approved data against the therapist pool ---------- */

// The columns a person reads at a glance: what fits the client. Language, place and time are hard criteria (they
// exclude) or practicalities, so they stay in the total but get no column of their own.
const COLUMNS: { key: string; label: string }[] = [
  { key: 'goalCompetence', label: 'Osaaminen' }, { key: 'workingStyle', label: 'Työtapa' }, { key: 'userPreferences', label: 'Toiveet' },
];

function Dots({ score, label, hint }: { score: number; label: string; hint?: string }) {
  const filled = Math.round(score * 4);
  return (
    <span className="bm-dots" title={hint ?? `${label}: ${Math.round(score * 100)} %`} aria-label={`${label} ${filled}/4`}>
      {[0, 1, 2, 3].map((i) => <i key={i} className={i < filled ? 'on' : ''} />)}
    </span>
  );
}

/** Rows glide to their new place when the ranking changes (FLIP; no re-render needed). */
function useRowFlip(gridRef: RefObject<HTMLDivElement | null>, order: string) {
  const tops = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    const grid = gridRef.current;
    if (!grid) return;
    grid.querySelectorAll<HTMLElement>('[data-name]').forEach((el) => {
      const name = el.dataset.name ?? '';
      const before = tops.current.get(name);
      if (before !== undefined && before !== el.offsetTop) {
        el.animate([{ transform: `translateY(${before - el.offsetTop}px)` }, { transform: 'none' }],
          { duration: 700, easing: 'cubic-bezier(0.2, 0.7, 0.2, 1)' });
      }
      tops.current.set(name, el.offsetTop);
    });
  }, [gridRef, order]);
}

function MatchCard({ match, fresh }: { match: BackstageMatch; fresh: boolean }) {
  const gridRef = useRef<HTMLDivElement>(null);
  useRowFlip(gridRef, match.candidates.map((c) => c.name).join('|'));

  return (
    <section className={`bm-card ${fresh ? 'is-fresh' : ''}`} aria-label="Terapeuttimatching">
      <div className="bp-head">
        <p className="bs-title"><PuzzleIcon size={15} /> Terapeuttimatching</p>
        <span className={`bm-state ${match.ran ? 'is-run' : ''}`}>{match.ran ? 'matching ajettu' : 'esikatselu'}</span>
      </div>
      <div className="bm-grid" ref={gridRef} role="table" aria-label="Pisteytys osa-alueittain">
        <div className="bm-row bm-row-head" role="row">
          <span role="columnheader">Terapeutti</span>
          {COLUMNS.map((c) => <span key={c.key} role="columnheader">{c.label}</span>)}
          <span role="columnheader">Sopivuus</span>
        </div>
        {match.candidates.map((cand) => (
          <div key={cand.name} data-name={cand.name} role="row" className={`bm-row ${cand.status === 'selected' ? 'is-chosen' : ''}`}>
            <span role="cell" className="bm-name">{cand.name}{cand.status === 'selected' && <em>valittu</em>}</span>
            {COLUMNS.map((col) => {
              const c = cand.components.find((x) => x.key === col.key);
              return <span key={col.key} role="cell" className="bm-cell">{c ? <Dots score={c.score} label={c.label} /> : '–'}</span>;
            })}
            <span role="cell" className="bm-total">
              <span className="bm-bar"><i style={{ width: `${Math.min(100, cand.total)}%` }} /></span>{Math.round(cand.total)}
            </span>
          </div>
        ))}
      </div>
      {match.excluded.length > 0 && (
        <details className="bm-out">
          <summary><ChevronDownIcon size={12} /> Rajattu pois kovilla ehdoilla: {match.excluded.length} terapeuttia</summary>
          <ul>
            {match.excluded.map((e) => <li key={e.name}><b>{e.name}</b> {e.reason}</li>)}
          </ul>
        </details>
      )}
      <p className="bm-scale"><Dots score={1} label="Vahva osuma" /> vahva osuma · sopivuus 0–100 säännöillä, ei tekoälyllä</p>
    </section>
  );
}

/* ---------- Therapy approach: which way of working fits the client ---------- */

const MODALITY_COLUMNS = ['Tavoitteet', 'Työtapa', 'Kokemus'];

/** The same kind of table as the therapist matching, for the therapy approaches: how each suits the client's goals,
    the way of working they wish for and what they have tried during the wait. A suggestion – the professional decides. */
function ModalityCard({ modality, fresh }: { modality: BackstageModality; fresh: boolean }) {
  const gridRef = useRef<HTMLDivElement>(null);
  useRowFlip(gridRef, modality.rows.map((r) => r.id).join('|'));
  const columns = modality.rows[0]?.components.map((c) => c.label) ?? MODALITY_COLUMNS;
  return (
    <section className={`bm-card bm-modality ${fresh ? 'is-fresh' : ''}`} aria-label="Terapiamuoto ja työtapa">
      <div className="bp-head">
        <p className="bs-title"><SlidersIcon size={15} /> Terapiamuoto ja työtapa</p>
        {modality.rows[0] && <span className="bm-state is-run" title={modality.rows[0].title}>sopivin: {modality.rows[0].label}</span>}
      </div>
      <div className="bm-grid" ref={gridRef} role="table" aria-label="Terapiamuotojen sopivuus osa-alueittain">
        <div className="bm-row bm-row-head" role="row">
          <span role="columnheader">Terapiamuoto</span>
          {columns.map((label) => <span key={label} role="columnheader">{label}</span>)}
          <span role="columnheader">Sopivuus</span>
        </div>
        {modality.rows.map((row, i) => (
          <div key={row.id} data-name={row.id} role="row" className={`bm-row ${i === 0 ? 'is-top' : ''}`}
            title={`${row.title} – ${row.therapists ? `tarjolla ${row.therapists} terapeutilla` : 'ei tarjolla nyt'}`}>
            <span role="cell" className="bm-name">{row.label}</span>
            {row.components.map((c) => (
              <span key={c.key} role="cell" className="bm-cell">
                {c.known ? <Dots score={c.score} label={c.label} hint={`${c.label}: ${c.detail}`} />
                  : <span className="bm-unknown" title={c.detail} aria-label={`${c.label}: ${c.detail}`}>–</span>}
              </span>
            ))}
            <span role="cell" className="bm-total">
              <span className="bm-bar"><i style={{ width: `${Math.min(100, row.total)}%` }} /></span>{Math.round(row.total)}
            </span>
          </div>
        ))}
      </div>
      <p className="bm-scale">kokemus = odotusajan harjoittelu · – ei vielä tietoa · ehdotus, ammattilainen päättää</p>
    </section>
  );
}

/* ---------- Log: every agent action ---------- */

function Log({ client }: { client: ClientView }) {
  return (
    <div className="bs-feed">
      <AgentTimeline limit={14} items={client.timeline.map((e) => ({ id: e.id, at: e.at, agent: e.agent, title: e.title,
        detail: e.detail, ruleId: e.ruleId, aiSource: e.aiSource, kind: e.kind }))} />
    </div>
  );
}
