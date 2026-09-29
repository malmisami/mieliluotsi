import { useEffect, useRef, useState } from 'react';
import { ExternalIcon, PrintIcon } from '../icons';
import { loopApi } from './api';
import { flagText, formatDate, formatValue, StatusBadge } from './labels';
import type { FullSummaryData, HealthEvent, TrackedMetric } from './types';

interface Props {
  onBack?: () => void;
}

/** The results of one lab order (e.g. "Lipidit", 7 results) are one line, as on the Terveystiedot view. */
function groupByOrder(events: HealthEvent[]) {
  const lines: { key: string; event: HealthEvent; title?: string; count: number; size: number }[] = [];
  const orders = new Map<string, (typeof lines)[number]>();
  for (const e of events) {
    const orderId = typeof e.structuredData?.panelId === 'string' ? e.structuredData.panelId : null;
    const order = orderId ? orders.get(orderId) : undefined;
    if (order) {
      order.count += 1;
      continue;
    }
    const size = typeof e.structuredData?.panelSize === 'number' ? e.structuredData.panelSize : 1;
    const title = typeof e.structuredData?.panelName === 'string' ? e.structuredData.panelName : undefined;
    const line = { key: orderId ?? e.id, event: e, title, count: 1, size };
    if (orderId) orders.set(orderId, line);
    lines.push(line);
  }
  return lines.map(({ key, event, title, count, size }) => {
    const date = formatDate(event.date);
    if (!title || size <= 1) return { key, text: `${event.displayName} ${formatValue(event)} (${date})` };
    const elsewhere = size - count;
    return { key, text: `${title}: ${count} tulosta${elsewhere > 0 ? `, lisäksi ${elsewhere} löydöksen kohdalla` : ''} (${date})` };
  });
}

function MetricTrend({ metric }: { metric: TrackedMetric }) {
  const trend = metric.points.map((p) => `${p.value ?? '–'} ${metric.unit} (${formatDate(p.date)})${flagText(p.abnormalFlag) ? ` · ${flagText(p.abnormalFlag)}` : ''}`);
  return <li><strong>{metric.label}</strong>: {trend.join(' → ')}</li>;
}

export default function FullSummary({ onBack }: Props) {
  const [summary, setSummary] = useState<FullSummaryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    loopApi.fullSummary().then(setSummary).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (summary) headingRef.current?.focus();
  }, [summary]);

  if (error) {
    return (
      <section className="panel">
        <p className="form-error" role="alert">{error}</p>
        {onBack && <button type="button" onClick={onBack}>Palaa takaisin</button>}
      </section>
    );
  }
  if (!summary) return <section className="panel"><p role="status">Muodostetaan yhteenvetoa…</p></section>;

  return (
    <section className="panel professional-summary" aria-labelledby="summary-title">
      <div className="print-area">
        <p className="synthetic-banner strong" role="note">SYNTEETTINEN DEMOAINEISTO – ei oikean henkilön tietoja</p>
        <h2 id="summary-title" tabIndex={-1} ref={headingRef}>Yhteenveto terveydenhuollon ammattilaiselle</h2>
        <p className="muted">Agenttinen hyvinvointikumppani · muodostettu {formatDate(summary.generatedAt)} · kaikki seurannassa olevat löydökset</p>
        <p className="disclaimer-box" role="note"><strong>{summary.disclaimer}</strong></p>

        <h3>Henkilö</h3>
        <dl className="fact-list">
          <div><dt>Nimi</dt><dd>{summary.syntheticPersonName} (keksitty)</dd></div>
        </dl>

        <h3>Johdanto</h3>
        <p>{summary.intro}</p>
        <p className="muted small">Teksti: {summary.introSource === 'llm' ? 'tekoälyn luonnos annetuista tiedoista' : 'valmis tekstipohja'}</p>

        {summary.findings.map(({ finding, confirmationLabel, evidenceLevelLabel, monitoringStatus, relatedEvents, trackedMetrics, hasDefinedMetric, missingInformation }) => (
          <div key={finding.id}>
            <h3>{finding.title}</h3>
            <dl className="fact-list two-col">
              <div><dt>Geeni / variantti</dt><dd>{finding.gene} · {finding.variant}</dd></div>
              <div><dt>Luokitus</dt><dd>{finding.classification}</dd></div>
              <div><dt>Vahvistustila</dt><dd>{confirmationLabel}</dd></div>
              <div><dt>Evidenssin taso</dt><dd>{evidenceLevelLabel}</dd></div>
              <div><dt>Seurannan tila</dt><dd><StatusBadge status={monitoringStatus} /></dd></div>
            </dl>
            <p><strong>Seurattava mittari ja sen kehitys:</strong></p>
            {trackedMetrics.length ? (
              <ul>{trackedMetrics.map((m) => <MetricTrend key={m.code} metric={m} />)}</ul>
            ) : hasDefinedMetric ? (
              <p className="muted small">Ei vielä numeerisia mittaustuloksia aikajanalla.</p>
            ) : (
              <p className="muted small">Ei tässä demossa määriteltyä seurattavaa mittaria (raakaehdokaslöydös ilman virallista seurantasääntöä).</p>
            )}
            <p><strong>Liittyvät terveystapahtumat aikajanalla:</strong></p>
            {relatedEvents.length ? (
              <ul>
                {relatedEvents.map((e) => (
                  <li key={e.id}>{e.displayName} {formatValue(e)} ({formatDate(e.date)}){e.confirmedByUser ? ' · käyttäjän vahvistama' : ''}</li>
                ))}
              </ul>
            ) : <p className="muted small">Ei liittyviä tapahtumia aikajanalla.</p>}
            <p><strong>Puuttuvat tiedot:</strong></p>
            {missingInformation.length ? (
              <ul>{missingInformation.map((item) => <li key={item}>{item}</li>)}</ul>
            ) : <p className="muted small">Ei puuttuvia tietoja.</p>}
          </div>
        ))}

        <h3>Muut terveystapahtumat (eivät liity suoraan mihinkään löydökseen)</h3>
        {summary.unrelatedEvents.length ? (
          <ul>
            {groupByOrder(summary.unrelatedEvents).map((line) => <li key={line.key}>{line.text}</li>)}
          </ul>
        ) : <p>Ei muita tapahtumia.</p>}

        <h3>Ehdotettuja lisäselvityksiä</h3>
        {summary.suggestedNextSteps.length ? (
          <ul>{summary.suggestedNextSteps.map((item) => <li key={item}>{item}</li>)}</ul>
        ) : <p>Ei ehdotettuja lisäselvityksiä.</p>}

        {summary.questionsForProfessional.length > 0 && (
          <>
            <h3>Käyttäjän kysymyksiä vastaanotolle</h3>
            <ul>{summary.questionsForProfessional.map((q) => <li key={q}>{q}</li>)}</ul>
          </>
        )}

        <h3>Vastuullisuusrajaus</h3>
        <ul>{summary.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </div>

      <div className="row no-print summary-actions">
        <button type="button" className="btn-secondary" onClick={() => window.print()}><PrintIcon size={18} /> Tulosta</button>
        <a className="button-link secondary" href={loopApi.fullSummaryHtmlUrl()} target="_blank" rel="noreferrer">
          Avaa tulostettava HTML (uusi välilehti) <ExternalIcon size={16} />
        </a>
        {onBack && <button type="button" className="btn-secondary" onClick={onBack}>Palaa takaisin</button>}
      </div>
      <p className="muted small no-print">Demossa ei ole sähköposti- tai potilastietojärjestelmäintegraatiota.</p>
    </section>
  );
}
