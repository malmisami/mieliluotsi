import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtShort } from '../format';
import { CopyIcon, EyeIcon, LockIcon, QuoteIcon, TrashIcon } from '../icons';
import { MoodAnxietyChart } from '../components/charts';
import type { ThoughtRecordRow } from '../types';
import { ChangeBars } from './ChatWidgets';
import { useClientUI } from './ClientApp';
import { LadderCard } from './ToolsTab';

/* "Edistyminen": mood and anxiety over time (Limbic's "Your progress"), a weekly review built only from the client's own
   answers (Wysa's "Your week in review") and the private thought journal. */

export default function ProgressTab() {
  const { client } = useClientUI();
  const practice = client.practice;
  const stats = practice.stats;
  return (
    <div className="cx-screen cx-progress">
      <h1 className="cx-title">Edistyminen</h1>
      <MoodAnxietyChart points={client.progress.series} title="Mielialasi ja ahdistus" />
      <WordsCard />

      <div className="cx-stats" aria-label="Harjoittelu yhteensä">
        <span><strong>{stats.thoughtRecords}</strong> ajatusten tutkimista</span>
        <span><strong>{stats.exposureAttempts}</strong> altistusaskelta</span>
        <span><strong>{stats.experimentsDone}</strong> käyttäytymiskoetta</span>
      </div>
      {stats.avgDrop !== null && (
        <p className="cx-fine">Ajatusten tutkimisen jälkeen tunne on laskenut keskimäärin <strong>{String(stats.avgDrop).replace('.', ',')}</strong> pistettä
          asteikolla 0–10.{stats.traps.length > 0 && ` Useimmin tunnistamasi ajatusloukku: ${stats.traps[0].label}.`}</p>
      )}

      <WeekCard />

      {practice.thoughtRecords.length > 0 && (
        <section className="cx-section">
          <h2 className="cx-h2">Ajatuspäiväkirja</h2>
          <p className="cx-fine"><LockIcon size={12} /> Merkinnät näkyvät vain sinulle. Voit jakaa yksittäisen merkinnän terapeutillesi.</p>
          {practice.thoughtRecords.map((record) => <RecordCard key={record.id} record={record} />)}
        </section>
      )}

      {practice.experiments.length > 0 && (
        <section className="cx-section">
          <h2 className="cx-h2">Käyttäytymiskokeet</h2>
          {practice.experiments.map((e) => (
            <article key={e.id} className="cx-card">
              <div className="cx-done-top"><span className="cx-tag">{e.status === 'done' ? 'Tehty' : 'Suunniteltu'}</span>
                <span className="cx-fine">{e.plannedFor ? fmtShort(e.plannedFor) : ''}</span></div>
              <p className="cx-card-label">Ennuste</p><p>{e.prediction}</p>
              <p className="cx-card-label">Koe</p><p>{e.plan}</p>
              {e.status === 'done' && (
                <>
                  <p className="cx-card-label">Mitä tapahtui</p><p>{e.outcome}</p>
                  {e.learned && <><p className="cx-card-label">Mitä opin</p><p>{e.learned}</p></>}
                  {e.beliefBefore !== null && e.beliefAfter !== null && (
                    <ChangeBars change={{ label: 'Usko ennusteeseen', before: e.beliefBefore, after: e.beliefAfter, max: 10 }} />
                  )}
                </>
              )}
            </article>
          ))}
        </section>
      )}

      {practice.ladders.length > 0 && (
        <section className="cx-section">
          <h2 className="cx-h2">Altistusportaat</h2>
          {practice.ladders.map((ladder) => <LadderCard key={ladder.id} ladder={ladder} />)}
        </section>
      )}
    </div>
  );
}

/** The week's own words, lifted from the client's answers – shown right under the chart. */
function WordsCard() {
  const { client } = useClientUI();
  const words = client.progress.week.words;
  const [copied, setCopied] = useState(false);
  if (!words) return null;
  return (
    <div className="cx-words">
      <p className="cx-words-kicker"><QuoteIcon size={14} /> Sanat muistiin – omin sanoin</p>
      <p className="cx-words-text">{words}</p>
      <button type="button" className="cx-icon-btn cx-words-copy" aria-label="Kopioi"
        onClick={() => { void navigator.clipboard?.writeText(words).then(() => setCopied(true)).catch(() => undefined); }}>
        <CopyIcon size={17} />
      </button>
      {copied && <span className="cx-fine" role="status">Kopioitu</span>}
    </div>
  );
}

function WeekCard() {
  const { view } = useValituki();
  const { client } = useClientUI();
  const week = client.progress.week;
  const moodWords = view.meta.labels.moodScale;
  return (
    <section className="cx-week" aria-label="Viikkosi">
      <p className="cx-week-range">Tämä viikko · {fmtShort(week.start)}–{fmtShort(week.end)}</p>
      <p className="cx-week-big"><strong>{week.sessions}</strong> {week.sessions === 1 ? 'harjoitus' : 'harjoitusta'} tällä viikolla</p>
      <div className="cx-week-days" role="list" aria-label="Mieliala päivittäin">
        {week.days.map((d) => (
          <span key={d.date} role="listitem" className={`cx-week-day ${d.future ? 'is-future' : ''}`}
            aria-label={`${d.weekday}: ${d.mood ? `mieliala ${d.mood}/5 (${moodWords[String(d.mood)]})` : 'ei check-iniä'}`}>
            <span className="cx-week-wd">{d.weekday}</span>
            <span className={`cx-week-dot ${d.mood ? `mood-${d.mood}` : ''}`}>{d.mood ?? ''}</span>
          </span>
        ))}
      </div>
      <p className="cx-fine cx-week-legend">Numero = mieliala 1–5 (1 tosi huonosti … 5 tosi hyvin)</p>
      {week.cameUp.length > 0 && (
        <>
          <h3 className="cx-h3">Mitä tällä viikolla nousi esiin</h3>
          <ul className="cx-bullets">{week.cameUp.map((t) => <li key={t}>{t}</li>)}</ul>
        </>
      )}
      {week.steps.length > 0 && (
        <>
          <h3 className="cx-h3">Pienet askeleet eteenpäin</h3>
          <ul className="cx-bullets">{week.steps.map((t) => <li key={t}>{t}</li>)}</ul>
        </>
      )}
      <p className="cx-fine">Koottu vain omista vastauksistasi – ei diagnoosi.</p>
    </section>
  );
}

function RecordCard({ record }: { record: ThoughtRecordRow }) {
  const { run, busy } = useValituki();
  const { client } = useClientUI();
  const [open, setOpen] = useState(false);
  const therapist = client.mode.therapistFirstName;
  return (
    <article className="cx-record">
      <button type="button" className="cx-record-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="cx-fine">{fmtShort(record.date)}{record.shared ? ' · jaettu terapeutille' : ''}</span>
        <span className="cx-record-situation">{record.situation}</span>
        <span className="cx-record-thoughts">
          <span className="cx-record-old">”{record.thought}”</span>
          {record.alternative && <span className="cx-record-new">→ ”{record.alternative}”</span>}
        </span>
      </button>
      {open && (
        <div className="cx-record-body">
          {record.emotions.length > 0 && <p><span className="cx-card-label">Tunne</span> {record.emotions.join(', ')}</p>}
          {record.behaviour && <p><span className="cx-card-label">Toiminta</span> {record.behaviour}</p>}
          {record.traps.length > 0 && <p className="cx-chips-inline">{record.traps.map((t) => <span key={t.id} className="cx-tag">{t.label}</span>)}</p>}
          {record.evidenceFor && <p><span className="cx-card-label">Mikä tukee ajatusta</span> {record.evidenceFor}</p>}
          {record.evidenceAgainst && <p><span className="cx-card-label">Ystävälle sanoisin</span> {record.evidenceAgainst}</p>}
          {record.intensityBefore !== null && record.intensityAfter !== null && (
            <ChangeBars change={{ label: 'Tunteen voimakkuus', before: record.intensityBefore, after: record.intensityAfter, max: 10 }} />
          )}
          <div className="cx-row">
            <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy} aria-pressed={record.shared}
              onClick={() => run((s) => api.setPracticeSharing(s, client.id, 'thought_record', record.id, !record.shared),
                () => (record.shared ? 'Merkintä näkyy taas vain sinulle.' : `Merkintä jaettiin${therapist ? ` terapeutti ${therapist}lle` : ' terapeutillesi, kun terapia alkaa'}.`))}>
              {record.shared ? <><LockIcon size={14} /> Lopeta jakaminen</> : <><EyeIcon size={14} /> Jaa terapeutille</>}
            </button>
            <button type="button" className="cx-btn cx-btn-ghost cx-btn-sm" disabled={busy}
              onClick={() => run((s) => api.removePracticeItem(s, client.id, 'thought_record', record.id), () => 'Merkintä poistettiin.')}>
              <TrashIcon size={14} /> Poista
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
