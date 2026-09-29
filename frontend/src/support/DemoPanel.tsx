import { useState } from 'react';
import { CheckIcon } from '../icons';
import { loopApi } from '../loop/api';
import { formatDate } from '../loop/labels';
import type { LoopDashboard } from '../loop/types';
import { supportApi } from './api';
import { useRunner } from './useRunner';

interface Props {
  dashboard: LoopDashboard;
  setDashboard: (dashboard: LoopDashboard) => void;
}

const ACTION_WORDS: Record<string, string> = {
  no_action: 'ei yhteydenottoa (tilanne vakaa)',
  deferred: 'yhteydenotto lykättiin suostumusasetusten vuoksi',
  check_in: 'lähetti check-in-kysymyksiä',
  reminder: 'lähetti muistutuksen',
  show_guide: 'näytti hyväksytyn ohjeen',
  clarifying_question: 'kysyi tarkentavan kysymyksen',
  escalate: 'teki automaattisen arvion ja ohjasi ammattilaiselle',
  offer_home_monitoring: 'ehdotti itse kolmen päivän kotiseurantaa',
};

type CycleResult = { plans?: { plan: string; action: string }[] } | null | undefined;

function describeCycle(cycle: CycleResult): string {
  if (!cycle?.plans?.length) return 'Agenttikierros ajettu: ei aktiivisia seurantoja.';
  return 'Agenttikierros: ' + cycle.plans.map((p) => `${p.plan} – ${ACTION_WORDS[p.action] ?? p.action}`).join('; ') + '.';
}

/** The scripted story of the demo, derived from the state so the presenter always sees the next move. */
function demoSteps(dashboard: LoopDashboard) {
  const support = dashboard.support;
  if (!support.available) return [];
  const plan = support.plans.find((p) => p.theme === 'blood_pressure');
  if (!plan) return [];
  const escalations = support.escalations.filter((e) => e.planId === plan.id);
  const completed = plan.checkIns.filter((c) => c.status === 'completed');
  const approved = plan.approval.status === 'approved';
  const week1 = approved && completed.length > 0;
  const escalated = escalations.length > 0;
  const monitoring = support.continuity?.homeMonitoring;
  const offered = escalated || Boolean(monitoring?.offer || monitoring?.active || monitoring?.latest);
  const monitored = escalated || Boolean(monitoring?.latest);
  const updated = escalations.some((e) => e.status === 'resolved') || plan.version >= 2;
  const continued = updated && completed.some((c) => c.planVersion >= 2);
  // while a check-in is open, the next move is to answer it (one click per question)
  const answering = support.openCheckIns.length > 0;
  const askHint = (first: string) => (answering ? 'Vastaa kysymyksiin – tai paina Simuloi käyttäjän vastaus, kunnes tarkistus on valmis' : first);
  const monitorHint = monitoring?.offer
    ? 'Vastaa ehdotukseen: Kyllä, aloitetaan (Hyvinvointikumppani tai Tilanne nyt)'
    : 'Simuloi kotiseuranta (3 pv)';
  return [
    { title: 'Hoitaja hyväksyy verenpainesuunnitelman', hint: 'Ammattilainen → Työjono → Hyväksy suunnitelma', done: approved },
    { title: 'Viikko 1: agentti kysyy, miten askel sujui – askel pienenee', hint: askHint('Simuloi seuraava viikko → ”Ei tällä kertaa” → ”Aika tai kiire” → ”Sopii”'), done: week1 },
    { title: 'Kotimittausten taso nousee – agentti ottaa itse yhteyttä', hint: 'Lisää uusi mittaus × 2', done: offered },
    { title: 'Kolmen päivän kotiseuranta – yhteenveto ja suunta', hint: monitorHint, done: monitored },
    { title: 'Viikko 2: omahoito ei riitä – automaattinen arvio (kiireetön) ja ohjaus hoitajalle', hint: askHint('Simuloi seuraava viikko → vastaa taas ”Ei tällä kertaa”'), done: escalated },
    { title: 'Hoitaja vahvistaa arvion ja päivittää suunnitelman (versio 2)', hint: 'Ammattilainen → Eskaloidut → Muokkaa suunnitelmaa', done: updated },
    { title: 'Viikko 3: omahoito jatkuu uudella suunnitelmalla', hint: askHint('Simuloi seuraava viikko'), done: continued },
  ];
}

/** Demo controls: make the agent's initiative visible without a real background scheduler. */
export default function DemoPanel({ dashboard, setDashboard }: Props) {
  const [open, setOpen] = useState(true);
  const [freeText, setFreeText] = useState('');
  const { busy, error, message, run } = useRunner(setDashboard);
  const demo = dashboard.support.demo;
  const steps = demoSteps(dashboard);
  const currentIndex = steps.findIndex((step) => !step.done);

  // after "Tyhjennä tiedot" there is no synthetic client left: offer only the way back to the demo
  if (!dashboard.support.available || !demo) {
    return (
      <section className="panel demo-controls support-demo" aria-labelledby="support-demo-title">
        <div className="demo-controls-head">
          <h2 id="support-demo-title">Demo-ohjaus</h2>
        </div>
        <p className="muted small">Tiedot on tyhjennetty. Palauta demo alkutilaan, niin synteettinen asiakas, seurannat ja agentin toiminta palaavat.</p>
        <button type="button" disabled={busy} onClick={() => run(() => loopApi.reset(), () => 'Demo palautettu alkutilaan.')}>
          Palauta demo alkutilaan
        </button>
        <p className="live-message demo-live" aria-live="polite">{message}</p>
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>
    );
  }

  return (
    <section className="panel demo-controls support-demo" aria-labelledby="support-demo-title">
      <div className="demo-controls-head">
        <h2 id="support-demo-title">Demo-ohjaus</h2>
        <button type="button" className="btn-secondary" aria-expanded={open} aria-controls="support-demo-body" onClick={() => setOpen(!open)}>
          {open ? 'Piilota' : 'Näytä'}
        </button>
      </div>
      {open && (
        <div id="support-demo-body">
          <p className="demo-date">Demon päivämäärä: <strong>{formatDate(dashboard.currentDate)}</strong></p>
          <p className="muted small">Painikkeet korvaavat taustaprosessin, joka oikeasti ajaisi agentin. Kaikki tiedot ovat synteettisiä.</p>

          {steps.length > 0 && (
            <ol className="demo-steps" aria-label="Demon kulku">
              {steps.map((step, index) => (
                <li key={step.title} className={step.done ? 'is-done' : index === currentIndex ? 'is-current' : ''} aria-current={index === currentIndex ? 'step' : undefined}>
                  <span className="demo-step-mark" aria-hidden="true">{step.done ? <CheckIcon size={14} /> : index + 1}</span>
                  <span>
                    {step.title}
                    {index === currentIndex && <small className="demo-step-hint">{step.hint}</small>}
                  </span>
                </li>
              ))}
            </ol>
          )}

          <div className="demo-buttons">
            <button type="button" disabled={busy} onClick={() => run(() => supportApi.runCycle(), (r) => describeCycle(r.result))}>
              Käynnistä agenttikierros
            </button>
            <button type="button" disabled={busy} onClick={() => run(() => supportApi.simulateWeek(), (r) => `Aikaa siirrettiin 7 päivää. ${describeCycle((r.result as { cycle?: CycleResult }).cycle)}`)}>
              Simuloi seuraava viikko
            </button>
            <button type="button" disabled={busy} onClick={() => run(() => supportApi.simulateMeasurement(), () => `Kotimittaus kirjattiin. Agentti havainnoi tiedon.`)}>
              Lisää uusi mittaus{demo.nextMeasurement ? ` (${demo.nextMeasurement})` : ''}
            </button>
            <button type="button" disabled={busy || !demo.openQuestion} onClick={() => run(() => supportApi.simulateUserResponse(), () => 'Käyttäjän vastaus simuloitiin.')}>
              Simuloi käyttäjän vastaus
            </button>
            <button type="button" disabled={busy || !demo.homeMonitoringActive}
              onClick={() => run(() => supportApi.simulateHomeMonitoring(), (r) => `Kotiseurannan mittaukset kirjattiin (${r.result.readings.join(', ')}). Agentti teki yhteenvedon.`)}>
              Simuloi kotiseuranta (3 pv)
            </button>
            <button type="button" disabled={busy || !demo.pendingProfessional} onClick={() => run(() => supportApi.simulateProfessionalDecision(), () => 'Ammattilaisen päätös simuloitiin.')}>
              Simuloi ammattilaisen päätös
            </button>
          </div>
          <details className="demo-more">
            <summary>Muut demotapahtumat</summary>
            <div className="demo-buttons">
              {dashboard.demoTemplates.map((template) => (
                <button key={template.key} type="button" className="btn-secondary" disabled={busy}
                  onClick={() => run(() => loopApi.addDemoEvent(template.key), (r) => (r.userVisibleAlert ? 'Sääntömoottori muodosti uuden huomion.' : 'Tapahtuma kirjattiin.'))}>
                  {template.label}
                </button>
              ))}
              <button type="button" className="btn-secondary" disabled={busy} title={demo.symptomReport ?? undefined}
                onClick={() => run(() => supportApi.simulateSymptomReport(), () => 'Oirekuvaus lähetettiin; automaattinen arvio tehtiin.')}>
                Simuloi oirekuvaus chatissa
              </button>
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => run(() => loopApi.advanceTime(30), () => 'Aikaa siirrettiin 30 päivää.')}>
                Siirrä aikaa 30 päivää
              </button>
            </div>
            <form
              className="free-text-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (freeText.trim()) {
                  run(() => loopApi.addFreeText(freeText), (r) => (r.userVisibleAlert ? 'Sääntömoottori muodosti uuden huomion.' : 'Teksti kirjattiin tapahtumaksi.'));
                  setFreeText('');
                }
              }}
            >
              <label htmlFor="support-free-text">Vapaamuotoinen synteettinen terveysteksti</label>
              <textarea id="support-free-text" rows={2} value={freeText} onChange={(e) => setFreeText(e.target.value)} placeholder="Esim. Labra: LDL 4,6 mmol/l" />
              <small>
                Muutetaan rakenteiseksi {dashboard.llm.enabled ? 'tekoälyllä (sääntöpohjainen jäsennin varalla)' : 'sääntöpohjaisella jäsentimellä'}. Poikkeamamerkintä lasketaan aina säännöllä.
              </small>
              <button type="submit" className="btn-secondary" disabled={busy || !freeText.trim()}>Lisää teksti tapahtumaksi</button>
            </form>
          </details>
          <button type="button" className="btn-secondary demo-reset" disabled={busy} onClick={() => run(() => loopApi.reset(), () => 'Demo palautettu alkutilaan.')}>
            Palauta demo alkutilaan
          </button>
          <p className="live-message demo-live" aria-live="polite">{message}</p>
          {error && <p className="form-error" role="alert">{error}</p>}
        </div>
      )}
    </section>
  );
}
