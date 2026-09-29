import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
// Legacy OmaGenomi styles travel with the lazily loaded legacy app (see main.tsx).
import './styles/loop.css';
import './styles/support.css';
import './styles/wellbeing.css';
import { API_BASE, loopApi } from './loop/api';
import CompanionView from './loop/companion/CompanionView';
import FullSummary from './loop/FullSummary';
import LifestyleQuiz from './loop/LifestyleQuiz';
import Timeline from './loop/Timeline';
import { withoutSyntheticMarker as plain } from './loop/labels';
import type { LoopDashboard } from './loop/types';
import { supportApi } from './support/api';
import AuditView from './support/AuditView';
import ConsentView from './support/ConsentView';
import GeneticSourcePanel from './support/GeneticSourcePanel';
import ImpactView from './support/ImpactView';
import { CategoryBadge } from './support/labels';
import ProfessionalView from './support/professional/ProfessionalView';
import SituationView from './support/SituationView';
import type { RelevanceCategory } from './support/types';
import WellbeingDataView from './wellbeing/WellbeingDataView';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CalendarIcon,
  ChatIcon,
  CheckIcon,
  ChevronRightIcon,
  ClipboardIcon,
  ClockIcon,
  DnaIcon,
  DocumentIcon,
  ExternalIcon,
  HeartHandIcon,
  LockIcon,
  PersonIcon,
  PulseIcon,
  ShieldIcon,
  StethoscopeIcon,
  TestTubeIcon,
  TrashIcon,
  UploadIcon,
  WarningIcon,
} from './icons';

type MainView = 'situation' | 'companion' | 'timeline' | 'wellbeing' | 'analysis' | 'consent' | 'audit' | 'professional' | 'impact' | 'summary' | 'quiz';
type Role = 'client' | 'professional';

const RELEVANCE_GROUPS: { category: RelevanceCategory; title: string; intro: string; open: boolean }[] = [
  {
    category: 'needs_professional_check',
    title: 'Ammattilaisen arvioon ehdotettavat havainnot',
    intro: 'Voivat olla merkityksellisiä. Ammattilainen arvioi ne ennen kuin ne vaikuttavat mihinkään.',
    open: true,
  },
  {
    category: 'no_practical_significance',
    title: 'Havainnot, joilla ei ole käytännön merkitystä seurannallesi',
    intro: 'Esimerkiksi tilastollisia yhteyksiä. Ei käytetä seurannassa.',
    open: false,
  },
  {
    category: 'uncertain_or_conflicting',
    title: 'Tulkinnaltaan epävarmat havainnot',
    intro: 'Merkitystä ei tiedetä riittävän varmasti. Ei käytetä, eikä tarkoita sairautta tai riskiä.',
    open: false,
  },
];

// Analysis and report are one step: the summary table, the gate-1 panel and the grouped report follow each other.
const STEPS = ['DNA-aineisto', 'Analyysi ja raportti'];

/** "Löydösten yhteenveto" as a table: one row per database match (gene / variant, what it relates to, certainty). */
function FindingsOverview({ report }: { report: any }) {
  const findings: any[] = report?.findings ?? [];
  if (!findings.length) {
    return (
      <div className="clinvar-overview">
        <h3>Löydösten yhteenveto</h3>
        <p>{report?.clinvar_overview_fi || 'ClinVar-haussa ei löytynyt raportoitavia variantteja.'}</p>
      </div>
    );
  }
  const significant = findings.filter((f) => f.category === 'clinically_significant').length;
  const uncertain = findings.filter((f) => f.category === 'uncertain_or_conflicting').length;
  return (
    <div className="clinvar-overview">
      <h3>Löydösten yhteenveto</h3>
      <p>
        Analyysissä löytyi {findings.length} {findings.length === 1 ? 'tietokantamerkintä' : 'tietokantamerkintää'}:{' '}
        {significant} {significant === 1 ? 'kliinisesti merkittävä' : 'kliinisesti merkittävää'} ja{' '}
        {uncertain} {uncertain === 1 ? 'epävarma tai ristiriitainen' : 'epävarmaa tai ristiriitaista'}.
      </p>
      <div className="findings-table-wrap findings-overview-table">
        <table className="findings-table">
          <thead>
            <tr>
              <th scope="col">Geeni</th>
              <th scope="col">Havainto</th>
              <th scope="col">Varmuus</th>
            </tr>
          </thead>
          <tbody>
            {findings.map((f) => {
              const conditions: string[] = f.disease_observation?.related_conditions ?? f.conditions ?? [];
              const area: string | undefined = f.disease_observation?.health_area;
              return (
                <tr key={f.id ?? `${f.rsid}-${f.pos}`}>
                  <td>
                    <strong>{f.gene || 'Tuntematon geeni'}</strong>
                    {f.rsid && <><br /><small>{f.rsid}</small></>}
                    {f.chrom && <><br /><small className="variant-position">(chr{f.chrom}:{f.pos} {f.ref}&gt;{f.alt})</small></>}
                  </td>
                  <td>
                    {conditions.length ? conditions.join(', ') : 'Ei nimettyä sairautta tai ominaisuutta'}
                    {area && <><br /><small>Liittyy {area}</small></>}
                  </td>
                  <td>{f.clinical_significance_fi || 'Ei ilmoitettu'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function findingExplanation(finding: any) {
  const categoryText: Record<string, string> = {
    clinically_significant: 'Tietokannassa tämä variantti on arvioitu kliinisesti merkittäväksi.',
    uncertain_or_conflicting: 'Tietokannan tulkinta on epävarma tai eri lähteissä on ristiriitaa.',
    pharmacogenetics: 'Variantti voi liittyä siihen, miten elimistö käsittelee tiettyjä lääkkeitä.',
    risk_or_association: 'Variantti on yhdistetty tutkimuksissa johonkin riskiin tai ominaisuuteen.',
    other: 'Variantista löytyi tietokantamerkintä, mutta se ei kuulu edellisiin pääluokkiin.',
  };
  return categoryText[finding.category] || categoryText.other;
}

function clinvarGeneUrl(finding: any) {
  return `https://www.ncbi.nlm.nih.gov/clinvar/?term=${encodeURIComponent(`${finding.gene}[gene]`)}`;
}

export default function App() {
  const [step, setStep] = useState(0);
  const [viewStage, setViewStage] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [textareaValue, setTextareaValue] = useState('');
  const [inputMode, setInputMode] = useState<'own' | 'demo'>('own');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [resourceProfile, setResourceProfile] = useState('light');
  const [mode, setMode] = useState('auto');
  const [genomeBuild, setGenomeBuild] = useState('GRCh38');
  const [status, setStatus] = useState('Valmiina');
  const [report, setReport] = useState<any>(null);
  const [showGeneticReport, setShowGeneticReport] = useState(false);
  const [counters, setCounters] = useState({ processed: 0, valid: 0, invalid: 0, matches: 0 });
  const [isRunning, setIsRunning] = useState(false);
  const [mainView, setMainView] = useState<MainView>('analysis');
  const [role, setRole] = useState<Role>('client');
  const [loopDashboard, setLoopDashboard] = useState<LoopDashboard | null>(null);
  const [loopError, setLoopError] = useState<string | null>(null);
  const [addingFindingId, setAddingFindingId] = useState<string | null>(null);
  const [addFindingError, setAddFindingError] = useState<{ id: string; message: string } | null>(null);
  const [deleteState, setDeleteState] = useState<{ phase: 'idle' | 'confirm' | 'done' | 'error'; message?: string }>({ phase: 'idle' });
  const [deleting, setDeleting] = useState(false);
  const confirmDeleteRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (deleteState.phase === 'confirm') confirmDeleteRef.current?.focus();
  }, [deleteState.phase]);

  useEffect(() => {
    loopApi.state().then(setLoopDashboard).catch((error: Error) => setLoopError(error.message));
  }, []);

  useEffect(() => {
    document.querySelector('.main-nav-button[aria-current="page"]')?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [mainView]);

  function openView(view: MainView) {
    setMainView(view);
    setShowGeneticReport(false); // the genetic report is hidden behind its button every time the view opens
    if (view !== 'analysis') {
      loopApi.state().then((data) => { setLoopDashboard(data); setLoopError(null); }).catch((error: Error) => setLoopError(error.message));
    }
  }

  function switchRole(next: Role) {
    setRole(next);
    openView(next === 'professional' ? 'professional' : 'situation');
  }

  async function requestProfessionalReview(findingId: string) {
    if (!sessionId) return;
    setAddingFindingId(findingId);
    setAddFindingError(null);
    try {
      const result = await supportApi.requestReview(sessionId, findingId);
      setLoopDashboard(result.dashboard);
    } catch (e) {
      setAddFindingError({ id: findingId, message: (e as Error).message });
    } finally {
      setAddingFindingId(null);
    }
  }

  const support = loopDashboard?.support;
  // after "Tyhjennä tiedot" the support payload is only {available: false}; the counters must not crash the app
  const openCheckIns = support?.available ? support.openCheckIns.length : 0;
  const professionalQueue = support?.available
    ? support.professional.pendingPlanIds.length + support.professional.escalationIds.length + support.professional.insightReviewIds.length
    : 0;
  const clientNav: { view: MainView; label: string; icon: ReactNode; badge?: string | null }[] = [
    { view: 'analysis', label: 'Perimätieto', icon: <DnaIcon size={22} /> },
    { view: 'timeline', label: 'Terveystiedot', icon: <CalendarIcon size={22} /> },
    {
      view: 'wellbeing',
      label: 'Hyvinvointidata',
      icon: <PulseIcon size={22} />,
      badge: support?.available && support.wellbeing?.newObservations
        ? `${support.wellbeing.newObservations} ${support.wellbeing.newObservations === 1 ? 'havainto' : 'havaintoa'}`
        : null,
    },
    {
      view: 'companion',
      label: 'Hyvinvointikumppani',
      icon: <ChatIcon size={22} />,
      badge: loopDashboard?.companion.unansweredProactive
        ? `${loopDashboard.companion.unansweredProactive} ${loopDashboard.companion.unansweredProactive === 1 ? 'uusi viesti' : 'uutta viestiä'}`
        : null,
    },
    { view: 'consent', label: 'Suostumukset', icon: <ShieldIcon size={22} /> },
    {
      view: 'situation',
      label: 'Tilanne nyt',
      icon: <HeartHandIcon size={22} />,
      badge: openCheckIns ? (openCheckIns === 1 ? '1 kysymys' : `${openCheckIns} kysymystä`) : null,
    },
    { view: 'audit', label: 'Agentin toiminta', icon: <ClipboardIcon size={22} /> },
  ];
  const professionalNav: typeof clientNav = [
    { view: 'professional', label: 'Työjono', icon: <StethoscopeIcon size={22} />, badge: professionalQueue ? `${professionalQueue} avoinna` : null },
    { view: 'audit', label: 'Agentin toiminta', icon: <ClipboardIcon size={22} /> },
    { view: 'impact', label: 'Vaikuttavuus', icon: <DocumentIcon size={22} /> },
  ];
  const navItems = role === 'client' ? clientNav : professionalNav;

  useEffect(() => {
    const saved = sessionStorage.getItem('omagenomi_session_id');
    if (saved) {
      setSessionId(saved);
      setStatus('Istunto löytyi. Voit jatkaa.');
    }
  }, []);

  async function requestJson(url: string, init?: RequestInit) {
    try {
      const res = await fetch(url, init);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Pyyntö epäonnistui.');
      }
      return data;
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Yhteys palvelimeen epäonnistui.');
      return null;
    }
  }

  async function runFullAnalysis(session: string) {
    setIsRunning(true);

    const preflight = await requestJson(`${API_BASE}/api/analysis/sessions/${session}/preflight`, { method: 'POST' });
    if (!preflight) {
      setIsRunning(false);
      return;
    }
    setStatus(preflight.warnings?.length ? preflight.warnings.join(', ') : 'Esitarkastus valmis.');
    setStep(2);

    let parseResult: any;
    let totalProcessed = 0;
    let totalValid = 0;
    let totalInvalid = 0;
    do {
      setStatus('DNA-aineistoa käsitellään...');
      parseResult = await requestJson(`${API_BASE}/api/analysis/sessions/${session}/parse-next`, { method: 'POST' });
      if (!parseResult) {
        setIsRunning(false);
        return;
      }
      totalProcessed += parseResult.processed_rows;
      totalValid += parseResult.valid_rows;
      totalInvalid += parseResult.invalid_rows;
      setCounters((prev) => ({ ...prev, processed: totalProcessed, valid: totalValid, invalid: totalInvalid }));
    } while (!parseResult.done);
    setStatus('Varianttien valmistelu valmis.');
    setStep(3);

    let matchResult: any;
    do {
      setStatus('DNA:ta verrataan tietokantaan...');
      matchResult = await requestJson(`${API_BASE}/api/analysis/sessions/${session}/match-next`, { method: 'POST' });
      if (!matchResult) {
        setIsRunning(false);
        return;
      }
      setCounters((prev) => ({ ...prev, matches: matchResult.position_matches }));
    } while (!matchResult.done);
    setStatus('Vertailu valmis.');
    setStep(4);

    setStatus('Löydöksiä luokitellaan...');
    const classified = await requestJson(`${API_BASE}/api/analysis/sessions/${session}/classify`, { method: 'POST' });
    if (!classified) {
      setIsRunning(false);
      return;
    }
    setStep(5);

    setStatus('Raporttia muodostetaan...');
    const finalized = await requestJson(`${API_BASE}/api/analysis/sessions/${session}/finalize`, { method: 'POST' });
    if (finalized) {
      setReport(finalized.report);
      setStatus('Raportti muodostettu.');
    }
    setIsRunning(false);
  }

  async function createFromPaste() {
    const data = await requestJson(`${API_BASE}/api/analysis/sessions/from-text?genome_build=${genomeBuild}&mode=${mode}&resource_profile=${resourceProfile}`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      body: textareaValue,
    });
    if (!data) return;
    setSessionId(data.session_id);
    sessionStorage.setItem('omagenomi_session_id', data.session_id);
    setStatus('DNA tallennettu paikallisesti. Analyysi alkaa...');
    setStep(1);
    setViewStage(1);
    await runFullAnalysis(data.session_id);
  }

  async function createFromFile() {
    if (!selectedFile) return;
    const form = new FormData();
    form.append('file', selectedFile);
    const data = await requestJson(`${API_BASE}/api/analysis/sessions/from-file`, { method: 'POST', body: form });
    if (!data) return;
    setSessionId(data.session_id);
    sessionStorage.setItem('omagenomi_session_id', data.session_id);
    setStatus('Tiedosto tallennettu paikallisesti. Analyysi alkaa...');
    setStep(1);
    setViewStage(1);
    await runFullAnalysis(data.session_id);
  }

  async function useDemo(kind: 'quick_snippet' | 'full_100k') {
    if (kind === 'quick_snippet') {
      const snippetData = await requestJson(`${API_BASE}/api/demo-snippet`);
      if (!snippetData) return;
      setTextareaValue(snippetData.text);
      setStatus('Testipätkä ladattu tekstialueeseen. Tallenna aineisto jatkaaksesi.');
      return;
    }
    const data = await requestJson(`${API_BASE}/api/analysis/sessions/from-demo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, mode, resource_profile: resourceProfile }),
    });
    if (!data) return;
    setSessionId(data.session_id);
    sessionStorage.setItem('omagenomi_session_id', data.session_id);
    setStatus('Täysi 100k demo perustettu. Analyysi alkaa...');
    setStep(1);
    setViewStage(1);
    await runFullAnalysis(data.session_id);
  }

  async function runPreflight() {
    if (!sessionId) return;
    const data = await requestJson(`${API_BASE}/api/analysis/sessions/${sessionId}/preflight`, { method: 'POST' });
    if (!data) return;
    setStatus(data.warnings.length ? data.warnings.join(', ') : 'Esitarkastus valmis');
    setStep(2);
  }

  async function runParseNext() {
    if (!sessionId) return;
    const data = await requestJson(`${API_BASE}/api/analysis/sessions/${sessionId}/parse-next`, { method: 'POST' });
    if (!data) return;
    setCounters((prev) => ({ ...prev, processed: data.processed_rows, valid: data.valid_rows, invalid: data.invalid_rows }));
    setStatus(data.done ? 'Varianttien valmistelu valmis.' : 'Käsitellään seuraavaa erää...');
    if (data.done) setStep(3);
  }

  async function runMatchNext() {
    if (!sessionId) return;
    const data = await requestJson(`${API_BASE}/api/analysis/sessions/${sessionId}/match-next`, { method: 'POST' });
    if (!data) return;
    setCounters((prev) => ({ ...prev, matches: data.position_matches }));
    setStatus(data.done ? 'Vertailu valmis.' : 'Vertailu käynnissä...');
    if (data.done) setStep(4);
  }

  async function runClassify() {
    if (!sessionId) return;
    const data = await requestJson(`${API_BASE}/api/analysis/sessions/${sessionId}/classify`, { method: 'POST' });
    if (!data) return;
    setReport(data);
    setStatus('Löydökset luokiteltu.');
    setStep(5);
  }

  async function runFinalize() {
    if (!sessionId) return;
    const data = await requestJson(`${API_BASE}/api/analysis/sessions/${sessionId}/finalize`, { method: 'POST' });
    if (!data) return;
    setReport(data.report);
    setStatus('Raportti muodostettu.');
    setStep(5);
  }

  async function removeSession() {
    setDeleting(true);
    if (sessionId) {
      await fetch(`${API_BASE}/api/analysis/sessions/${sessionId}`, { method: 'DELETE' });
    }
    try {
      const result = await loopApi.clearAll();
      setLoopDashboard(result.dashboard);
      setLoopError(null);
    } catch (e) {
      setDeleteState({ phase: 'error', message: (e as Error).message });
      setDeleting(false);
      return;
    }
    setDeleting(false);
    setDeleteState({ phase: 'done' });
    sessionStorage.removeItem('omagenomi_session_id');
    setSessionId(null);
    setTextareaValue('');
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setReport(null);
    setCounters({ processed: 0, valid: 0, invalid: 0, matches: 0 });
    setStep(0);
    setViewStage(0);
    setStatus('Kaikki tiedot poistettu.');
  }

  function renderFinding(finding: any, category: RelevanceCategory) {
    const insight = loopDashboard?.support.insights?.find((i) => i.kind === 'genetic' && i.findingId === finding.genomic_finding?.id);
    const approved = insight?.reviewStatus === 'approved';
    const pending = insight?.reviewStatus === 'pending_professional_review' || insight?.reviewStatus === 'info_requested';
    const uncertain = category === 'uncertain_or_conflicting';
    const geneticAllowed = loopDashboard?.support.consent?.dataSources.geneticInsights ?? true;
    const name = finding.gene || finding.rsid || 'Tuntematon variantti';
    return (
      <article className="finding" key={finding.id}>
        <div className="finding-heading">
          <strong>{name}</strong>
          <CategoryBadge
            category={approved ? 'professionally_approved' : category}
            label={approved ? 'Ammattilaisen hyväksymä taustatieto' : finding.relevance?.label ?? 'Ei luokiteltu'}
          />
        </div>
        {uncertain ? (
          <p>{finding.relevance?.reason}</p>
        ) : (
          <>
            <p><strong>Mihin tämä liittyy:</strong> {finding.disease_observation?.related_conditions?.length ? finding.disease_observation.related_conditions.map((c: string) => plain(c)).join(', ') : 'Tietokannassa ei ole nimettyä sairautta tai ominaisuutta.'}</p>
            <p><strong>Terveysalue:</strong> {finding.disease_observation?.health_area}</p>
            <p><strong>Yksinkertaisesti:</strong> {findingExplanation(finding)} {plain(finding.summary_fi)}</p>
            <p className="muted small">{approved ? insight?.reason : finding.relevance?.reason}</p>
          </>
        )}
        <small>{finding.rsid || '-'} | kromosomi {finding.chrom}, sijainti {finding.pos} | Genotyyppi {finding.genotype}</small>
        <details className="classification-details">
          <summary>Mitä tämä luokitus tarkoittaa?</summary>
          <p>{plain(finding.clinical_significance_fi)}: {plain(finding.classification_explanation_fi)}</p>
        </details>
        {category === 'needs_professional_check' && (
          <div className="finding-monitoring">
            {approved ? (
              <span className="chip chip-attention"><CheckIcon size={16} /> Ammattilaisen hyväksymä – vahvistamaton taustatieto</span>
            ) : pending ? (
              <span className="chip"><ClockIcon size={16} /> Odottaa ammattilaisen arviota</span>
            ) : (
              <button
                type="button"
                aria-label={`Pyydä ammattilaisen arvio: ${name}`}
                onClick={() => requestProfessionalReview(finding.id)}
                disabled={!sessionId || !geneticAllowed || addingFindingId === finding.id}
              >
                {addingFindingId === finding.id ? 'Lähetetään…' : 'Pyydä ammattilaisen arvio'}
              </button>
            )}
            {!geneticAllowed && <p className="muted small">Perimätiedon käyttö ei ole sallittu suostumusasetuksissasi.</p>}
          </div>
        )}
        {addFindingError && addFindingError.id === finding.id && (
          <p className="form-error" role="alert">{addFindingError.message}</p>
        )}
        {finding.gene && !uncertain && (
          <div className="finding-actions">
            <a className="button-link secondary" href={clinvarGeneUrl(finding)} target="_blank" rel="noreferrer">
              Kaikki geenin {finding.gene} tiedot <ExternalIcon size={16} />
              <span className="visually-hidden">(avautuu uuteen välilehteen)</span>
            </a>
          </div>
        )}
      </article>
    );
  }

  return (
    <div className="site">
      <header className="site-header">
        <div className="site-header-inner">
          <div className="site-header-top">
            <h1 className="site-brand">
              <span className="site-brand-mark" aria-hidden="true"><HeartHandIcon size={36} /></span>
              <span className="site-brand-text">
                <span className="site-brand-name">Agenttinen hyvinvointikumppani</span>
                <span className="site-brand-sub">Pitää omahoidon käynnissä arjessa myös vastaanottojen välissä</span>
              </span>
            </h1>
            <div className="site-header-tools">
              <div className="role-switch" role="group" aria-label="Näkymä">
                <button type="button" aria-pressed={role === 'client'} onClick={() => switchRole('client')}>
                  <PersonIcon size={18} /> Asiakas{loopDashboard ? `: ${loopDashboard.profile.name}` : ''}
                </button>
                <button type="button" aria-pressed={role === 'professional'} onClick={() => switchRole('professional')}>
                  <StethoscopeIcon size={18} /> Ammattilainen
                </button>
              </div>
              <span className="site-lang" aria-label="Kieli: suomi">FI</span>
            </div>
          </div>

          <nav className="main-nav" aria-label="Päänavigaatio">
            {navItems.map((item) => (
              <button
                key={item.view}
                type="button"
                className="main-nav-button"
                aria-current={mainView === item.view ? 'page' : undefined}
                onClick={() => openView(item.view)}
              >
                {item.icon}
                <span className="nav-label" data-label={item.label}>{item.label}</span>
                {item.badge && <span className="nav-count">{item.badge}</span>}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="site-main">
      {mainView !== 'analysis' && !loopDashboard && (
        <section className="panel">
          <h2>{navItems.find((item) => item.view === mainView)?.label}</h2>
          {loopError ? <p className="form-error" role="alert">{loopError}</p> : <p role="status">Ladataan tietoja…</p>}
        </section>
      )}
      {mainView === 'situation' && loopDashboard && (
        <SituationView dashboard={loopDashboard} setDashboard={setLoopDashboard} onNavigate={(view) => openView(view)} />
      )}
      {mainView === 'companion' && loopDashboard && <CompanionView dashboard={loopDashboard} setDashboard={setLoopDashboard} />}
      {mainView === 'timeline' && loopDashboard && (
        <Timeline
          dashboard={loopDashboard}
          setDashboard={setLoopDashboard}
          onOpenQuiz={() => openView('quiz')}
          onOpenAnalysis={() => openView('analysis')}
          dnaSessionId={report?.analysis ? sessionId : null}
        />
      )}
      {/* the DNA report is read together with the other health data (it is produced on the Perimätieto tab) */}
      {mainView === 'timeline' && report?.analysis && (
        <div className="timeline-report">
          <button type="button" className="btn-secondary" aria-expanded={showGeneticReport} onClick={() => setShowGeneticReport(!showGeneticReport)}>
            <DocumentIcon size={18} /> {showGeneticReport ? 'Piilota perimätietoraportti' : 'Näytä perimätietoraportti'}
          </button>
          {showGeneticReport && <section className="panel">
            <div className="panel-heading">
              <span className="panel-heading-icon" aria-hidden="true"><DocumentIcon size={48} /></span>
              <h2>Perimätietoraportti</h2>
            </div>
            <div className="stat-grid">
              <div className="stat"><span className="stat-value">{report.analysis?.relevance_counts?.needs_professional_check || 0}</span><span className="stat-label">Ammattilaisen arvioon ehdotettavat</span></div>
              <div className="stat"><span className="stat-value">{report.analysis?.relevance_counts?.no_practical_significance || 0}</span><span className="stat-label">Ei käytännön merkitystä</span></div>
              <div className="stat"><span className="stat-value">{report.analysis?.relevance_counts?.uncertain_or_conflicting || 0}</span><span className="stat-label">Epävarmat (ei käytetä)</span></div>
            </div>
            <p className="disclaimer-box" role="note">
              Raportti ei vaikuta seurantaasi. Vain ammattilaisen hyväksymä havainto voi olla seurannan taustatietona.
            </p>
            <div className="report-content">
              {report.findings?.length ? RELEVANCE_GROUPS.map((group) => {
                const items = report.findings.filter((f: any) => (f.relevance?.category ?? 'no_practical_significance') === group.category);
                if (!items.length) return null;
                return (
                  <details key={group.category} className="relevance-group" open={group.open}>
                    <summary><h3>{group.title} ({items.length})</h3></summary>
                    <p className="muted">{group.intro}</p>
                    {items.map((finding: any) => renderFinding(finding, group.category))}
                  </details>
                );
              }) : <p>Analyysissä ei löytynyt raportoitavia variantteja.</p>}
            </div>
          </section>}
        </div>
      )}
      {mainView === 'wellbeing' && loopDashboard && (
        <WellbeingDataView dashboard={loopDashboard} setDashboard={setLoopDashboard} onOpenCompanion={() => openView('companion')} />
      )}
      {mainView === 'consent' && loopDashboard && <ConsentView dashboard={loopDashboard} setDashboard={setLoopDashboard} />}
      {mainView === 'audit' && loopDashboard && <AuditView dashboard={loopDashboard} role={role} />}
      {mainView === 'professional' && loopDashboard && <ProfessionalView dashboard={loopDashboard} setDashboard={setLoopDashboard} />}
      {mainView === 'impact' && loopDashboard && <ImpactView dashboard={loopDashboard} />}
      {mainView === 'summary' && loopDashboard && (
        <>
          <button type="button" className="btn-secondary back-button" onClick={() => openView('situation')}><ArrowLeftIcon size={18} /> Takaisin: Tilanne nyt</button>
          {loopDashboard.counts.activeMonitorings > 0 ? (
            <FullSummary />
          ) : (
            <section className="panel">
              <div className="panel-heading">
                <span className="panel-heading-icon" aria-hidden="true"><DocumentIcon size={48} /></span>
                <h2>Yhteenveto terveydenhuollon ammattilaiselle</h2>
              </div>
              <p>Yhteenveto muodostetaan seurannassa olevista, ammattilaisen hyväksymistä perimätiedon havainnoista. Niitä ei nyt ole käytössä.</p>
            </section>
          )}
        </>
      )}
      {mainView === 'quiz' && loopDashboard && (
        <>
          <button type="button" className="btn-secondary back-button" onClick={() => openView('situation')}><ArrowLeftIcon size={18} /> Takaisin: Tilanne nyt</button>
          <p className="stage-help">Laaja elämäntapakysely on vapaaehtoinen. Hyvinvointikumppani kysyy tarvittaessa 1–3 lyhyttä kysymystä seurantasuunnitelmasi perusteella.</p>
          <LifestyleQuiz dashboard={loopDashboard} setDashboard={setLoopDashboard} />
        </>
      )}

      {mainView === 'analysis' && <>
      <div className="wizard">
        {STEPS.map((label, index) => (
          <button
            key={label}
            type="button"
            className={`step ${index === viewStage ? 'active' : ''} ${index < viewStage ? 'done' : ''}`}
            onClick={() => setViewStage(index)}
          >
            <span>{index < viewStage ? <CheckIcon size={16} /> : index + 1}</span>
            <div>{label}</div>
          </button>
        ))}
      </div>

      <div className={`content-grid ${viewStage === 1 ? 'single-column' : ''}`}>
        <div className="left-column">
          {viewStage === 0 && <section className="panel">
            <div className="panel-heading">
              <span className="panel-heading-icon" aria-hidden="true"><DnaIcon size={48} /></span>
              <h2>Oma DNA-aineisto</h2>
            </div>
            <p className="lead">Tuo raakadata tai kokeile testiaineistolla. Analyysi tehdään paikallisesti tällä laitteella.</p>

            <div className="option-cards">
              <button type="button" className="option-card" onClick={() => { setInputMode('own'); fileInputRef.current?.click(); }}>
                <span className="option-card-icon" aria-hidden="true"><UploadIcon size={48} /></span>
                <span className="option-card-title">Valitse oma DNA-tiedosto</span>
                <span className="option-card-text">Tuo tekstimuotoinen raakadatatiedosto tai liitä rivit alla olevaan kenttään.</span>
                <span className="option-card-chevron" aria-hidden="true"><ChevronRightIcon size={26} /></span>
              </button>
              <button type="button" className="option-card" onClick={() => useDemo('quick_snippet')}>
                <span className="option-card-icon" aria-hidden="true"><TestTubeIcon size={48} /></span>
                <span className="option-card-title">Käytä testi-DNA:ta</span>
                <span className="option-card-text">Kokeile palvelua synteettisellä esimerkkiaineistolla. Ei oikean henkilön tietoja.</span>
                <span className="option-card-chevron" aria-hidden="true"><ChevronRightIcon size={26} /></span>
              </button>
            </div>

            {inputMode === 'own' && (
              <div className="text-editing">
                <input
                  ref={fileInputRef}
                  id="dna-file"
                  type="file"
                  accept=".txt,.tsv,.csv,.vcf,text/plain,text/tab-separated-values"
                  hidden
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                />
                {selectedFile && <p className="file-name"><CheckIcon size={18} /> {selectedFile.name} ({selectedFile.size} tavua)</p>}
                <label htmlFor="dna-text">DNA-rivit</label>
                <textarea
                  id="dna-text"
                  value={textareaValue}
                  onChange={(e) => setTextareaValue(e.target.value)}
                  rows={5}
                  placeholder={'rsid chromosome position genotype\nrs6025 1 169549811 CT'}
                />
                <div className="row">
                  <button onClick={selectedFile ? createFromFile : createFromPaste}>Tallenna DNA-aineisto ja jatka esitarkastukseen</button>
                  <button
                    type="button"
                    className="btn-secondary"
                    aria-expanded={deleteState.phase === 'confirm'}
                    aria-controls="delete-confirm"
                    onClick={() => setDeleteState({ phase: 'confirm' })}
                  >
                    <TrashIcon size={18} /> Tyhjennä ja poista kaikki tiedot
                  </button>
                </div>
                {deleteState.phase === 'confirm' && (
                  <div
                    id="delete-confirm"
                    className="confirm-box"
                    role="alertdialog"
                    aria-labelledby="delete-confirm-title"
                    aria-describedby="delete-confirm-text"
                    onKeyDown={(e) => e.key === 'Escape' && setDeleteState({ phase: 'idle' })}
                  >
                    <p id="delete-confirm-title" className="confirm-box-title"><WarningIcon size={22} /> Poistetaanko kaikki tietosi?</p>
                    <p id="delete-confirm-text">
                      DNA-aineisto, raportti, keskustelut, kyselyvastaukset ja omat lisäyksesi poistetaan kaikilta välilehdiltä. Toimintoa ei voi perua.
                      Terveydenhuollon kirjaamat terveystiedot säilyvät, koska ne luetaan lähdejärjestelmistä.
                    </p>
                    <div className="row">
                      <button type="button" ref={confirmDeleteRef} className="btn-danger" disabled={deleting} onClick={removeSession}>
                        {deleting ? 'Poistetaan…' : 'Kyllä, poista kaikki tiedot'}
                      </button>
                      <button type="button" className="btn-secondary" disabled={deleting} onClick={() => setDeleteState({ phase: 'idle' })}>Peruuta</button>
                    </div>
                  </div>
                )}
                {deleteState.phase === 'done' && (
                  <p className="success-text" role="status"><CheckIcon size={18} /> Tietosi poistettiin. Terveystiedot luettiin lähdejärjestelmistä uudelleen.</p>
                )}
                {deleteState.phase === 'error' && (
                  <p className="form-error" role="alert">Tietojen poisto epäonnistui: {deleteState.message}</p>
                )}
              </div>
            )}

            <p className="local-note">
              <LockIcon size={26} />
              <span>DNA-tietoja ei lähetetä verkkoon. Ne käsitellään paikallisesti, ja voit poistaa ne milloin tahansa.</span>
            </p>

            <details className="settings-box">
              <summary>
                <span className="settings-title">Analyysin asetukset</span>
                <span className="settings-current">
                  {genomeBuild} · {{ auto: 'Automaattinen', demo: 'Demo', clinvar: 'Paikallinen ClinVar' }[mode] ?? mode} · {{ ultralight: 'Erittäin kevyt tila', light: 'Kevyt tila', normal: 'Normaali tila' }[resourceProfile] ?? resourceProfile}
                </span>
              </summary>
              <div className="selectors">
                <label>
                  Genomirakennelma
                  <select value={genomeBuild} onChange={(e) => setGenomeBuild(e.target.value)}>
                    <option value="GRCh38">GRCh38</option>
                  </select>
                  <small>DNA-aineiston koordinaattijärjestelmä. Käytä tässä GRCh38-valintaa.</small>
                </label>
                <label>
                  Vertailutapa
                  <select value={mode} onChange={(e) => setMode(e.target.value)}>
                    <option value="auto">Automaattinen</option>
                    <option value="demo">Demo</option>
                    <option value="clinvar">Paikallinen ClinVar</option>
                  </select>
                  <small>Automaattinen valitsee käytettävissä olevan paikallisen lähteen.</small>
                </label>
                <label>
                  Resurssiprofiili
                  <select value={resourceProfile} onChange={(e) => setResourceProfile(e.target.value)}>
                    <option value="ultralight">Erittäin kevyt tila</option>
                    <option value="light">Kevyt tila</option>
                    <option value="normal">Normaali tila</option>
                  </select>
                  <small>Määrittää käsittelyerien koon. Kevyt tila sopii tavalliseen käyttöön.</small>
                </label>
              </div>
            </details>
          </section>}

          {viewStage === 1 && step > 0 && (isRunning || !report?.analysis) && <section className="panel">
            <h2>Analyysin eteneminen</h2>
            {isRunning && <p className="stage-help">Analyysi etenee automaattisesti. Sinun ei tarvitse tehdä mitään.</p>}
            {!isRunning && (
              <p className="stage-help">Analyysin viimeisin vaihe ei mennyt läpi. Voit jatkaa siitä, mihin jäätiin.</p>
            )}
            {!isRunning && <div className="row">
              {step === 1 && <button onClick={runPreflight}>Suorita esitarkastus</button>}
              {step === 2 && <button onClick={runParseNext}>Käsittele seuraava DNA-erä</button>}
              {step === 3 && <button onClick={runMatchNext}>Vertaa ClinVar-tietoon</button>}
              {step === 4 && <button onClick={runClassify}>Luokittele löydökset</button>}
              {step === 5 && <button onClick={runFinalize}>Muodosta raportti</button>}
            </div>}
          </section>}

          {viewStage === 1 && <section className="panel status-panel">
            <h2>Analyysi</h2>
            {!report?.analysis && <p className={`status-line ${isRunning ? 'is-running' : ''}`} role="status">{status}</p>}
            {report?.analysis && <FindingsOverview report={report} />}
          </section>}
        </div>

        <div className="right-column">
          {viewStage === 1 && report?.analysis && loopDashboard && (
            <GeneticSourcePanel dashboard={loopDashboard} setDashboard={setLoopDashboard} onOpenConsent={() => openView('consent')} />
          )}
        </div>
      </div>
      </>}
      {role === 'client' && loopDashboard && (
        <FlowNav items={clientNav} current={mainView} onOpen={openView} />
      )}
      </main>

      <footer className="site-footer">
        <div className="site-footer-inner">
          <p>
            <strong>Agenttinen hyvinvointikumppani</strong>
            Demo synteettisellä aineistolla. Omahoidon jatkuvuus ammattilaisen hyväksymän suunnitelman mukaan: muistaa, ottaa itse yhteyttä, ehdottaa yhden askeleen kerrallaan ja huomaa, milloin tarvitaan ammattilaista. Hoidon tarpeen arvio sääntöjen perusteella (terveydenhuoltolaki 51 § 3 mom. – oletettu voimaantulo 2027). Ei diagnooseja, ei lääkitysohjeita. Ammattilaisen arvion voi aina pyytää.
          </p>
          <p className="site-footer-trust">
            <LockIcon size={28} />
            <span>Tiedot käsitellään vain tällä laitteella.</span>
          </p>
        </div>
      </footer>
    </div>
  );
}

/** Demo flow: the client views are ordered like the story, and each view ends with a link to the next one. */
function FlowNav({ items, current, onOpen }: { items: { view: MainView; label: string }[]; current: MainView; onOpen: (view: MainView) => void }) {
  const index = items.findIndex((item) => item.view === current);
  if (index < 0) return null;
  const previous = items[index - 1];
  const next = items[index + 1];
  return (
    <nav className="flow-nav" aria-label="Demon kulku">
      <span className="flow-nav-step">Vaihe {index + 1}/{items.length}</span>
      <div className="flow-nav-buttons">
        {previous && (
          <button type="button" className="btn-secondary" onClick={() => onOpen(previous.view)}><ArrowLeftIcon size={18} /> {previous.label}</button>
        )}
        {next ? (
          <button type="button" onClick={() => onOpen(next.view)}>Seuraava: {next.label} <ArrowRightIcon size={18} /></button>
        ) : (
          <span className="muted">Vaihda yläkulmasta näkymään <strong>Ammattilainen</strong>.</span>
        )}
      </div>
    </nav>
  );
}
