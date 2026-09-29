import { useEffect, useMemo, useRef, useState } from 'react';
import { StethoscopeIcon } from '../../icons';
import { formatDate } from '../../loop/labels';
import type { LoopDashboard } from '../../loop/types';
import { supportApi } from '../api';
import { CategoryBadge, escalationTone, PLAN_TONES, ToneBadge, UrgencyBadge } from '../labels';
import type { AssessmentReviewRequest, CareAssessment, SupportPlan } from '../types';
import { useRunner } from '../useRunner';
import AdapterPreview from './AdapterPreview';
import AssessmentReview from './AssessmentReview';
import CohortTable from './CohortTable';
import InsightReview from './InsightReview';
import PlanDetail from './PlanDetail';

interface Props {
  dashboard: LoopDashboard;
  setDashboard: (dashboard: LoopDashboard) => void;
}

type Selection = { kind: 'plan'; id: string } | { kind: 'assessment'; id: string } | { kind: 'insights' } | { kind: 'filtered' } | { kind: 'shared' } | { kind: 'cohort' };

/** Gate 2: the professional reviews proposals and escalations; decisions flow back into the plan. */
export default function ProfessionalView(props: Props) {
  // after "Tyhjennä tiedot" the support payload is only {available: false}: check before any hook reads its fields
  if (!props.dashboard.support.available) {
    return <section className="panel"><h2>Ammattilaisen työjono</h2><p>Seurannan tietoja ei ole ladattu.</p></section>;
  }
  return <ProfessionalQueue {...props} />;
}

function ProfessionalQueue({ dashboard, setDashboard }: Props) {
  const support = dashboard.support;
  const q = support.professional;
  // tolerate a backend without the assessment fields (older state/server) instead of crashing the queue
  const assessmentReviewIds = q.assessmentReviewIds ?? [];
  const humanReviewRequestIds = q.humanReviewRequestIds ?? [];
  const allAssessments = support.assessments ?? [];
  const [role, setRole] = useState('nurse');
  const [selection, setSelection] = useState<Selection | null>(null);
  const manual = useRef(false); // once the professional picks something, the queue no longer moves the selection
  const { busy, error, message, run } = useRunner(setDashboard);

  function pick(next: Selection) {
    manual.current = true;
    setSelection(next);
  }

  const plansById = useMemo(() => Object.fromEntries(support.plans.map((p) => [p.id, p])), [support.plans]);
  const escalationPlanIds = useMemo(
    () => q.escalationIds.map((id) => support.escalations.find((e) => e.id === id)?.planId).filter(Boolean) as string[],
    [q.escalationIds, support.escalations],
  );
  const firstPending = escalationPlanIds[0] ?? q.pendingPlanIds[0] ?? q.reviewDuePlanIds[0] ?? q.activePlanIds[0];
  const firstAssessment = assessmentReviewIds[0];

  // follow the queue (escalations first, then the oversight of automated assessments) until the professional picks an item
  useEffect(() => {
    if (manual.current) return;
    if (firstPending) {
      if (selection?.kind === 'plan' && selection.id === firstPending) return;
      setSelection({ kind: 'plan', id: firstPending });
    } else if (firstAssessment) {
      if (selection?.kind === 'assessment' && selection.id === firstAssessment) return;
      setSelection({ kind: 'assessment', id: firstAssessment });
    }
  }, [selection, firstPending, firstAssessment]);

  const groups: { title: string; ids: string[]; hint?: string }[] = [
    { title: 'Eskaloidut', ids: escalationPlanIds, hint: 'Agentti on koonnut strukturoidun yhteenvedon.' },
    { title: 'Odottaa hyväksyntää', ids: q.pendingPlanIds },
    { title: 'Arviointipäivä lähestyy', ids: q.reviewDuePlanIds.filter((id) => !escalationPlanIds.includes(id)) },
    { title: 'Aktiiviset seurannat', ids: q.activePlanIds.filter((id) => !escalationPlanIds.includes(id) && !q.reviewDuePlanIds.includes(id)) },
    { title: 'Päättyneet ja hylätyt', ids: q.closedPlanIds },
  ];
  const selectedPlan: SupportPlan | undefined = selection?.kind === 'plan' ? plansById[selection.id] : undefined;
  const insightsById = Object.fromEntries(support.insights.map((i) => [i.id, i]));
  const assessmentsById: Record<string, CareAssessment> = Object.fromEntries(allAssessments.map((a) => [a.id, a]));
  const selectedAssessment = selection?.kind === 'assessment' ? assessmentsById[selection.id] : undefined;
  const automation = support.policy.automation;
  const reviewAssessment = (assessmentId: string, body: AssessmentReviewRequest) =>
    run(() => supportApi.reviewAssessment(assessmentId, body),
      () => `Arvio käsitelty: ${q.assessmentDecisionLabels[body.decision]}. Asiakas sai tiedon, ja päätös kirjattiin lokiin.`);

  function assessmentItem(assessment: CareAssessment) {
    const selected = selection?.kind === 'assessment' && selection.id === assessment.id;
    const requested = humanReviewRequestIds.includes(assessment.id);
    const source = assessment.planId ? plansById[assessment.planId]?.name ?? 'Seuranta' : 'Oirekuvaus chatissa';
    return (
      <li key={assessment.id}>
        <button type="button" className={`queue-item ${selected ? 'is-selected' : ''}`} aria-current={selected ? 'true' : undefined}
          onClick={() => pick({ kind: 'assessment', id: assessment.id })}>
          <span className="queue-item-title">Automaattinen arvio · {formatDate(assessment.createdAt)}</span>
          <span className="muted small">{support.person.name} · {source}</span>
          <UrgencyBadge urgency={assessment.urgency} label={assessment.urgencyLabel} />
          {requested && <span className="chip chip-attention">Asiakas pyysi ammattilaisen arvion</span>}
          {assessment.mode === 'professional_required' && <span className="chip">Esiarvio</span>}
        </button>
      </li>
    );
  }

  function item(plan: SupportPlan) {
    const escalation = support.escalations.find((e) => e.planId === plan.id && e.status === 'open');
    const selected = selection?.kind === 'plan' && selection.id === plan.id;
    return (
      <li key={plan.id}>
        <button type="button" className={`queue-item ${selected ? 'is-selected' : ''}`} aria-current={selected ? 'true' : undefined}
          onClick={() => pick({ kind: 'plan', id: plan.id })}>
          <span className="queue-item-title">{plan.name}</span>
          <span className="muted small">{support.person.name} · v{plan.version} · {plan.owner.label}</span>
          {escalation
            ? <ToneBadge tone={escalationTone(escalation.urgency)}>{escalation.urgencyLabel}</ToneBadge>
            : <ToneBadge tone={PLAN_TONES[plan.status]}>{plan.statusLabel}</ToneBadge>}
        </button>
      </li>
    );
  }

  return (
    <div className="professional-layout">
      <aside className="panel queue-panel" aria-labelledby="queue-title">
        <div className="panel-heading">
          <span className="panel-heading-icon" aria-hidden="true"><StethoscopeIcon size={40} /></span>
          <h2 id="queue-title">Työjono</h2>
        </div>
        <label className="role-select">
          Toimit roolissa
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {Object.entries(q.ownerRoles).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
        <p className="muted small">Yksi synteettinen asiakas. Agentti tekee hoidon tarpeen arviot automaattisesti; ammattilainen valvoo arviot ja päättää hoidosta.</p>
        {groups.slice(0, 1).map((group) => group.ids.length > 0 && (
          <div key={group.title} className="queue-group">
            <h3>{group.title} <span className="queue-count">{group.ids.length}</span></h3>
            <ul className="queue-list">{group.ids.map((id) => plansById[id] && item(plansById[id]))}</ul>
          </div>
        ))}
        {assessmentReviewIds.length > 0 && (
          <div className="queue-group">
            <h3>Automaattiset arviot (valvonta) <span className="queue-count">{assessmentReviewIds.length}</span></h3>
            <ul className="queue-list">{assessmentReviewIds.map((id) => assessmentsById[id] && assessmentItem(assessmentsById[id]))}</ul>
          </div>
        )}
        {groups.slice(1).map((group) => group.ids.length > 0 && (
          <div key={group.title} className="queue-group">
            <h3>{group.title} <span className="queue-count">{group.ids.length}</span></h3>
            <ul className="queue-list">{group.ids.map((id) => plansById[id] && item(plansById[id]))}</ul>
          </div>
        ))}
        <div className="queue-group">
          <h3>Muut</h3>
          <ul className="queue-list">
            <li><button type="button" className={`queue-item ${selection?.kind === 'insights' ? 'is-selected' : ''}`} onClick={() => pick({ kind: 'insights' })}>
              <span className="queue-item-title">Perimätiedon arviopyynnöt</span><span className="queue-count">{q.insightReviewIds.length}</span></button></li>
            <li><button type="button" className={`queue-item ${selection?.kind === 'shared' ? 'is-selected' : ''}`} onClick={() => pick({ kind: 'shared' })}>
              <span className="queue-item-title">Asiakkaan jakamat yhteenvedot</span><span className="queue-count">{q.sharedObservationIds.length}</span></button></li>
            <li><button type="button" className={`queue-item ${selection?.kind === 'filtered' ? 'is-selected' : ''}`} onClick={() => pick({ kind: 'filtered' })}>
              <span className="queue-item-title">Portti 1: suodatetut havainnot</span><span className="queue-count">{q.filteredInsightIds.length}</span></button></li>
            <li><button type="button" className={`queue-item ${selection?.kind === 'cohort' ? 'is-selected' : ''}`} onClick={() => pick({ kind: 'cohort' })}>
              <span className="queue-item-title">Asiakaslista (synteettinen kohortti)</span></button></li>
          </ul>
        </div>
      </aside>

      <div className="professional-main">
        <p className="live-message" aria-live="polite">{message}</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        {selectedPlan && (
          <section className="panel">
            <PlanDetail
              plan={selectedPlan}
              escalations={support.escalations.filter((e) => e.planId === selectedPlan.id)}
              insights={support.insights}
              role={role}
              labels={q.decisionLabels}
              busy={busy}
              currentDate={dashboard.currentDate}
              personName={support.person.name}
              onDecide={(body) => run(() => supportApi.decide(selectedPlan.id, body), () => `Päätös tallennettu: ${q.decisionLabels[body.decision]}. Suunnitelma päivittyi ja asiakas sai tiedon.`)}
              assessments={allAssessments}
              urgencyClasses={automation?.urgencyClasses ?? []}
              assessmentLabels={q.assessmentDecisionLabels}
              assessmentQuestion={q.assessmentQuestion}
              onReviewAssessment={reviewAssessment}
            />
          </section>
        )}
        {selection?.kind === 'assessment' && (
          <section className="panel" aria-labelledby="oversight-title">
            <h2 id="oversight-title">Automaattiset arviot (valvonta)</h2>
            <p className="muted small">
              Sääntömoottori teki arvion automaattisesti. Vahvista arvio, muuta kiireellisyysluokkaa tai tee arvio itse. Hoitopäätökset tekee ammattilainen.
            </p>
            {selectedAssessment ? (
              <AssessmentReview
                assessment={selectedAssessment}
                urgencyClasses={automation?.urgencyClasses ?? []}
                labels={q.assessmentDecisionLabels}
                role={role}
                busy={busy}
                onReview={(body) => reviewAssessment(selectedAssessment.id, body)}
                planName={selectedAssessment.planId ? plansById[selectedAssessment.planId]?.name : undefined}
                onOpenPlan={(planId) => pick({ kind: 'plan', id: planId })}
              />
            ) : <p>Arviota ei löytynyt.</p>}
          </section>
        )}
        {selection?.kind === 'insights' && (
          <section className="panel" aria-labelledby="insight-reviews-title">
            <h2 id="insight-reviews-title">Perimätiedon arviopyynnöt</h2>
            <p className="muted small">Hyväksytty havainto on vahvistamaton taustatieto, kunnes kliininen vahvistus on tehty.</p>
            {q.insightReviewIds.length === 0 && <p>Ei avoimia arviopyyntöjä.</p>}
            {q.insightReviewIds.map((id) => insightsById[id] && (
              <InsightReview key={id} insight={insightsById[id]} role={role} ownerRoles={q.ownerRoles} busy={busy}
                onDecide={(body) => run(() => supportApi.decideInsight(id, body), () => 'Päätös tallennettu.')} />
            ))}
          </section>
        )}
        {selection?.kind === 'shared' && (
          <section className="panel">
            <h2>Asiakkaan jakamat yhteenvedot</h2>
            <p className="muted small">Asiakkaan itse jakamat huomiot. Käsitellään vastaanotolla.</p>
            {q.sharedObservationIds.length === 0 && <p>Ei jaettuja yhteenvetoja.</p>}
            <ul className="plain-list">
              {dashboard.observations.filter((o) => q.sharedObservationIds.includes(o.id)).map((o) => (
                <li key={o.id}><strong>{o.title}</strong> – jaettu {formatDate(o.sharedAt)}. {o.connection}</li>
              ))}
            </ul>
          </section>
        )}
        {selection?.kind === 'filtered' && (
          <section className="panel" aria-labelledby="filtered-title">
            <h2 id="filtered-title">Portti 1: suodatetut havainnot</h2>
            <p>Eivät näy asiakkaalle eivätkä vaikuta ohjaukseen. Ammattilainen näkee ne läpinäkyvyyden vuoksi.</p>
            <ul className="plain-list">
              {q.filteredInsightIds.map((id) => insightsById[id] && (
                <li key={id} className="filtered-item">
                  <CategoryBadge category={insightsById[id].category} label={insightsById[id].categoryLabel} />{' '}
                  <strong>{insightsById[id].title}</strong>: {insightsById[id].reason}
                </li>
              ))}
            </ul>
          </section>
        )}
        {selection?.kind === 'cohort' && <CohortTable />}
        <AdapterPreview />
      </div>
    </div>
  );
}
