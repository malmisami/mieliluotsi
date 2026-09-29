import { useMemo, useState } from 'react';
import { AlertIcon, CalendarIcon, CheckIcon, ClipboardIcon, DnaIcon, LockIcon, MinusIcon } from '../icons';
import { supportApi } from '../support/api';
import { loopApi } from './api';
import type { GeneticLinkTheme, GeneticLinkingView } from '../support/types';
import { useRunner } from '../support/useRunner';
import { formatDate, withoutSyntheticMarker as plain } from './labels';
import type { HealthEvent, LoopDashboard } from './types';

interface Props {
  dashboard: LoopDashboard;
  setDashboard: (dashboard: LoopDashboard) => void;
  onOpenQuiz: () => void;
  onOpenAnalysis: () => void;
  /** The user's own DNA analysis (Perimätieto tab), when it has been run in this session. */
  dnaSessionId: string | null;
}

type Category = 'text' | 'lab' | 'measurement' | 'diagnosis' | 'medication';

/** The same groups as in the national health record view, in the order a visit usually produces them. */
const CATEGORIES: { key: Category; label: string; plural: string }[] = [
  { key: 'text', label: 'Tekstimerkintä', plural: 'Tekstimerkinnät' },
  { key: 'lab', label: 'Laboratoriotutkimus', plural: 'Laboratoriotutkimukset' },
  { key: 'measurement', label: 'Mittaus', plural: 'Mittaukset' },
  { key: 'diagnosis', label: 'Diagnoosi', plural: 'Diagnoosit' },
  { key: 'medication', label: 'Lääkitys', plural: 'Lääkitys' },
];
const CATEGORY_ORDER: Record<Category, number> = { text: 0, lab: 1, measurement: 2, diagnosis: 3, medication: 4 };

/** One entry as the person sees it: a visit with its notes, or one laboratory order with all its results. */
interface HealthRecord {
  key: string;
  date: string;
  category: Category;
  title: string;
  detail?: string;
  organisation: string;
  events: HealthEvent[];
  results?: HealthEvent[];
  sections?: { heading: string; text: string }[];
}

const SOURCE_KIND_FOR_TYPE: Record<string, string> = {
  diagnosis: 'diagnoses',
  medication: 'medications',
  care_episode: 'careEpisodes',
  professional_note: 'professionalNotes',
  contact: 'interactionEvents',
  lab_result: 'measurements',
  vital_sign: 'measurements',
};

// Only records written by health care are listed. Own notes, home readings and demo events stay in the data that
// the agent uses, but they are not health care records.
const RECORD_TYPES = new Set(Object.keys(SOURCE_KIND_FOR_TYPE));
const CHANNEL_TITLES: Record<string, string> = { phone: 'Puhelinkontakti', digital: 'Sähköinen asiointi', visit: 'Käynti' };
const DIAGNOSIS_STATUS: Record<string, string> = { active: 'Voimassa', resolved: 'Päättynyt' };
const MEDICATION_STATUS: Record<string, string> = { active: 'Käytössä', stopped: 'Lopetettu' };

function text(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined;
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function isHomeReading(event: HealthEvent) {
  return event.code === 'BP' && (event.displayName.includes('(kotimittaus)') || event.structuredData?.context === 'home');
}

function noteHeading(role: string | undefined) {
  if (role === 'lääkäri') return 'Lääkärin merkintä';
  if (role === 'sairaanhoitaja' || role === 'terveydenhoitaja') return 'Hoitotyön merkintä';
  if (role === 'fysioterapeutti') return 'Fysioterapian merkintä';
  return 'Merkintä';
}

function resultValue(event: HealthEvent) {
  const reported = text(event.structuredData?.resultText);
  const value = reported ?? (event.value === null ? '' : typeof event.value === 'number' ? event.value.toLocaleString('fi-FI') : event.value);
  return `${value}${event.unit ? ` ${event.unit}` : ''}`;
}

function flagLabel(flag: HealthEvent['abnormalFlag']) {
  if (flag === 'high') return '▲ Korkea';
  if (flag === 'low') return '▼ Matala';
  return null;
}

function buildRecords(events: HealthEvent[]): HealthRecord[] {
  const kept = events.filter((e) => RECORD_TYPES.has(e.type) && !isHomeReading(e));
  const records: HealthRecord[] = [];
  const visits = new Map<string, HealthRecord>();
  const labOrders = new Map<string, HealthRecord>();

  // a visit is one text entry: the notes and the visit contact of the same day join it
  for (const e of kept.filter((x) => x.type === 'care_episode')) {
    const role = text(e.structuredData?.professionalRole);
    const record: HealthRecord = {
      key: e.id, date: e.date, category: 'text', title: e.displayName, detail: role ? capitalize(role) : undefined,
      organisation: e.source, events: [e], sections: e.rawText ? [{ heading: 'Käynnin syy', text: e.rawText }] : [],
    };
    visits.set(e.date, record);
    records.push(record);
  }

  for (const e of kept) {
    if (e.type === 'professional_note') {
      const section = { heading: noteHeading(text(e.structuredData?.authorRole)), text: e.rawText ?? '' };
      const visit = visits.get(e.date);
      if (visit) {
        visit.events.push(e);
        visit.sections?.push(section);
      } else {
        records.push({ key: e.id, date: e.date, category: 'text', title: e.displayName, organisation: e.source, events: [e], sections: [section] });
      }
    } else if (e.type === 'contact') {
      const channel = text(e.structuredData?.channel) ?? '';
      const visit = visits.get(e.date);
      if (channel === 'visit' && visit) {
        visit.events.push(e); // the visit is already an entry
        continue;
      }
      const topic = text(e.structuredData?.topic);
      records.push({
        key: e.id, date: e.date, category: 'text', title: CHANNEL_TITLES[channel] ?? 'Asiointi',
        detail: topic ? `Aihe: ${topic}` : undefined, organisation: e.source, events: [e],
        sections: e.rawText ? [{ heading: 'Asia', text: e.rawText }] : [],
      });
    } else if (e.type === 'lab_result') {
      const orderId = text(e.structuredData?.panelId);
      const order = orderId ? labOrders.get(orderId) : undefined;
      if (order) {
        order.events.push(e);
        order.results?.push(e);
        continue;
      }
      const record: HealthRecord = {
        key: orderId ?? e.id, date: e.date, category: 'lab', title: text(e.structuredData?.panelName) ?? e.displayName,
        organisation: e.source, events: [e], results: [e],
      };
      if (orderId) labOrders.set(orderId, record);
      records.push(record);
    } else if (e.type === 'diagnosis') {
      const status = text(e.structuredData?.status);
      records.push({
        key: e.id, date: e.date, category: 'diagnosis', title: e.displayName.replace(/^Diagnoosi:\s*/, ''),
        detail: [e.code, status ? DIAGNOSIS_STATUS[status] ?? status : null].filter(Boolean).join(' · '), organisation: e.source, events: [e],
      });
    } else if (e.type === 'medication') {
      const purpose = text(e.structuredData?.purpose);
      const status = text(e.structuredData?.status);
      records.push({
        key: e.id, date: e.date, category: 'medication', title: text(e.value) ?? e.displayName,
        detail: [purpose ? `Käyttötarkoitus: ${purpose}` : null, status ? MEDICATION_STATUS[status] ?? status : null].filter(Boolean).join(' · ') || undefined,
        organisation: e.source, events: [e],
      });
    } else if (e.type === 'vital_sign') {
      records.push({
        key: e.id, date: e.date, category: 'measurement', title: e.displayName.replace(/\s*\(vastaanotto\)$/, ''),
        detail: e.structuredData?.context === 'clinic' ? 'Vastaanotolla mitattu' : undefined, organisation: e.source, events: [e], results: [e],
      });
    }
  }

  for (const record of records) {
    record.title = plain(record.title);
    record.organisation = plain(record.organisation);
    record.detail = plain(record.detail);
    record.sections = record.sections?.map((section) => ({ ...section, text: plain(section.text) }));
    if (record.category === 'lab' && record.results?.length === 1) {
      // one result: name the analysis itself (e.g. "Verensokeri (paastoarvo)"), the order name goes to the details
      const result = record.results[0];
      const abbreviation = text(result.structuredData?.abbreviation);
      const order = text(result.structuredData?.panelName);
      record.title = plain(result.displayName);
      record.detail = [abbreviation, order && order !== result.displayName ? order : null].filter(Boolean).join(' · ') || undefined;
    }
    if (record.results && record.results.length > 1) {
      const abnormal = record.results.filter((r) => flagLabel(r.abnormalFlag)).length;
      record.detail = `${record.results.length} tulosta${abnormal ? ` · ${abnormal} poikkeavaa` : ''}`;
    }
  }
  // newest first, as in the national health record view
  return records
    .map((record, index) => ({ record, index }))
    .sort((a, b) => b.record.date.localeCompare(a.record.date) || CATEGORY_ORDER[a.record.category] - CATEGORY_ORDER[b.record.category] || a.index - b.index)
    .map(({ record }) => record);
}

function LabResults({ results }: { results: HealthEvent[] }) {
  return (
    <details className="record-results">
      <summary>Näytä tulokset ({results.length})</summary>
      <div className="record-results-wrap">
        <table className="record-results-table">
          <thead>
            <tr>
              <th scope="col">Tutkimus</th>
              <th scope="col">Tulos</th>
              <th scope="col" className="record-reference">Viitearvot</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => {
              const abbreviation = text(r.structuredData?.abbreviation);
              const reference = text(r.structuredData?.referenceRange);
              const flag = flagLabel(r.abnormalFlag);
              return (
                <tr key={r.id} className={flag ? 'is-abnormal' : ''}>
                  <td>
                    <strong>{abbreviation ?? plain(r.displayName)}</strong>
                    {abbreviation && <small>{plain(r.displayName)}</small>}
                  </td>
                  <td>
                    <span className="record-value">{resultValue(r)}</span>
                    {flag && <span className="record-flag">{flag}</span>}
                    {reference && <small className="record-reference-inline">Viitearvot {reference}</small>}
                  </td>
                  <td className="record-reference">{reference ?? '–'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/** Health care records in one list, grouped like the national health record view: text entries, laboratory
 * orders with their results, measurements, diagnoses and medication. */
export default function Timeline({ dashboard, setDashboard, onOpenQuiz, onOpenAnalysis, dnaSessionId }: Props) {
  const [categoryFilter, setCategoryFilter] = useState<Category | 'linked' | ''>('');
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const { busy, error, message, run } = useRunner(setDashboard);
  const observationEventIds = new Set(dashboard.observations.map((o) => o.eventId));
  const age = new Date(dashboard.currentDate).getFullYear() - dashboard.profile.birthYear;
  const consent = dashboard.support.available ? dashboard.support.consent : null;
  const records = useMemo(() => buildRecords(dashboard.events), [dashboard.events]);
  const counts = useMemo(() => {
    const result: Partial<Record<Category, number>> = {};
    for (const r of records) result[r.category] = (result[r.category] ?? 0) + 1;
    return result;
  }, [records]);
  const linking: GeneticLinkingView | null = dashboard.support.available ? dashboard.support.geneticLinking : null;
  const linkedThemes = linking && !linking.suspended ? linking.themes : [];
  const themesForRecord = (record: HealthRecord) => linkedThemes.filter((t) => record.events.some((e) => t.eventIds.includes(e.id)));
  const recordsForTheme = (theme: GeneticLinkTheme) => records.filter((r) => r.events.some((e) => theme.eventIds.includes(e.id)));
  const linkedCount = records.filter((r) => themesForRecord(r).length > 0).length;
  const shown = records.filter((r) =>
    !categoryFilter ? true : categoryFilter === 'linked' ? themesForRecord(r).length > 0 : r.category === categoryFilter);
  const geneticAllowed = dashboard.support.available ? dashboard.support.consent.dataSources.geneticInsights !== false : false;
  const geneticCount = dashboard.support.available ? dashboard.support.insights.filter((i) => i.kind === 'genetic').length : 0;
  const canLink = geneticAllowed && (geneticCount > 0 || Boolean(dnaSessionId));

  function link() {
    run(() => supportApi.linkGenetics(dnaSessionId), (r) => {
      const themes = r.result.themes;
      if (!themes.length) return 'DNA-analyysissä ei ole havaintoja.';
      const findings = themes.reduce((sum, t) => sum + t.findings.length, 0);
      const withRecords = themes.filter((t) => t.recordCount > 0);
      return `${findings} DNA-analyysin havaintoa käytiin läpi. Terveystietoja liittyy aiheisiin: ${withRecords.map((t) => `${t.label} (${t.recordCount})`).join(', ') || 'ei yhtään'}.`;
    });
  }

  function jumpTo(record: HealthRecord) {
    if (categoryFilter && categoryFilter !== 'linked' && record.category !== categoryFilter) setCategoryFilter('');
    setHighlighted(record.key);
    window.setTimeout(() => document.getElementById(`record-${record.key}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50);
    window.setTimeout(() => setHighlighted((current) => (current === record.key ? null : current)), 2500);
  }

  function inUse(event: HealthEvent) {
    const kind = (event.extractedData?.sourceKind as string | undefined) ?? SOURCE_KIND_FOR_TYPE[event.type];
    return !consent || !kind ? true : consent.dataSources[kind] !== false;
  }

  return (
    <div className="loop-layout loop-layout-single">
      <div className="loop-main">
        <section className="panel timeline-panel" aria-labelledby="timeline-title">
          <div className="panel-heading">
            <span className="panel-heading-icon" aria-hidden="true"><CalendarIcon size={48} /></span>
            <h2 id="timeline-title">Terveystiedot</h2>
          </div>
          <p className="muted">
            {dashboard.profile.name} · {age} vuotta · {dashboard.profile.heightCm} cm · {dashboard.profile.weightKg} kg
          </p>
          <p className="lead">
            Terveydenhuollon kirjaamat tiedot: käynnit, laboratoriotutkimukset, mittaukset, diagnoosit ja lääkitys. Luettu suoraan
            lähdejärjestelmistä – mitään ei kirjata uudelleen.
          </p>
          {dashboard.support.available && !linking && (
            <div className="dna-link-start">
              <button type="button" onClick={link} disabled={busy || !canLink}>
                <DnaIcon size={20} /> Linkitä DNA-analyysiin
              </button>
              <p className="muted small">
                {!geneticAllowed ? 'Perimätiedon käyttöä ei ole sallittu suostumuksissa, joten linkitys ei ole käytössä.'
                  : !canLink ? <>Perimätietoa ei ole. <button type="button" className="link-button" onClick={onOpenAnalysis}>Aja DNA-analyysi Perimätieto-välilehdellä</button>.</>
                  : 'Yhdistää terveystiedot ja DNA-analyysin havainnot aiheittain – esimerkiksi kaikki kohonneeseen kolesteroliin liittyvät merkinnät.'}
              </p>
            </div>
          )}
          {linking && (
            <section className="dna-links" aria-labelledby="dna-links-title">
              <div className="dna-links-head">
                <h3 id="dna-links-title"><DnaIcon size={22} /> Linkitys DNA-analyysiin</h3>
                <span className="muted small">Linkitetty {formatDate(linking.linkedAt)} · sääntöjen perusteella</span>
              </div>
              {linking.suspended ? (
                <p>Linkitys on piilotettu, koska perimätiedon käyttöä ei ole sallittu suostumuksissa.</p>
              ) : (
                <>
                  {linkedThemes.length === 0 && <p>Terveystiedoista ei löytynyt DNA-analyysin havaintoihin liittyviä merkintöjä.</p>}
                  {linkedThemes.map((theme) => {
                    const themeRecords = recordsForTheme(theme);
                    return (
                      <article key={theme.id} className="dna-link-card">
                        <h4>{theme.label}</h4>
                        <p className="muted small">{plain(theme.reason)}{theme.planName ? ` Liittyy seurantaan: ${theme.planName}.` : ''}</p>
                        {theme.findings.length > 0 && (
                          <div className="dna-link-findings">
                            <h5>DNA-analyysin havainnot ({theme.findings.length})</h5>
                            <ul className="dna-finding-list">
                              {theme.findings.map((finding) => (
                                <li key={finding.key}>
                                  <strong>{finding.label}</strong>
                                  <small className="muted"> · {finding.statusLabel}</small>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {theme.keyMeasurements?.length > 0 && (
                          <div className="dna-key-measurements">
                            <h5>DNA-havaintoon liittyvät mittaukset</h5>
                            <div className="findings-table-wrap">
                              <table className="findings-table dna-key-table">
                                <thead>
                                  <tr>
                                    <th scope="col">Mittaus</th>
                                    {theme.keyMeasurements[0].values.map((v) => <th scope="col" key={v.eventId}>{formatDate(v.date)}</th>)}
                                  </tr>
                                </thead>
                                <tbody>
                                  {theme.keyMeasurements.map((m) => (
                                    <tr key={m.code}>
                                      <th scope="row">
                                        {m.label}
                                        <small className="muted"> {m.unit}{m.referenceRange ? ` · viite ${m.referenceRange}` : ''}</small>
                                      </th>
                                      {theme.keyMeasurements[0].values.map((head) => {
                                        const v = m.values.find((x) => x.date === head.date);
                                        return (
                                          <td key={head.eventId} className={v?.flag ? 'is-flagged' : undefined}>
                                            {v ? v.value : '–'}{v?.flag === 'high' ? ' ↑' : v?.flag === 'low' ? ' ↓' : ''}
                                            {v?.flag && <span className="visually-hidden">{v.flag === 'high' ? ' (koholla)' : ' (matala)'}</span>}
                                          </td>
                                        );
                                      })}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}
                        <div className="dna-link-columns">
                          <div>
                            <h5>Terveystiedot ({themeRecords.length} merkintää)</h5>
                            {themeRecords.length === 0 && <p className="muted small">Terveystiedoissa ei ole tähän liittyviä merkintöjä.</p>}
                            <ul className="dna-link-list">
                              {themeRecords.map((record) => (
                                <li key={record.key}>
                                  <button type="button" className="link-button" onClick={() => jumpTo(record)}>
                                    {formatDate(record.date)} · {CATEGORIES.find((c) => c.key === record.category)?.label}: {record.title}
                                  </button>
                                  {record.detail && <small className="muted">{plain(record.detail)}</small>}
                                </li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      </article>
                    );
                  })}
                  {linking.healthOnlyThemes.length > 0 && (
                    <p className="muted small">Ei DNA-analyysin havaintoa: {linking.healthOnlyThemes.join(', ')}.</p>
                  )}
                </>
              )}
              <p className="dna-links-note">{linking.note}</p>
              <div className="row">
                <button type="button" className="btn-secondary" onClick={link} disabled={busy || !canLink}>Päivitä linkitys</button>
                <button type="button" className="link-button" disabled={busy}
                  onClick={() => run(() => supportApi.unlinkGenetics(), () => 'Linkitys purettiin. Seurantaan ei tullut muutoksia.')}>
                  Pura linkitys
                </button>
              </div>
            </section>
          )}
          <p className="live-message" aria-live="polite">{message}</p>
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="filter-row">
            <label>
              Näytä
              <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value as Category | 'linked' | '')}>
                <option value="">Kaikki merkinnät ({records.length})</option>
                {linkedCount > 0 && <option value="linked">Linkitetty DNA-analyysiin ({linkedCount})</option>}
                {CATEGORIES.filter((c) => counts[c.key]).map((c) => (
                  <option key={c.key} value={c.key}>{c.plural} ({counts[c.key]})</option>
                ))}
              </select>
            </label>
            <button type="button" className="btn-secondary" onClick={onOpenQuiz}><ClipboardIcon size={18} /> Laaja elämäntapakysely (valinnainen)</button>
          </div>
          {!dashboard.support.available ? (
            <div className="empty-state">
              <p>Terveystiedot on tyhjennetty (<em>Tyhjennä ja poista kaikki tiedot</em>). Palauta demo alkutilaan, niin terveystiedot palaavat.</p>
              <button type="button" disabled={busy} onClick={() => run(() => loopApi.reset(), () => 'Demo palautettu alkutilaan.')}>
                Palauta demo alkutilaan
              </button>
            </div>
          ) : shown.length === 0 ? (
            <p>Ei merkintöjä.</p>
          ) : (
            <ol className="timeline health-records">
              {shown.map((record) => {
                const ledToObservation = record.events.some((e) => observationEventIds.has(e.id));
                const single = record.results?.length === 1 ? record.results[0] : null;
                const singleFlag = single ? flagLabel(single.abnormalFlag) : null;
                const userReported = record.events.some((e) => e.source === 'user_reported');
                const recordThemes = themesForRecord(record);
                const classes = [ledToObservation ? 'led-to-observation' : '', recordThemes.length ? 'is-dna-linked' : '', highlighted === record.key ? 'is-highlighted' : '']
                  .filter(Boolean).join(' ');
                return (
                  <li key={record.key} id={`record-${record.key}`} className={classes}>
                    <div className="timeline-date">
                      <time dateTime={record.date}>{formatDate(record.date)}</time>
                    </div>
                    <div className="timeline-body">
                      <span className="record-category">{CATEGORIES.find((c) => c.key === record.category)?.label}</span>
                      <p className="timeline-title">
                        <strong>{record.title}</strong>
                        {single && <> · {resultValue(single)}</>}
                        {singleFlag && <span className="record-flag">{singleFlag}</span>}
                      </p>
                      <p className="timeline-meta">
                        {[record.detail, single && text(single.structuredData?.referenceRange) ? `Viitearvot ${text(single.structuredData?.referenceRange)}` : null, record.organisation]
                          .filter(Boolean)
                          .join(' · ')}
                        {userReported && <span className="chip"><CheckIcon size={14} /> Käyttäjän kertoma</span>}
                        {ledToObservation && <span className="chip chip-attention"><AlertIcon size={14} /> Johti huomioon</span>}
                        {!inUse(record.events[0]) && <span className="chip"><LockIcon size={14} /> Ei käytössä seurannassa (suostumus)</span>}
                        {recordThemes.map((theme) => (
                          <span key={theme.id} className="chip chip-dna"><DnaIcon size={14} /> Linkitetty: {theme.label}</span>
                        ))}
                      </p>
                      {record.sections && record.sections.length > 0 && (
                        <dl className="record-sections">
                          {record.sections.map((section, index) => (
                            <div key={`${section.heading}-${index}`}>
                              <dt>{section.heading}</dt>
                              <dd>{section.text}</dd>
                            </div>
                          ))}
                        </dl>
                      )}
                      {record.results && record.results.length > 1 && <LabResults results={record.results} />}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}
