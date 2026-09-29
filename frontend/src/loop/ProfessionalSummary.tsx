import { useEffect, useRef, useState } from 'react';
import { CheckIcon, ExternalIcon, PrintIcon } from '../icons';
import { loopApi } from './api';
import { flagText, formatDate, formatValue } from './labels';
import type { LoopDashboard, ProfessionalSummaryData } from './types';

interface Props {
  observationId: string;
  onBack: () => void;
  onShared: (dashboard: LoopDashboard) => void;
}

export default function ProfessionalSummary({ observationId, onBack, onShared }: Props) {
  const [summary, setSummary] = useState<ProfessionalSummaryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    loopApi.summary(observationId).then(setSummary).catch((e: Error) => setError(e.message));
  }, [observationId]);

  useEffect(() => {
    if (summary) headingRef.current?.focus();
  }, [summary]);

  async function share() {
    setSharing(true);
    try {
      const result = await loopApi.share(observationId);
      onShared(result.dashboard);
      setSummary(await loopApi.summary(observationId));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSharing(false);
    }
  }

  if (error) {
    return (
      <section className="panel">
        <p className="form-error" role="alert">{error}</p>
        <button type="button" onClick={onBack}>Palaa takaisin</button>
      </section>
    );
  }
  if (!summary) return <section className="panel"><p role="status">Muodostetaan yhteenvetoa…</p></section>;

  const event = summary.event;
  return (
    <section className="panel professional-summary" aria-labelledby="summary-title">
      <div className="print-area">
        <p className="synthetic-banner strong" role="note">SYNTEETTINEN DEMOAINEISTO – ei oikean henkilön tietoja</p>
        <h2 id="summary-title" tabIndex={-1} ref={headingRef}>Yhteenveto terveydenhuollon ammattilaiselle</h2>
        <p className="muted">Agenttinen hyvinvointikumppani · muodostettu {formatDate(summary.generatedAt)} · huomio {summary.observationId}</p>
        <p className="disclaimer-box" role="note"><strong>{summary.disclaimer}</strong></p>

        <h3>Henkilö</h3>
        <dl className="fact-list">
          <div><dt>Nimi</dt><dd>{summary.syntheticPersonName} (keksitty)</dd></div>
        </dl>

        <h3>Johdanto</h3>
        <p>{summary.intro}</p>
        <p className="muted small">Teksti: {summary.introSource === 'llm' ? 'tekoälyn luonnos annetuista tiedoista' : 'valmis tekstipohja'}</p>

        <h3>Geneettinen löydös</h3>
        <dl className="fact-list two-col">
          <div><dt>Löydös</dt><dd>{summary.finding.title}</dd></div>
          <div><dt>Geeni / variantti</dt><dd>{summary.finding.gene} · {summary.finding.variant}</dd></div>
          <div><dt>Luokitus</dt><dd>{summary.finding.classification}</dd></div>
          <div><dt>Vahvistustila</dt><dd>{summary.confirmationLabel}</dd></div>
          <div><dt>Evidenssin taso</dt><dd>{summary.evidenceLevelLabel}</dd></div>
          <div><dt>Lähde</dt><dd>{summary.source}</dd></div>
        </dl>

        <h3>Relevantti terveystapahtuma</h3>
        {event && (
          <dl className="fact-list two-col">
            <div><dt>Tapahtuma</dt><dd>{event.displayName} {formatValue(event)}</dd></div>
            <div><dt>Poikkeamamerkintä</dt><dd>{flagText(event.abnormalFlag) ?? '–'}</dd></div>
            <div><dt>Tapahtuman lähde</dt><dd>{event.source}</dd></div>
            <div><dt>Alkuperäinen teksti</dt><dd>{event.rawText ?? '–'}</dd></div>
          </dl>
        )}

        {summary.relevantEvents.length > 1 && (
          <>
            <h3>Kaikki huomioon liittyvät terveystapahtumat</h3>
            <ul>
              {summary.relevantEvents.map((e) => (
                <li key={e.id}>{e.displayName} {formatValue(e)} ({formatDate(e.date)}){e.confirmedByUser ? ' · käyttäjän vahvistama' : ''}</li>
              ))}
            </ul>
          </>
        )}

        <h3>Käyttäjän vahvistama sukuhistoria</h3>
        {summary.userConfirmedFamilyHistory.length ? (
          <ul>
            {summary.userConfirmedFamilyHistory.map((e) => (
              <li key={e.id}>{formatValue(e)} · kirjattu {formatDate(e.date)} · lähde: käyttäjän kertoma ja vahvistama</li>
            ))}
          </ul>
        ) : (
          <p>Ei käyttäjän vahvistamaa sukuhistoriaa.</p>
        )}

        <h3>Päivämäärät</h3>
        <dl className="fact-list two-col">
          <div><dt>Löydöksen evidenssi tarkistettu</dt><dd>{formatDate(summary.dates.findingLastReviewedAt)}</dd></div>
          <div><dt>Seuranta hyväksytty</dt><dd>{formatDate(summary.dates.monitoringConsentedAt)}</dd></div>
          <div><dt>Terveystapahtuma</dt><dd>{formatDate(summary.dates.eventDate)}</dd></div>
          <div><dt>Huomio muodostettu</dt><dd>{formatDate(summary.dates.observationCreatedAt)}</dd></div>
        </dl>

        <h3>Miksi huomio muodostettiin</h3>
        <p>{summary.reason}</p>
        <p><strong>Sääntömoottorin säännöt:</strong></p>
        <ul>
          {summary.rules.map((rule) => (
            <li key={rule.id}><code>{rule.id}</code> – {rule.name}{rule.demoNotice ? ` (${rule.demoNotice})` : ''}</li>
          ))}
        </ul>

        <h3>Puuttuvat tiedot</h3>
        <ul>{summary.missingInformation.map((item) => <li key={item}>{item}</li>)}</ul>

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
        {summary.sharedAt ? (
          <p className="success-text" role="status"><CheckIcon size={18} /> Merkitty jaetuksi {formatDate(summary.sharedAt)}. Tietoja ei lähetetty mihinkään.</p>
        ) : (
          <button type="button" onClick={share} disabled={sharing}>
            {sharing ? 'Tallennetaan…' : 'Hyväksy ja merkitse jaetuksi'}
          </button>
        )}
        <button type="button" className="btn-secondary" onClick={() => window.print()}><PrintIcon size={18} /> Tulosta</button>
        <a className="button-link secondary" href={loopApi.summaryHtmlUrl(summary.observationId)} target="_blank" rel="noreferrer">
          Avaa tulostettava HTML (uusi välilehti) <ExternalIcon size={16} />
        </a>
        <button type="button" className="btn-secondary" onClick={onBack}>Palaa takaisin</button>
      </div>
      <p className="muted small no-print">Demossa ei ole sähköposti- tai potilastietojärjestelmäintegraatiota. ”Merkitse jaetuksi” tallentaa vain tilan tähän demoon.</p>
    </section>
  );
}
