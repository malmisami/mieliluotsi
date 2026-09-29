import { formatDate } from '../../loop/labels';
import { CategoryBadge, escalationTone, PLAN_TONES, ToneBadge } from '../labels';
import type {
  AssessmentDecision, AssessmentReviewRequest, CareAssessment, DecisionRequest, Escalation, Insight, SupportPlan, UrgencyClass,
} from '../types';
import AssessmentReview from './AssessmentReview';
import DecisionPanel from './DecisionPanel';
import EscalationSummary from './EscalationSummary';

const PRIORITY_LABELS: Record<string, string> = { low: 'matala', normal: 'tavallinen', high: 'korkea' };
const ACTOR_NAMES: Record<string, string> = { system: 'Järjestelmä', agent: 'Hyvinvointikumppani', user: 'Asiakas', professional: 'Ammattilainen' };

interface Props {
  plan: SupportPlan;
  escalations: Escalation[];
  insights: Insight[];
  role: string;
  labels: Record<string, string>;
  busy: boolean;
  currentDate: string;
  personName: string;
  onDecide: (body: DecisionRequest) => void;
  /** Automated care-need assessments (all of them; the ones linked to this plan's escalations are embedded). */
  assessments: CareAssessment[];
  urgencyClasses: UrgencyClass[];
  assessmentLabels: Record<AssessmentDecision, string>;
  assessmentQuestion: string;
  onReviewAssessment: (assessmentId: string, body: AssessmentReviewRequest) => void;
}

/** The professional's plan page: what needs a decision first, the plan in six facts, the decision, then the details. */
export default function PlanDetail({
  plan, escalations, insights, role, labels, busy, currentDate, personName, onDecide,
  assessments, urgencyClasses, assessmentLabels, assessmentQuestion, onReviewAssessment,
}: Props) {
  const open = escalations.find((e) => e.status === 'open') ?? null;
  const resolved = escalations.filter((e) => e.status === 'resolved');
  const related = insights.filter((i) => i.linkedPlanId === plan.id);
  const pending = plan.status === 'pending_professional_review';
  // with an open escalation the decision needed is shown in the escalation itself
  const needed = open ? null
    : pending ? 'Hyväksy, muokkaa tai hylkää järjestelmän ehdottama seurantasuunnitelma.'
    : plan.nextReviewAt && plan.nextReviewAt <= currentDate ? 'Suunnitelman arviointipäivä on käsillä.' : null;
  const events = plan.agentActions.length + plan.checkIns.length;
  const reviewFor = (escalation: Escalation) => {
    const assessment = escalation.assessmentId ? assessments.find((a) => a.id === escalation.assessmentId) : undefined;
    return assessment ? (
      <AssessmentReview assessment={assessment} urgencyClasses={urgencyClasses} labels={assessmentLabels} role={role} busy={busy}
        onReview={(body) => onReviewAssessment(assessment.id, body)} />
    ) : undefined;
  };

  return (
    <article className="plan-detail" aria-labelledby={`detail-${plan.id}`}>
      <header className="plan-detail-head">
        <div>
          <h2 id={`detail-${plan.id}`}>{plan.name}</h2>
          <p className="muted">{personName} · versio {plan.version} · vastuu: {plan.owner.label} · prioriteetti: {PRIORITY_LABELS[plan.priority]}</p>
        </div>
        <ToneBadge tone={open ? escalationTone(open.urgency) : PLAN_TONES[plan.status]}>{plan.statusLabel}</ToneBadge>
      </header>
      {needed && <p className="decision-needed"><strong>Päätöstä tarvitaan:</strong> {needed}</p>}

      {open && <EscalationSummary escalation={open} assessmentReview={reviewFor(open)} />}

      <section>
        <h3>Suunnitelma lyhyesti</h3>
        <dl className="fact-list plan-summary-grid">
          <div><dt>Seurannan tavoite</dt><dd>{plan.objective}</dd></div>
          <div><dt>Omahoidon tavoite</dt><dd>{plan.goal ? `${plan.goal.label}${plan.goal.setBy === 'agent_with_user' ? ' (agentti sovitti asiakkaan kanssa)' : ''}` : '–'}</dd></div>
          <div><dt>Kotimittaukset</dt><dd>{plan.measurementsPerWeek ? `${plan.measurementsPerWeek} tarkistusvälillä` : '–'}</dd></div>
          <div><dt>Tarkistusväli</dt><dd>{plan.checkInEveryDays} pv{plan.nextCheckInAt ? ` · seuraava ${formatDate(plan.nextCheckInAt)}` : ''}</dd></div>
          <div><dt>Tavoitetaso (demo)</dt><dd>{plan.demoTarget ? plan.demoTarget.label : '–'}</dd></div>
          <div><dt>Suunnitelman arviointi</dt><dd>{formatDate(plan.nextReviewAt)}</dd></div>
          {plan.professionalInstructions.length > 0 && (
            <div className="span-2"><dt>Ohjeet asiakkaalle</dt><dd><ul>{plan.professionalInstructions.map((line) => <li key={line}>{line}</li>)}</ul></dd></div>
          )}
          {plan.currentSignals.length > 0 && (
            <div className="span-2"><dt>Nyt havaitut signaalit</dt><dd>{plan.currentSignals.map((s) => s.label).join(', ')}</dd></div>
          )}
        </dl>
      </section>

      <DecisionPanel plan={plan} escalation={open} role={role} labels={labels} busy={busy} currentDate={currentDate}
        appropriateQuestion={assessmentQuestion} onDecide={onDecide} />

      <details className="plan-section" open={pending}>
        <summary>Mistä ehdotus muodostui</summary>
        <p>{plan.rationale}</p>
        <ul className="source-list">
          {plan.sourceDetails.map((source) => (
            <li key={`${source.kind}-${source.id}`}>
              <span>{source.label}</span>
              <span className="muted small">{source.kindLabel}{source.date ? ` · ${formatDate(source.date)}` : ''}</span>
              {!source.inUse && <span className="chip">Asiakas ei salli käyttöä</span>}
            </li>
          ))}
        </ul>
        {related.map((insight) => (
          <p key={insight.id} className="small">
            <CategoryBadge category={insight.category} label={insight.categoryLabel} /> {insight.title}: {insight.reason}
          </p>
        ))}
        <p className="muted small">Asiakkaan suostumus: {plan.userConsent.given ? `annettu ${formatDate(plan.userConsent.at)} (${plan.userConsent.how})` : 'ei annettu'}.</p>
      </details>

      <details className="plan-section">
        <summary>Signaalit, agentin valtuudet ja kiireellisyyssäännöt</summary>
        <dl className="fact-list two-col">
          <div><dt>Seurattavat signaalit</dt><dd><ul>{plan.signals.map((s) => <li key={s.id}>{s.label}</li>)}</ul></dd></div>
          <div>
            <dt>Kiireellisyys- ja ohjaussäännöt</dt>
            <dd><ul>{plan.escalationRules.map((r) => <li key={r.id}><code>{r.id}</code> {r.name} – {r.urgencyLabel.toLowerCase()} ({r.handlingTime})</li>)}</ul></dd>
          </div>
          <div><dt>Agentti saa</dt><dd><ul>{plan.allowedActions.map((a) => <li key={a}>{plan.allowedActionLabels[a]}</li>)}</ul></dd></div>
          <div><dt>Agentti ei koskaan</dt><dd><ul>{plan.forbiddenActions.map((a) => <li key={a}>{plan.forbiddenActionLabels[a]}</li>)}</ul></dd></div>
        </dl>
      </details>

      <details className="plan-section">
        <summary>Agentin toimet ja asiakkaan vastaukset ({events})</summary>
        <h4>Mitä agentti on tehnyt</h4>
        {plan.agentActions.length ? (
          <ol className="history-list">{plan.agentActions.map((a) => <li key={a.id}>{formatDate(a.date)} – {a.detail}</li>)}</ol>
        ) : <p className="muted">Ei vielä toimenpiteitä.</p>}
        <h4>Asiakkaan vastaukset</h4>
        {plan.checkIns.length ? plan.checkIns.map((checkIn) => (
          <div key={checkIn.id} className="answers-block">
            <p className="small"><strong>{formatDate(checkIn.createdAt)}</strong> · versio {checkIn.planVersion} · {checkIn.status === 'open' ? 'kesken' : checkIn.status === 'completed' ? 'valmis' : 'ei vastausta'}</p>
            <ul>
              {checkIn.questions.map((q) => <li key={q.id}>{q.text} <strong>{q.skipped ? 'Ohitettu' : q.answerLabel ?? '–'}</strong></li>)}
            </ul>
          </div>
        )) : <p className="muted">Ei vielä vastauksia.</p>}
      </details>

      {resolved.map((escalation) => (
        <details key={escalation.id} className="plan-section">
          <summary>Käsitelty arvio ja ohjaus {formatDate(escalation.createdAt)}</summary>
          <EscalationSummary escalation={escalation} assessmentReview={reviewFor(escalation)} />
        </details>
      ))}

      <details className="plan-section">
        <summary>Versiohistoria ({plan.history.length})</summary>
        <ol className="history-list">
          {plan.history.map((change, i) => (
            <li key={`${change.version}-${i}`}>
              {formatDate(change.date)} · v{change.version} · {change.actorRole ?? ACTOR_NAMES[change.actor]}: {change.summary}
              {change.changes.length > 0 && <ul>{change.changes.map((line) => <li key={line}>{line}</li>)}</ul>}
            </li>
          ))}
        </ol>
      </details>
    </article>
  );
}
