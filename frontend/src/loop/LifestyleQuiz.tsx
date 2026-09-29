import { useState } from 'react';
import type { ReactNode } from 'react';
import {
  AppleIcon,
  ArrowLeftIcon,
  CheckIcon,
  ClipboardIcon,
  ClockIcon,
  FamilyIcon,
  GlassIcon,
  LeafIcon,
  MoonIcon,
  NoSmokingIcon,
  SproutIcon,
  StethoscopeIcon,
  WalkIcon,
} from '../icons';
import { loopApi } from './api';
import { formatDate } from './labels';
import type { LoopDashboard } from './types';

type Tier = 'strong' | 'okay' | 'watch';

interface QuizOption {
  id: string;
  label: string;
  tier: Tier;
}

interface QuizQuestion {
  id: string;
  icon: ReactNode;
  question: string;
  options: QuizOption[];
}

const ICON_SIZE = 64;

const QUESTIONS: QuizQuestion[] = [
  {
    id: 'liikunta',
    icon: <WalkIcon size={ICON_SIZE} />,
    question: 'Kuinka usein olet liikkunut reippaasti (esim. kävely, pyöräily, liikunta) viimeisen kuukauden aikana?',
    options: [
      { id: 'usein', label: 'Useita kertoja viikossa', tier: 'strong' },
      { id: 'silloin_tallom', label: 'Muutaman kerran kuukaudessa', tier: 'okay' },
      { id: 'harvoin', label: 'Hyvin harvoin tai en lainkaan', tier: 'watch' },
    ],
  },
  {
    id: 'ruokavalio',
    icon: <AppleIcon size={ICON_SIZE} />,
    question: 'Millaista ruokaa olet syönyt viimeisen kuukauden aikana?',
    options: [
      { id: 'kasviksia', label: 'Enimmäkseen kasviksia, kalaa, kuitua ja pehmeitä rasvoja', tier: 'strong' },
      { id: 'sekalaista', label: 'Sekalaista, vaihtelevasti', tier: 'okay' },
      { id: 'lihaa_rasvaa', label: 'Paljon punaista lihaa, kovaa rasvaa tai valmisruokaa', tier: 'watch' },
    ],
  },
  {
    id: 'tupakointi',
    icon: <NoSmokingIcon size={ICON_SIZE} />,
    question: 'Oletko tupakoinut tai käyttänyt muita nikotiinituotteita viimeisen kuukauden aikana?',
    options: [
      { id: 'ei', label: 'En lainkaan', tier: 'strong' },
      { id: 'satunnaisesti', label: 'Satunnaisesti', tier: 'okay' },
      { id: 'saannollisesti', label: 'Säännöllisesti', tier: 'watch' },
    ],
  },
  {
    id: 'alkoholi',
    icon: <GlassIcon size={ICON_SIZE} />,
    question: 'Kuinka usein olet käyttänyt alkoholia viimeisen kuukauden aikana?',
    options: [
      { id: 'ei_juuri', label: 'En lainkaan tai vain kerran pari', tier: 'strong' },
      { id: 'kohtuudella', label: 'Kohtuudella, noin viikoittain', tier: 'okay' },
      { id: 'usein', label: 'Usein tai runsaasti', tier: 'watch' },
    ],
  },
  {
    id: 'uni',
    icon: <MoonIcon size={ICON_SIZE} />,
    question: 'Oletko nukkunut riittävästi ja hyvin (n. 7–8 tuntia) viimeisen kuukauden aikana?',
    options: [
      { id: 'kylla', label: 'Kyllä, useimpina öinä', tier: 'strong' },
      { id: 'vaihtelevasti', label: 'Vaihtelevasti', tier: 'okay' },
      { id: 'harvoin', label: 'Harvoin tai en juuri koskaan', tier: 'watch' },
    ],
  },
  {
    id: 'sukuhistoria',
    icon: <FamilyIcon size={ICON_SIZE} />,
    question: 'Oletko viimeisen kuukauden aikana selvittänyt tai keskustellut läheistesi kanssa, onko lähisuvussasi todettu varhaisia sydän- ja verisuonisairauksia tai korkeaa kolesterolia?',
    options: [
      { id: 'tiedan', label: 'Kyllä, ja tilanne on minulle selvä', tier: 'strong' },
      { id: 'en_varma', label: 'Olen kysellyt, mutta asia on vielä epäselvä', tier: 'okay' },
      { id: 'en_ole_selvittanyt', label: 'En ole selvittänyt', tier: 'watch' },
    ],
  },
  {
    id: 'seuranta',
    icon: <StethoscopeIcon size={ICON_SIZE} />,
    question: 'Oletko mitannut verenpaineesi tai kolesterolisi viimeisen kuukauden aikana?',
    options: [
      { id: 'alle_vuosi', label: 'Kyllä', tier: 'strong' },
      { id: 'yli_vuosi', label: 'En tässä kuussa, mutta viimeisen vuoden aikana', tier: 'okay' },
      { id: 'en_muista', label: 'En, tai edellisestä mittauksesta on yli vuosi', tier: 'watch' },
    ],
  },
  {
    id: 'stressi',
    icon: <LeafIcon size={ICON_SIZE} />,
    question: 'Miten olet palautunut arjen kiireestä ja stressistä viimeisen kuukauden aikana?',
    options: [
      { id: 'hyvin', label: 'Hyvin, olen löytänyt aikaa palautumiselle', tier: 'strong' },
      { id: 'vaihtelevasti', label: 'Vaihtelevasti', tier: 'okay' },
      { id: 'huonosti', label: 'Huonosti, stressi on kasautunut', tier: 'watch' },
    ],
  },
];

const TIPS: Record<string, Partial<Record<Tier, string>>> = {
  liikunta: {
    okay: 'Pienikin lisäys arkiliikuntaan auttaa: kokeile lisätä yksi reipas kävelylenkki viikkoon.',
    watch: 'Aloita pienestä: jo 10–15 minuutin päivittäinen kävely tukee sydän- ja verisuoniterveyttä pitkällä aikavälillä.',
  },
  ruokavalio: {
    okay: 'Lisää kasviksia ja kuitua aterioihin ja vähennä kovaa rasvaa vähän kerrallaan – pienet muutokset kertyvät ajan mittaan.',
    watch: 'Harkitse yhtä konkreettista muutosta kerrallaan, esim. voin vaihtamista kasviöljyyn tai kalan lisäämistä ruokavalioon.',
  },
  tupakointi: {
    okay: 'Nikotiinin käytön vähentäminen tukee sydän- ja verisuoniterveyttä – terveysasemalta saa tukea lopettamiseen.',
    watch: 'Tupakoinnin lopettaminen on yksi tehokkaimmista tavoista tukea sydänterveyttä – terveysasema tarjoaa maksutonta tukea.',
  },
  alkoholi: {
    okay: 'Kohtuullisuuden rajojen tarkistaminen ajoittain kannattaa oman hyvinvoinnin tueksi.',
    watch: 'Alkoholinkäytön vähentäminen tukee monella tapaa terveyttä – asiasta voi keskustella luottamuksellisesti terveydenhuollossa.',
  },
  uni: {
    okay: 'Säännöllinen unirytmi ja rauhoittuminen ennen nukkumaanmenoa voivat parantaa unenlaatua.',
    watch: 'Unen puute kuormittaa kehoa monella tapaa – kokeile kiinteää nukkumaanmenoaikaa muutaman viikon ajan.',
  },
  sukuhistoria: {
    okay: 'Voit täydentää suvun sairaushistorian Hyvinvointikumppanille – se auttaa seurantaa tulkitsemaan tilannettasi tarkemmin.',
    watch: 'Suvun sairaushistorian selvittäminen ja kertominen Hyvinvointikumppanille voi olla arvokasta seurantasi kannalta.',
  },
  seuranta: {
    okay: 'Säännölliset perusmittaukset (verenpaine, kolesteroli) auttavat huomaamaan muutokset ajoissa.',
    watch: 'Ajantasainen verenpaine- tai kolesterolimittaus antaisi seurannalle hyvän lähtökohdan – tuloksen voi kirjata myös OmaGenomiin.',
  },
  stressi: {
    okay: 'Pienetkin palautumishetket (esim. kävely, hengitysharjoitukset) tukevat jaksamista.',
    watch: 'Palautumiselle kannattaa raivata tilaa arjesta – pienikin säännöllinen tauko voi auttaa.',
  },
};

const MONTHS_GENITIVE = [
  'tammikuun', 'helmikuun', 'maaliskuun', 'huhtikuun', 'toukokuun', 'kesäkuun',
  'heinäkuun', 'elokuun', 'syyskuun', 'lokakuun', 'marraskuun', 'joulukuun',
];

function monthGenitive(isoDate: string) {
  const monthIndex = Number(isoDate.slice(5, 7)) - 1;
  return MONTHS_GENITIVE[monthIndex] ?? 'kuukauden';
}

function capitalize(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

interface Props {
  dashboard: LoopDashboard;
  setDashboard: (dashboard: LoopDashboard) => void;
}

export default function LifestyleQuiz({ dashboard, setDashboard }: Props) {
  const [step, setStep] = useState(-1); // -1 = intro, QUESTIONS.length = results
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const monitoredFindings = dashboard.findings.filter((f) => f.monitored);
  const total = QUESTIONS.length;

  const pastResults = dashboard.events
    .filter((e) => e.type === 'lifestyle_survey')
    .sort((a, b) => (a.date < b.date ? 1 : -1));
  const lastResult = pastResults[0] ?? null;
  const currentMonth = dashboard.currentDate.slice(0, 7);
  const doneThisMonth = lastResult?.date.slice(0, 7) === currentMonth;
  const monthLabel = monthGenitive(dashboard.currentDate);

  function choose(questionId: string, optionId: string) {
    setAnswers((prev) => ({ ...prev, [questionId]: optionId }));
    window.setTimeout(() => setStep((s) => Math.min(s + 1, total)), 200);
  }

  function restart() {
    setAnswers({});
    setSaved(false);
    setSaveError(null);
    setStep(-1);
  }

  function tierFor(question: QuizQuestion): Tier | null {
    const chosen = answers[question.id];
    return question.options.find((o) => o.id === chosen)?.tier ?? null;
  }

  async function saveResults() {
    setSaving(true);
    setSaveError(null);
    const structuredData: Record<string, { answer: string; tier: Tier }> = {};
    const lines: string[] = [];
    for (const q of QUESTIONS) {
      const chosen = q.options.find((o) => o.id === answers[q.id]);
      if (!chosen) continue;
      structuredData[q.id] = { answer: chosen.label, tier: chosen.tier };
      lines.push(`${q.question} ${chosen.label}`);
    }
    const rawText = `${capitalize(monthLabel)} elämäntapakysely täytetty ${formatDate(dashboard.currentDate)}: ${lines.join(' | ')}`;
    try {
      const result = await loopApi.submitLifestyleQuiz(structuredData, rawText);
      setDashboard(result.dashboard);
      setSaved(true);
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const watchTips = QUESTIONS
    .map((q) => ({ q, tier: tierFor(q) }))
    .filter(({ tier }) => tier === 'watch')
    .map(({ q }) => TIPS[q.id]?.watch)
    .filter((t): t is string => Boolean(t));
  const okayTips = QUESTIONS
    .map((q) => ({ q, tier: tierFor(q) }))
    .filter(({ tier }) => tier === 'okay')
    .map(({ q }) => TIPS[q.id]?.okay)
    .filter((t): t is string => Boolean(t));
  const resultTips = [...watchTips, ...okayTips].slice(0, 4);
  const familyHistoryUnclear = tierFor(QUESTIONS.find((q) => q.id === 'sukuhistoria')!) !== 'strong';

  return (
    <section className="panel quiz-panel" aria-labelledby="quiz-title">
      <div className="panel-heading">
        <span className="panel-heading-icon" aria-hidden="true"><ClipboardIcon size={48} /></span>
        <h2 id="quiz-title">Elämäntapatesti</h2>
      </div>
      <p className="muted small">
        Kuukausittainen elämäntapakysely siitä, mitä olet tehnyt viimeisen kuukauden aikana. Vastaukset
        tallentuvat seurantaasi ja tukevat kokonaiskuvaa hyvinvoinnistasi.
      </p>

      {step === -1 && (
        <p className="muted small">
          {doneThisMonth
            ? `${capitalize(monthLabel)} kysely on jo tehty (${formatDate(lastResult!.date)}). Voit silti täyttää sen uudelleen.`
            : lastResult
              ? `${capitalize(monthLabel)} kysely on vielä tekemättä. Edellinen kysely tehty ${formatDate(lastResult.date)}.`
              : `${capitalize(monthLabel)} kysely on vielä tekemättä.`}
        </p>
      )}

      {step >= 0 && step < total && (
        <div className="quiz-progress-wrap">
          <div className="quiz-progress" role="progressbar" aria-valuenow={step + 1} aria-valuemin={1} aria-valuemax={total}>
            <div className="quiz-progress-bar" style={{ width: `${((step + 1) / total) * 100}%` }} />
          </div>
          <span className="muted small">Kysymys {step + 1}/{total}</span>
        </div>
      )}

      {step === -1 && (
        <div className="quiz-card">
          <div className="quiz-card-icon" aria-hidden="true"><ClipboardIcon size={ICON_SIZE} /></div>
          <h3>{capitalize(monthLabel)} elämäntapakysely</h3>
          <p>
            {monitoredFindings.length > 0
              ? `Seurannassasi on ${monitoredFindings.length === 1 ? 'yksi geneettinen löydös' : `${monitoredFindings.length} geneettistä löydöstä`}. Yleiset, terveelliset elämäntavat tukevat hyvinvointia riippumatta löydösten tarkasta luonteesta.`
              : 'Vastaa kahdeksaan lyhyeen kysymykseen siitä, mitä olet tehnyt viimeisen kuukauden aikana.'}
            {' '}Kysymykset koskevat viimeistä kuukautta. Kysely kestää pari minuuttia ja antaa lopuksi muutaman sinulle poimitun vinkin. Toistuu kerran kuukaudessa, jotta kehityksen näkee ajan mittaan.
          </p>
          <button type="button" onClick={() => setStep(0)}>Aloita kysely</button>
        </div>
      )}

      {step >= 0 && step < total && (
        <div className="quiz-card" key={QUESTIONS[step].id}>
          <div className="quiz-card-icon" aria-hidden="true">{QUESTIONS[step].icon}</div>
          <h3>{QUESTIONS[step].question}</h3>
          <div className="quiz-options" role="group" aria-label="Vastausvaihtoehdot">
            {QUESTIONS[step].options.map((option) => (
              <button
                key={option.id}
                type="button"
                className={`quiz-option${answers[QUESTIONS[step].id] === option.id ? ' selected' : ''}`}
                onClick={() => choose(QUESTIONS[step].id, option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
          {step > 0 && (
            <button type="button" className="link-button" onClick={() => setStep((s) => s - 1)}><ArrowLeftIcon size={16} /> Edellinen kysymys</button>
          )}
        </div>
      )}

      {step === total && (
        <div className="quiz-card quiz-results">
          <div className="quiz-card-icon" aria-hidden="true"><SproutIcon size={ICON_SIZE} /></div>
          <h3>{capitalize(monthLabel)} ennaltaehkäisysuunnitelmasi</h3>
          <p>
            {monitoredFindings.length > 0
              ? `Seurannassasi on ${monitoredFindings.map((f) => f.title).join(', ')}. Näillä muutamalla arjen valinnalla tuet omaa hyvinvointiasi ennaltaehkäisevästi:`
              : 'Näillä muutamalla arjen valinnalla tuet omaa hyvinvointiasi ennaltaehkäisevästi:'}
          </p>
          {resultTips.length > 0 ? (
            <div className="quiz-tip-grid">
              {resultTips.map((tip) => (
                <div className="quiz-tip-card" key={tip}>{tip}</div>
              ))}
            </div>
          ) : (
            <div className="quiz-tip-grid">
              <div className="quiz-tip-card">Vastauksesi kertovat jo vahvoista, terveyttä tukevista arjen tavoista. Jatka samaan malliin!</div>
            </div>
          )}
          {familyHistoryUnclear && (
            <p className="muted small">
              Vinkki: voit kertoa suvun sairaushistoriasta Hyvinvointikumppanille, niin se voidaan huomioida seurannassasi.
            </p>
          )}
          <p className="muted small">
            Tämä kysely ei ole diagnoosi tai hoitosuositus eikä perustu terveystietoihisi – se antaa vain yleisiä,
            kaikille sopivia ennaltaehkäisyvinkkejä vastaustesi pohjalta.
          </p>
          {saveError && <p className="form-error" role="alert">{saveError}</p>}
          <div className="row">
            {saved ? (
              <p className="success-text" role="status"><CheckIcon size={18} /> Tallennettu seurantaasi.</p>
            ) : (
              <button type="button" onClick={saveResults} disabled={saving}>
                {saving ? 'Tallennetaan…' : `Tallenna ${monthLabel} kysely seurantaasi`}
              </button>
            )}
            <button type="button" className="btn-secondary" onClick={restart}>Täytä kysely uudelleen</button>
          </div>
        </div>
      )}

      {pastResults.length > 0 && (
        <div className="quiz-history">
          <button type="button" className="link-button quiz-history-toggle" onClick={() => setShowHistory((v) => !v)}>
            <ClockIcon size={16} />
            {showHistory ? 'Piilota aiemmat tulokset' : `Näytä aiemmat tulokset (${pastResults.length})`}
          </button>
          {showHistory && (
            <ul className="quiz-history-list">
              {pastResults.map((e) => (
                <li key={e.id}>
                  <strong>{formatDate(e.date)}</strong>
                  <span className="muted small">{e.rawText}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
