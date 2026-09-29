import { useState } from 'react';
import { ArrowRightIcon, CalendarIcon, ChatIcon, ClipboardIcon, DocumentIcon, HeartHandIcon, SirenIcon } from '../icons';
import { loopApi } from '../loop/api';
import FollowUpQuestion from '../loop/FollowUpQuestion';
import { formatDate, StatusBadge } from '../loop/labels';
import ProfessionalSummary from '../loop/ProfessionalSummary';
import type { AgentState, LoopDashboard, UserResponse } from '../loop/types';
import WhyNowView from '../loop/WhyNowView';
import { supportApi } from './api';
import AssessmentCard, { humanReviewRequestedText } from './AssessmentCard';
import CheckInCard from './CheckInCard';
import { DirectionBadge } from './ContinuityPanel';
import DemoPanel from './DemoPanel';
import MeasurementForm from './MeasurementForm';
import PlanCard from './PlanCard';
import { useRunner } from './useRunner';

export type NavigateTarget = 'companion' | 'audit' | 'quiz' | 'summary' | 'consent' | 'timeline';

interface Props {
  dashboard: LoopDashboard;
  setDashboard: (dashboard: LoopDashboard) => void;
  onNavigate: (view: NavigateTarget) => void;
}

type SubView = { kind: 'home' } | { kind: 'whyNow'; id: string } | { kind: 'summary'; id: string };

/** "Tilanne nyt": the situation and the next step first; reasons are one click away, never a risk list. */
export default function SituationView({ dashboard, setDashboard, onNavigate }: Props) {
  const [view, setView] = useState<SubView>({ kind: 'home' });
  const { busy, error, message, run } = useRunner(setDashboard);
  const support = dashboard.support;

  if (!support.available) {
    return (
      <section className="panel">
        <h2>Tilanne nyt</h2>
        <p>Seurannan tietoja ei ole ladattu. Jos poistit kaikki tiedot, voit palauttaa synteettisen demotapauksen.</p>
        <button type="button" disabled={busy} onClick={() => run(() => loopApi.reset(), () => 'Demo palautettu alkutilaan.')}>Palauta demo alkutilaan</button>
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>
    );
  }
  if (view.kind === 'whyNow') {
    const observation = dashboard.observations.find((o) => o.id === view.id);
    if (observation) {
      return <WhyNowView observation={observation} onBack={() => setView({ kind: 'home' })} onSummary={(id) => setView({ kind: 'summary', id })} />;
    }
  }
  if (view.kind === 'summary') {
    return <ProfessionalSummary observationId={view.id} onBack={() => setView({ kind: 'whyNow', id: view.id })} onShared={setDashboard} />;
  }

  const situation = support.situation;
  const continuity = support.continuity;
  const openCheckIn = support.openCheckIns[0];
  const planName = (id: string) => support.plans.find((p) => p.id === id)?.name ?? 'Seuranta';
  const safetyMessage = situation.safetyEscalationId
    ? [...dashboard.companion.messages].reverse().find((m) => m.kind === 'safety_threshold')
    : undefined;
  const step = situation.nextStep;

  return (
    <div className="loop-layout">
      <div className="loop-main">
        <section className={`panel situation-panel situation-tone-${situation.tone}`} aria-labelledby="situation-title">
          <div className="panel-heading">
            <span className="panel-heading-icon" aria-hidden="true"><HeartHandIcon size={48} /></span>
            <h2 id="situation-title">Tilanne nyt</h2>
          </div>
          <p className="situation-headline" aria-live="polite">{situation.headline}</p>
          <p className="muted small">
            {support.person.name}, {support.person.age} v · {formatDate(dashboard.currentDate)}
          </p>

          <div className="next-step" role="region" aria-labelledby="next-step-title">
            <h3 id="next-step-title">Seuraava askel</h3>
            <p className="next-step-title">{step.title}</p>
            <p className="next-step-detail">{step.detail}</p>
            {step.kind === 'answer_checkin' && <a className="button-link" href="#checkin-anchor">Siirry kysymyksiin <ArrowRightIcon size={16} /></a>}
            {step.kind === 'answer_offer' && step.periodId && (
              <div className="row">
                <button type="button" disabled={busy}
                  onClick={() => run(() => supportApi.respondHomeMonitoring(step.periodId as string, true), () => 'Kotiseuranta aloitettiin.')}>
                  Kyllä, aloitetaan
                </button>
                <button type="button" className="btn-secondary" disabled={busy}
                  onClick={() => run(() => supportApi.respondHomeMonitoring(step.periodId as string, false), () => 'Selvä, ei tällä viikolla.')}>
                  Ei tällä viikolla
                </button>
              </div>
            )}
            {(step.kind === 'record_measurement' || step.kind === 'wait') && (
              <MeasurementForm busy={busy} compact onSubmit={(s, d) => run(() => supportApi.addMeasurement(s, d), () => `Kotimittaus ${s}/${d} mmHg tallennettiin.`)} />
            )}
          </div>

          <div className="row">
            <button type="button" onClick={() => onNavigate('companion')}><ChatIcon size={18} /> Keskustele Hyvinvointikumppanin kanssa</button>
            <button type="button" className="btn-secondary" onClick={() => onNavigate('audit')}>Mitä agentti on tehnyt?</button>
          </div>
          <p className="live-message" aria-live="polite">{message}</p>
          {error && <p className="form-error" role="alert">{error}</p>}
        </section>

        {continuity?.available && (
          <section className="panel" aria-labelledby="continuity-summary-title">
            <h2 id="continuity-summary-title">Omahoidon jatkuvuus</h2>
            <p className="muted small">{continuity.tagline}</p>
            <div className="continuity-summary-grid">
              <div>
                <h3>Riittääkö omahoito?</h3>
                {continuity.direction ? (
                  <>
                    <DirectionBadge direction={continuity.direction} />
                    <p className="small"><strong>{continuity.direction.planName}:</strong> {continuity.direction.reasons.join(' ')}</p>
                  </>
                ) : <p className="small">Ei seurantoja.</p>}
              </div>
              <div>
                <h3>Tämän viikon askel</h3>
                {continuity.step ? (
                  <>
                    <p className="step-now">{continuity.step.text.charAt(0).toUpperCase() + continuity.step.text.slice(1)}</p>
                    <p className="muted small">
                      {continuity.step.stage === 'feedback' ? 'Viikkotarkistus odottaa vastaustasi: miten askel sujui?'
                        : continuity.step.feedbackAt ? `Kysyn ${formatDate(continuity.step.feedbackAt)}, miten meni.` : continuity.step.setByLabel}
                    </p>
                  </>
                ) : <p className="small">Askel sovitaan, kun ammattilainen on hyväksynyt seurantasuunnitelman.</p>}
              </div>
            </div>
            <button type="button" className="btn-secondary" onClick={() => onNavigate('companion')}>
              <ChatIcon size={18} /> Muisti, yhteydenotot ja askeleet Hyvinvointikumppanissa
            </button>
          </section>
        )}

        {situation.assessment && support.policy.automation && (
          <AssessmentCard
            assessment={situation.assessment}
            automation={support.policy.automation}
            requestedText={humanReviewRequestedText(situation.assessment, support.plans, support.escalations, support.policy.automation)}
            busy={busy}
            onRequestHuman={(id) => run(() => supportApi.requestHumanReview(id), () => 'Ammattilaisen arvio pyydetty. Vahvistus näkyy myös keskustelussa.')}
          />
        )}

        {safetyMessage && (
          <section className="panel safety-panel" role="alert" aria-labelledby="safety-title">
            <h2 id="safety-title"><SirenIcon size={24} /> Toimi näin</h2>
            <p>{safetyMessage.text}</p>
          </section>
        )}

        {openCheckIn && (
          <div id="checkin-anchor">
            <CheckInCard
              checkIn={openCheckIn}
              planName={planName(openCheckIn.planId)}
              busy={busy}
              onAnswer={(questionId, optionId, skip) => run(() => supportApi.answer(openCheckIn.id, questionId, optionId, skip))}
            />
          </div>
        )}

        {dashboard.pendingQuestions.map((question) => (
          <FollowUpQuestion
            key={question.id}
            question={question}
            busy={busy}
            onRespond={(taskId: string, response: UserResponse) => run(() => loopApi.respond(taskId, response), () => 'Vastaus tallennettu.')}
          />
        ))}

        {situation.legacyObservations.map((observation) => (
          <section key={observation.id} className="panel observation-alert" aria-labelledby={`obs-${observation.id}`}>
            <StatusBadge status={observation.status as AgentState} />
            <h2 id={`obs-${observation.id}`}>{observation.title}</h2>
            <p>{observation.explanation}</p>
            <div className="row">
              <button type="button" onClick={() => setView({ kind: 'whyNow', id: observation.id })}>Miksi nyt?</button>
              {observation.status !== 'additional_information_needed' && (
                <button type="button" className="btn-secondary" onClick={() => setView({ kind: 'summary', id: observation.id })}>Yhteenveto ammattilaiselle</button>
              )}
            </div>
          </section>
        ))}

        <section className="panel" aria-labelledby="themes-title">
          <h2 id="themes-title">Seurantateemat</h2>
          <div className="plan-list">
            {situation.plans.length ? situation.plans.map((card) => (
              <PlanCard
                key={card.id}
                card={card}
                busy={busy}
                onPause={(id) => run(() => supportApi.pausePlan(id), () => 'Seuranta tauotettu.')}
                onResume={(id) => run(() => supportApi.resumePlan(id), () => 'Seuranta jatkuu.')}
              />
            )) : <p>Ei seurantateemoja.</p>}
          </div>
        </section>

        <section className="panel progress-panel" aria-labelledby="progress-title">
          <h2 id="progress-title">Viimeisin edistyminen</h2>
          {situation.latestProgress.length ? (
            <ul className="plain-list">{situation.latestProgress.map((line, i) => <li key={`${i}-${line}`}>{line}</li>)}</ul>
          ) : <p>Ei vielä kirjattua edistymistä.</p>}
          <p className="next-check"><CalendarIcon size={20} /> Seuraava tarkistus: <strong>{formatDate(situation.nextCheck)}</strong></p>
        </section>

        <section className="panel optional-tools" aria-labelledby="optional-title">
          <h2 id="optional-title">Lisää</h2>
          <div className="row">
            <button type="button" className="btn-secondary" onClick={() => onNavigate('summary')}><DocumentIcon size={18} /> Yhteenveto vastaanotolle</button>
            <button type="button" className="btn-secondary" onClick={() => onNavigate('quiz')}><ClipboardIcon size={18} /> Laaja elämäntapakysely (valinnainen)</button>
            <button type="button" className="btn-secondary" onClick={() => onNavigate('consent')}>Suostumukset</button>
          </div>
        </section>
      </div>

      <aside className="loop-side" aria-label="Demon ohjaus">
        <DemoPanel dashboard={dashboard} setDashboard={setDashboard} />
      </aside>
    </div>
  );
}
