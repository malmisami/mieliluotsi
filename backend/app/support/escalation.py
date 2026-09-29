"""Routing to the responsible professional on the basis of an automated care-need assessment.

Whether and how urgently to route is decided only by the plan's rules (set by a professional): every escalation is
built on a CareAssessment (assessment.create) whose class comes from the rule engine. The optional LLM may draft the
narrative summary from bounded facts and must restate the class verbatim; the structured fields never come from it.
"""
from __future__ import annotations

from typing import Optional

from app.loop import llm
from app.loop.models import LoopState
from app.loop.safety import check_text
from app.loop.store import next_id
from app.loop.templates import fi_date
from app.support import assessment as assessment_module
from app.support import audit, messages, plan_state, policies, signals, texts
from app.support.models import CareAssessment, CheckIn, Escalation, EscalationRule, SourceRef, SupportPlan

OPEN_DECISIONS = {
    'goal_failures_and_above_target': ('Vahvista tai muuta automaattinen kiireellisyysarvio ja päätä jatkosta: vastaanottoaika tai muutos '
                                       'seurantasuunnitelmaan (mittausjakso, tavoite, tarkistusväli).'),
    'safety_threshold': 'Automaattinen arvio: kiireellinen, samana päivänä. Vahvista arvio ja ota yhteyttä asiakkaaseen tänään.',
    'data_missing': 'Vahvista arvio ja päätä, jatketaanko seurantaa nykyisellä suunnitelmalla.',
    'user_request': 'Asiakas käytti oikeuttaan ammattilaisen tekemään arvioon. Tee hoidon tarpeen arvio ja ota yhteyttä.',
    'symptom_report': 'Automaattinen arvio oirekuvauksesta: {label}. Vahvista tai muuta arvio ja ota yhteyttä asiakkaaseen {handling}.',
    'home_monitoring_above': ('Vahvista tai muuta automaattinen kiireellisyysarvio ja päätä jatkosta kotiseurannan tulosten perusteella: '
                              'vastaanottoaika tai muutos seurantasuunnitelmaan.'),
}
OPEN_DECISION_DEFAULT = 'Vahvista tai muuta automaattinen arvio ja päätä jatkosta.'
OPEN_DECISION_NO_CONSENT = 'Asiakas ei ole antanut suostumusta automaattiseen arvioon: tee hoidon tarpeen arvio itse. Esiarvio: {label}.'
LAST_ACTION_LABEL = 'Arvioitu automaattisesti ja ohjattu ammattilaiselle'


def open_escalation(state: LoopState, plan: SupportPlan) -> Optional[Escalation]:
    return next((e for e in state.support.escalations if e.planId == plan.id and e.status == 'open'), None)


def due_rule(state: LoopState, plan: SupportPlan, obs: dict) -> Optional[EscalationRule]:
    """The first plan rule whose condition holds. Safety thresholds are handled separately (they always go through)."""
    if open_escalation(state, plan):
        return None
    metrics, detected = obs['metrics'], obs['detected']
    for rule in plan.escalationRules:
        if rule.kind == 'goal_failures_and_above_target':
            if metrics.get('goalFailuresInRow', 0) >= rule.params.get('goalFailuresInRow', 2) and 'above_target' in detected:
                return rule
        elif rule.kind == 'data_missing':
            last = metrics.get('lastMeasurementDate')
            reminders = [c for c in state.support.contacts if c['planId'] == plan.id and c['kind'] == 'reminder'
                         and (last is None or c['date'] > last)]
            if last and signals.days_between(last, state.currentDate) >= rule.params.get('days', 21) \
                    and len(reminders) >= rule.params.get('minReminders', 2):
                return rule
    return None


def _facts(state: LoopState, plan: SupportPlan, obs: dict, rule: EscalationRule, trigger: str,
           extra: Optional[list[str]] = None, period_metrics: Optional[dict] = None) -> dict:
    metrics = obs['metrics']
    period = period_metrics or metrics
    checkins = sorted(signals.plan_checkins(state, plan), key=lambda c: (c.createdAt, c.id))
    observed: list[str] = list(extra or [])
    failures = metrics.get('goalFailuresInRow', 0)
    if rule.kind == 'goal_failures_and_above_target' and failures:
        dates = [fi_date(c.createdAt) for c in checkins if c.status == 'completed' and c.outcome.get('goal') == 'none'][-failures:]
        observed.append(f"Omahoitotavoite ei ole toteutunut {failures} peräkkäisellä viikkotarkistuksella ({', '.join(dates)}).")
    average = metrics.get('average')
    if average and plan.demoTarget:
        observed.append(
            f"Viimeisimpien kotimittausten keskiarvo {average['systolic']}/{average['diastolic']} mmHg ({average['n']} mittausta, "
            f"{fi_date(average['from'])}–{fi_date(average['to'])}). Suunnitelman tavoitetaso: {plan.demoTarget['label']} "
            f"({plan.demoTarget['setBy']})."
        )
    if metrics.get('trendDelta') is not None:
        observed.append(f"Keskiarvon muutos aiempiin mittauksiin: {metrics['trendDelta']:+d} mmHg (yläpaine).")
    if period.get('measurementCount') is not None and plan.measurementsPerWeek:
        observed.append(f"Kotimittauksia sovitulla jaksolla ({fi_date(period.get('periodStart'))} alkaen): "
                        f"{period['measurementCount']}/{plan.measurementsPerWeek}.")

    timeline = []
    if plan.activatedAt:
        timeline.append({'date': plan.activatedAt, 'text': f'Suunnitelma otettiin käyttöön ({plan.approval.byRole or plan.owner.label} hyväksyi).'})
    since = plan.activatedAt or state.currentDate
    for event, systolic, diastolic in signals.home_readings(state, until=state.currentDate):
        if event.date >= since:
            timeline.append({'date': event.date, 'text': f'Kotimittaus {systolic}/{diastolic} mmHg.'})
    for contact in state.support.contacts:
        if contact['planId'] == plan.id and contact['kind'] in ('reminder', 'review_reminder', 'show_guide'):
            timeline.append({'date': contact['date'], 'text': contact.get('label', 'Muistutus')})
    for checkin in checkins:
        answered = [f"{q.text.split('?')[0].split('. ')[-1]}: {q.answerLabel or 'ohitettu'}" for q in checkin.questions if q.answer or q.skipped]
        timeline.append({'date': checkin.createdAt, 'text': 'Viikkotarkistus – ' + ('; '.join(answered) if answered else 'ei vastauksia')})
    for change in plan.history:
        if change.actor == 'agent':
            timeline.append({'date': change.date, 'text': '; '.join(change.changes) or change.summary})
    for item in state.support.assessments:
        if item.planId == plan.id:
            timeline.append({'date': item.createdAt, 'text': f'Automaattinen hoidon tarpeen arvio: {item.urgencyLabel} ({item.trigger}).'})
    timeline.sort(key=lambda item: item['date'])

    agent_actions = [{'date': a.date, 'text': a.detail} for a in state.support.audit if a.planId == plan.id and a.stage == 'act']
    user_responses = [
        {'date': q.answeredAt, 'question': q.text, 'answer': q.answerLabel or 'ohitettu'}
        for c in checkins for q in c.questions if q.answer or q.skipped
    ]
    return {'observedChange': observed, 'timeline': timeline, 'agentActions': agent_actions, 'userResponses': user_responses,
            'checkIns': len(checkins),
            'reminders': sum(1 for c in state.support.contacts if c['planId'] == plan.id and c['kind'] == 'reminder'),
            'goalChanges': [c for change in plan.history if change.actor == 'agent' for c in change.changes]}


def _template_summary(plan: SupportPlan, rule: EscalationRule, assessment: CareAssessment, facts: dict) -> str:
    done = [f"{facts['checkIns']} viikkotarkistusta"]
    if facts['reminders']:
        done.append(f"{facts['reminders']} muistutusta")
    goal_text = f" sekä sovittanut tavoitteen käyttäjän kanssa ({'; '.join(facts['goalChanges'])})" if facts['goalChanges'] else ''
    observed = ' '.join(facts['observedChange'][:2])
    return (
        f'{plan.name} (suunnitelman versio {plan.version}, vastuu: {plan.owner.label}). Syy: {rule.name}. {observed} '
        f"Agentti on tehnyt {' ja '.join(done)}{goal_text}. "
        f'Automaattinen hoidon tarpeen arvio: {assessment.urgencyLabel} ({assessment.handlingTime}). Peruste: sääntö {rule.id}.'
    )


def _open_decision(rule: EscalationRule, assessment: CareAssessment, esc_class: dict) -> str:
    if assessment.mode == 'professional_required':
        return OPEN_DECISION_NO_CONSENT.format(label=assessment.urgencyLabel)
    return OPEN_DECISIONS.get(rule.kind, OPEN_DECISION_DEFAULT).format(label=esc_class['label'], handling=esc_class['handlingTime'])


def _notice(plan: SupportPlan, rule: EscalationRule, assessment: CareAssessment, esc_class: dict) -> str:
    template = texts.ESCALATION_NOTICE_PRELIMINARY if assessment.mode == 'professional_required' else texts.ESCALATION_NOTICE
    return template.format(urgency_label=assessment.urgencyLabel, owner_cap=texts.capitalize(texts.owner_possessive(plan.owner.role)),
                           handling=esc_class['handlingTime'], reason_short=texts.ESCALATION_REASON_SHORT.get(rule.kind, ''))


def _build(state: LoopState, plan: SupportPlan, rule: EscalationRule, assessment: CareAssessment, facts: dict, *, trigger: str,
           chain_id: str, notify: bool, extra_sources: Optional[list[SourceRef]] = None, urgency: Optional[str] = None) -> tuple[Escalation, str]:
    """The Escalation itself: urgency, label and handling time are copied from the assessment (self_care routes as
    routine, because an escalation always means professional contact)."""
    esc_class = assessment_module.escalation_class(urgency or assessment.urgency)
    text, source, llm_task = _template_summary(plan, rule, assessment, facts), 'template', None
    if llm.enabled():
        llm_task = 'draft_escalation_summary (rajatut faktat: suunnitelma, sääntö, havainnot, agentin toimet, vastaukset, kiireellisyysluokka)'
        generated = llm.draft_escalation_summary({
            'plan': plan.name, 'planVersion': plan.version, 'rule': {'id': rule.id, 'name': rule.name, 'description': rule.description},
            'observedChange': facts['observedChange'], 'agentActions': [a['text'] for a in facts['agentActions']],
            'userResponses': [{'question': r['question'], 'answer': r['answer']} for r in facts['userResponses']],
            'urgencyFromRule': rule.urgencyLabel, 'urgencyLabel': assessment.urgencyLabel, 'handlingTime': assessment.handlingTime,
        })
        # the class is set by the rules: the draft must restate it verbatim and pass the safety check for that class
        if generated and check_text(generated, allowed_urgency=assessment.urgency)['passed'] \
                and assessment.urgencyLabel.lower() in generated.lower():
            text, source = generated, 'llm'
    escalation = Escalation(
        id=next_id(state, 'esc'), planId=plan.id, planVersion=plan.version, chainId=chain_id, createdAt=state.currentDate,
        trigger=trigger, urgency=assessment_module.to_rule_urgency(esc_class['id']), urgencyLabel=esc_class['label'],
        handlingTime=esc_class['handlingTime'], ownerRole=plan.owner.role, reason=rule.description,
        observedChange=facts['observedChange'], timeline=facts['timeline'],
        sources=[*plan.sources, *(extra_sources or [])], rulesApplied=[{'id': rule.id, 'name': rule.name, 'description': rule.description}],
        agentActions=facts['agentActions'], userResponses=facts['userResponses'],
        openDecision=_open_decision(rule, assessment, esc_class), summaryText=text, summarySource=source,
        assessmentId=assessment.id, humanReviewRequested=assessment.status == 'human_review_requested',
    )
    state.support.escalations.append(escalation)
    assessment.escalationId = escalation.id
    if plan.status == 'active':
        plan_state.transition(state, plan, 'escalated')
    plan.lastAgentAction = {'date': state.currentDate, 'action': 'escalate', 'label': LAST_ACTION_LABEL,
                            'detail': f'{escalation.urgencyLabel} – {rule.name}'}
    audit.record(state, stage='escalate', actor='agent', plan=plan, chain_id=chain_id, rule={'id': rule.id, 'name': rule.name},
                 action='escalate', escalated=True, llm_used=source == 'llm', llm_task=llm_task,
                 detail=f'Ohjaus vastuuammattilaiselle ({plan.owner.label}) automaattisen arvion perusteella: {escalation.urgencyLabel}, '
                        f'käsittely {escalation.handlingTime}. Eskalaatio {escalation.id}, arvio {assessment.id}.',
                 outcome=escalation.id)
    notice = _notice(plan, rule, assessment, esc_class)
    if notify:
        actions = [assessment_module.human_review_action(state, assessment)] if assessment.status == 'issued' else []
        messages.post(state, notice, kind='escalation_notice', plan=plan, actions=actions, assessment=assessment,
                      basis_data=messages.assessment_basis(assessment, plan))
    return escalation, notice


def create(state: LoopState, plan: SupportPlan, rule: EscalationRule, *, trigger: str, chain_id: str, obs: dict,
           notify: bool = True, extra_sources: Optional[list[SourceRef]] = None, extra_facts: Optional[list[str]] = None,
           period_metrics: Optional[dict] = None) -> tuple[Escalation, str]:
    """Rule-based routing: the automated assessment is made FIRST (class from the rule, same_day for the safety
    threshold), then the escalation is built on it."""
    facts = _facts(state, plan, obs, rule, trigger, extra_facts, period_metrics)
    urgency = 'same_day' if trigger == 'safety_threshold' else assessment_module.from_rule_urgency(rule.urgency)
    if trigger == 'user_request':
        reason = texts.HUMAN_REVIEW_REASON
    else:
        reason = f"{texts.ASSESSMENT_REASONS.get(rule.kind, rule.name)} (sääntö {rule.id})."
    assessment = assessment_module.create(state, trigger=trigger, urgency=urgency, reason=reason, basis=facts['observedChange'], rules=[rule],
                                          plan=plan, chain_id=chain_id, sources=[*plan.sources, *(extra_sources or [])])
    if trigger == 'user_request':
        # the user exercised the right to an assessment made by a professional; the automated one stays as background
        assessment.status = 'human_review_requested'
        assessment.humanReviewRequestedAt = state.currentDate
    return _build(state, plan, rule, assessment, facts, trigger=trigger, chain_id=chain_id, notify=notify, extra_sources=extra_sources)


def check_and_create(state: LoopState, plan: SupportPlan, obs: dict, *, chain_id: str, notify: bool = True,
                     period_metrics: Optional[dict] = None):
    rule = due_rule(state, plan, obs)
    if not rule or 'escalate' not in plan.allowedActions:
        return None
    return create(state, plan, rule, trigger='rule', chain_id=chain_id, obs=obs, notify=notify, period_metrics=period_metrics)


def create_user_request(state: LoopState, plan: SupportPlan, checkin: CheckIn, notify: bool = True):
    rule = next((r for r in plan.escalationRules if r.kind == 'user_request'), None)
    if not rule or 'escalate' not in plan.allowedActions or open_escalation(state, plan):
        return None
    barrier = checkin.outcome.get('barrier')
    extra = [f'Käyttäjä pyysi ammattilaisen tekemän arvion ja yhteydenottoa tarkistuksessa {fi_date(checkin.createdAt)}'
             + (' (esteenä kipu tai muu vaiva).' if barrier == 'pain' else '.')]
    return create(state, plan, rule, trigger='user_request', chain_id=checkin.chainId, obs=signals.evaluate(state, plan),
                  notify=notify, extra_facts=extra)


def create_human_review_request(state: LoopState, plan: SupportPlan, assessment: CareAssessment, notify: bool = False) -> Optional[Escalation]:
    """The user asks for a professional's assessment of an existing automated assessment that has no open escalation:
    route it through the plan's user_request rule without making a second assessment. The escalation takes the higher
    of the assessment's class and the rule's class."""
    rule = next((r for r in plan.escalationRules if r.kind == 'user_request'), None)
    if not rule or 'escalate' not in plan.allowedActions or open_escalation(state, plan):
        return None
    chain_id = assessment.chainId or audit.new_chain(state)
    obs = signals.evaluate(state, plan)
    extra = [f'Asiakas pyysi ammattilaisen tekemän arvion {fi_date(state.currentDate)} (automaattinen arvio {assessment.id}: {assessment.urgencyLabel}).',
             *assessment.basis]
    facts = _facts(state, plan, obs, rule, 'user_request', extra)
    urgency = assessment_module.higher(assessment.urgency, assessment_module.from_rule_urgency(rule.urgency))
    escalation, _ = _build(state, plan, rule, assessment, facts, trigger='user_request', chain_id=chain_id, notify=notify, urgency=urgency)
    escalation.humanReviewRequested = True
    return escalation


def create_from_assessment(state: LoopState, plan: SupportPlan, assessment: CareAssessment, chain_id: Optional[str] = None,
                           notify: bool = True) -> tuple[Escalation, str]:
    """Route an existing assessment (e.g. from a symptom report in the chat) to the professional. The rulesApplied entry
    is synthetic: the symptom rule that set the class (or 'TRI-SYMPTOM' when none). Posts no user notice when notify=False."""
    first = assessment.rulesApplied[0] if assessment.rulesApplied else {}
    esc_class = assessment_module.escalation_class(assessment.urgency)
    rule = EscalationRule(
        id=first.get('id') or 'TRI-SYMPTOM', name=first.get('name') or 'Oirekuvauksen automaattinen arvio',
        description=first.get('description') or assessment.reason, kind='symptom_report', params={},
        urgency=assessment_module.to_rule_urgency(esc_class['id']), urgencyLabel=esc_class['label'], handlingTime=esc_class['handlingTime'],
    )
    chain_id = chain_id or assessment.chainId or audit.new_chain(state)
    if not assessment.chainId:
        assessment.chainId = chain_id
    symptoms = ', '.join(assessment.symptoms) if assessment.symptoms else 'ei tunnistettuja avainsanoja'
    extra = [f'Asiakas kuvasi oireita chatissa {fi_date(assessment.createdAt)}: {symptoms}. Automaattinen arvio {assessment.id}: '
             f'{assessment.urgencyLabel}.', *[line for line in assessment.basis if not line.startswith('Oirekuvaus chatissa')]]
    facts = _facts(state, plan, signals.evaluate(state, plan), rule, 'rule', extra)
    return _build(state, plan, rule, assessment, facts, trigger='rule', chain_id=chain_id, notify=notify)


def create_safety(state: LoopState, plan: SupportPlan, obs: dict, chain_id: str) -> Optional[Escalation]:
    rule = next((r for r in plan.escalationRules if r.kind == 'safety_threshold'), None)
    signal = next((s for s in obs['signals'] if s['kind'] == 'safety_threshold' and s['detected']), None)
    if not rule or not signal:
        return None
    events = [e for e in state.events if e.id in signal.get('eventIds', [])]
    extra_sources = [SourceRef(kind='event', id=e.id, label=f'{e.displayName} {e.value}', date=e.date) for e in events]
    readings = ', '.join(f'{e.value} mmHg ({fi_date(e.date)})' for e in events)
    escalation, _ = create(state, plan, rule, trigger='safety_threshold', chain_id=chain_id, obs=obs, notify=False,
                           extra_sources=extra_sources,
                           extra_facts=[f"Kotimittaus {readings} ylitti suunnitelman demo-turvarajan "
                                        f"{rule.params.get('systolic')}/{rule.params.get('diastolic')} mmHg."])
    assessment = assessment_module.find(state, escalation.assessmentId)
    contact = policies.service_contact(policies.theme(plan.theme).get('serviceContact', 'NURSE_LINE'))
    # fixed, predefined safety message (never LLM); the user can still ask for a professional's assessment
    messages.post(
        state,
        texts.SAFETY_THRESHOLD_USER.format(value=events[-1].value if events else '', contact=f"{contact['label']}, {contact['details']}",
                                           owner=texts.owner_allative(plan.owner.role)),
        kind='safety_threshold', plan=plan, actions=[assessment_module.human_review_action(state, assessment)], assessment=assessment,
        basis_data=messages.assessment_basis(assessment, plan, decision_by=f'Ennalta määritelty turvasääntö {rule.id} (ei kielimallia)'),
    )
    state.support.contacts.append({'date': state.currentDate, 'planId': plan.id, 'kind': 'safety_message', 'urgent': True,
                                   'label': 'Turvaviesti (demo-turvaraja)', 'deliveredAt': 'heti'})
    return escalation
