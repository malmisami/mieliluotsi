"""The agent cycle.

1 observe -> 2 compare with the active plan version -> 3 detect change / missing information -> 4 choose the
smallest sufficient allowed action -> 5 act -> 6 wait for / request the user's response -> 7 evaluate it
(interventions.answer) -> 8 update the situation -> 9 escalate when a rule holds -> 10 audit every step.

There is no background scheduler in the demo: the cycle runs when time is simulated, when new data arrives
(observation only) or when "Käynnistä agenttikierros" is pressed.
"""
from __future__ import annotations

from typing import Any

from app.loop import agent as rule_engine
from app.loop import llm
from app.loop.models import HealthEvent, LoopState
from app.loop.safety import check_text
from app.loop.templates import fi_date
from app.support import audit, consent, continuity, escalation, interventions, messages, policies, signals, texts
from app.support.models import SupportPlan

CYCLE_STATUSES = ('active', 'paused', 'escalated')


class CycleError(ValueError):
    pass


def _no_action(reason: str) -> dict:
    return {'action': 'no_action', 'reason': reason}


def _recent_contact(state: LoopState, plan: SupportPlan, kind: str, days: int) -> bool:
    return any(c['planId'] == plan.id and c['kind'] == kind and signals.days_between(c['date'], state.currentDate) < days
               for c in state.support.contacts)


def choose_action(state: LoopState, plan: SupportPlan, obs: dict) -> dict:
    """Step 4: the smallest sufficient action the plan allows. Order = policy ladder, safety first."""
    detected, allowed = obs['detected'], set(plan.allowedActions)
    if plan.status == 'paused':
        return _no_action('Seuranta on tauolla käyttäjän pyynnöstä. Agentti ei ota yhteyttä.')
    if 'source_disabled' in detected:
        return _no_action('Seurannan tietolähde ei ole käytössä. Agentti ei arvioi tilannetta eikä ota yhteyttä.')
    if 'safety_threshold' in detected and 'escalate' in allowed:
        rule = next((r for r in plan.escalationRules if r.kind == 'safety_threshold'), None)
        if rule:
            return {'action': 'escalate', 'urgent': True, 'kind': 'safety', 'rule': {'id': rule.id, 'name': rule.name},
                    'reason': f'Turvasääntö {rule.id}: yksittäinen mittaus ylitti suunnitelman demo-turvarajan. Automaattinen hoidon tarpeen '
                              'arvio: kiireellinen, samana päivänä; ohjaus vastuuammattilaiselle.'}
    if plan.status == 'escalated':
        return _no_action('Tilanne on arvioitu automaattisesti ja ohjattu ammattilaiselle. Agentti odottaa ammattilaisen päätöstä.')
    rule = escalation.due_rule(state, plan, obs)
    if rule and 'escalate' in allowed:
        return {'action': 'escalate', 'kind': 'rule', 'rule': {'id': rule.id, 'name': rule.name},
                'reason': f'Kiireellisyyssääntö {rule.id} täyttyi: {rule.name}. Agentti tekee automaattisen hoidon tarpeen arvion ja ohjaa '
                          'tilanteen ammattilaiselle.'}
    if 'checkin_due' in detected and 'check_in' in allowed and plan.microInterventions:
        return {'action': 'check_in', 'reason': f'Viikkotarkistus on ajankohtainen (suunnitelman tarkistusväli {plan.checkInEveryDays} pv).'}
    if detected & {'missing_measurement', 'stale_data'} and 'reminder' in allowed and not _recent_contact(state, plan, 'reminder', 3):
        return {'action': 'reminder', 'kind': 'measurements', 'reason': 'Sovittuja mittauksia puuttuu: ystävällinen muistutus riittää.'}
    outreach = continuity.outreach_due(state, plan, obs)
    if outreach and 'offer_home_monitoring' in allowed:
        return {'action': 'offer_home_monitoring', 'rule': {'id': outreach['id'], 'name': outreach['name']}, 'outreachRule': outreach,
                'reason': f"Yhteydenottosääntö {outreach['id']}: {outreach['name'].lower()}. Agentti ehdottaa itse kotiseurantaa – "
                          'käyttäjä päättää, aloitetaanko.'}
    if detected & {'review_due_soon', 'review_overdue'} and 'reminder' in allowed and not _recent_contact(state, plan, 'review_reminder', 14):
        return {'action': 'reminder', 'kind': 'review', 'reason': 'Seurannan tarkistuspäivä lähestyy: muistutus ja ajanvarauksen yhteystieto.'}
    if 'repeated_contact' in detected and 'show_guide' in allowed and plan.guides and not _recent_contact(state, plan, 'show_guide', 30):
        return {'action': 'show_guide', 'reason': 'Toistuvia yhteydenottoja samasta aiheesta: näytetään hyväksytty omahoito-ohje.'}
    if 'new_concern' in detected and 'clarifying_question' in allowed:
        return {'action': 'clarifying_question', 'reason': 'Käyttäjä kirjasi uuden huolen: yksi tarkentava kysymys.'}
    if 'rule_engine_observation' in detected:
        return _no_action('Sääntömoottorin huomio käsitellään Miksi nyt? -polun ja käyttäjän jakaman yhteenvedon kautta.')
    return _no_action('Tilanne on suunnitelman mukainen. Pienin riittävä toimenpide on olla ottamatta yhteyttä.')


def _record_contact(state: LoopState, plan: SupportPlan, kind: str, label: str, urgent: bool = False) -> None:
    state.support.contacts.append({
        'date': state.currentDate, 'planId': plan.id, 'kind': kind, 'label': label, 'urgent': urgent,
        'channel': state.support.consent.channel, 'deliveredAt': consent.delivery_time(state),
    })


def _guide_text(state: LoopState, plan: SupportPlan, chain_id: str) -> str:
    guide = policies.guide(plan.guides[0])
    text, used_llm = guide['text'], False
    if llm.enabled():
        rewritten = llm.plain_language(guide['text'])
        if rewritten and check_text(rewritten)['passed'] and len(rewritten) <= len(guide['text']) * 1.5:
            text, used_llm = rewritten, True
    audit.record(state, stage='act', actor='agent', plan=plan, chain_id=chain_id, action='show_guide', llm_used=used_llm,
                 llm_task='plain_language (hyväksytyn ohjeen selkokielistäminen)' if llm.enabled() else None,
                 detail=f"Näytettiin hyväksytty ohje ”{guide['title']}” ({guide['approvedBy']}, {fi_date(guide['approvedAt'])})."
                        + (' Kielimalli selkokielisti tekstin.' if used_llm else ''))
    return f"{texts.guide_attached(guide['title'])}\n\n{guide['title']}: {text}"


def execute(state: LoopState, plan: SupportPlan, decision: dict, obs: dict, chain_id: str) -> dict[str, Any]:
    """Step 5 (+6): carry out the chosen action. Every user-facing text is a predefined template."""
    action = decision['action']
    result: dict[str, Any] = {'action': action}
    if action == 'check_in':
        interventions.expire_stale(state, plan)
        checkin = interventions.create_checkin(state, plan, obs, chain_id, decision['reason'])
        if checkin:
            _record_contact(state, plan, 'check_in', 'Viikkotarkistus')
            audit.record(state, stage='act', actor='agent', plan=plan, chain_id=chain_id, action='check_in',
                         detail=f'Lähetettiin {len(checkin.questions)} kysymyksen tarkistus ({fi_date(checkin.createdAt)} klo '
                                f'{checkin.deliveredAt.split(" ")[1]}, kanava: {consent.CHANNEL_LABELS[checkin.channel].lower()}).')
            audit.record(state, stage='wait', actor='agent', plan=plan, chain_id=chain_id, action='await_response',
                         detail='Odotetaan käyttäjän vastausta. Vastaukset arvioidaan sääntöjen mukaan.')
            result['checkInId'] = checkin.id
    elif action == 'reminder' and decision.get('kind') == 'measurements':
        metrics = obs['metrics']
        text = texts.reminder_measurements(metrics.get('measurementCount', 0), metrics.get('measurementsRequired', plan.measurementsPerWeek),
                                           metrics.get('periodStart', state.currentDate))
        messages.post(state, text, kind='agent_reminder', plan=plan,
                      basis_data=messages.basis(plan, 'Agenttisykli: sovittu mittaus puuttuu', facts=[s['detail'] for s in obs['signals'] if s['detected']]))
        _record_contact(state, plan, 'reminder', 'Muistutus: kotimittaukset')
        audit.record(state, stage='act', actor='agent', plan=plan, chain_id=chain_id, action='reminder', detail=f'Muistutus lähetettiin: {text}')
    elif action == 'reminder':
        contact = policies.service_contact(policies.theme(plan.theme).get('serviceContact', 'NURSE_LINE'))
        text = texts.reminder_review(plan.name, plan.nextReviewAt, f"{contact['label']} ({contact['details']})")
        messages.post(state, text, kind='agent_reminder', plan=plan, basis_data=messages.basis(plan, 'Agenttisykli: tarkistuspäivä lähestyy'))
        _record_contact(state, plan, 'review_reminder', 'Muistutus: tarkistuspäivä')
        audit.record(state, stage='act', actor='agent', plan=plan, chain_id=chain_id, action='reminder', detail=f'Muistutus lähetettiin: {text}')
    elif action == 'show_guide':
        messages.post(state, _guide_text(state, plan, chain_id), kind='agent_guide', plan=plan,
                      basis_data=messages.basis(plan, 'Agenttisykli: toistuvat yhteydenotot samasta aiheesta'))
        _record_contact(state, plan, 'show_guide', 'Hyväksytty ohje näytettiin')
    elif action == 'clarifying_question':
        checkin = interventions.create_concern_question(state, plan, obs, chain_id)
        if checkin:
            _record_contact(state, plan, 'clarifying_question', 'Tarkentava kysymys')
            audit.record(state, stage='act', actor='agent', plan=plan, chain_id=chain_id, action='clarifying_question',
                         detail='Kysyttiin yksi tarkentava kysymys käyttäjän kirjaamasta huolesta.')
    elif action == 'offer_home_monitoring':
        period = continuity.offer_home_monitoring(state, plan, obs, chain_id, decision['outreachRule'])
        result['periodId'] = period.id
    elif action == 'escalate' and decision.get('kind') == 'safety':
        created = escalation.create_safety(state, plan, obs, chain_id)
        result['escalationId'] = created.id if created else None
    elif action == 'escalate':
        created = escalation.check_and_create(state, plan, obs, chain_id=chain_id)
        result['escalationId'] = created[0].id if created else None
    plan.lastAgentAction = plan.lastAgentAction if action.startswith('escalate') else {
        'date': state.currentDate, 'action': action, 'label': policies.action_label(action), 'detail': decision['reason']}
    return result


def run_plan(state: LoopState, plan: SupportPlan, trigger: str) -> dict[str, Any]:
    chain_id = audit.new_chain(state)
    obs = signals.evaluate(state, plan)
    allowed_sources = [consent.SOURCE_LABELS[k].lower() for k, v in state.support.consent.dataSources.items() if v]
    audit.record(state, stage='observe', actor='agent', plan=plan, chain_id=chain_id, signal={'metrics': obs['metrics']},
                 detail=f'Agenttisykli ({trigger}). Luettiin vain sallitut tietolähteet: {", ".join(allowed_sources)}.')
    target = f", tavoitetaso {plan.demoTarget['label'].lower()}" if plan.demoTarget else ''
    goal = f', tavoite {plan.goal.label}' if plan.goal else ''
    audit.record(state, stage='compare', actor='agent', plan=plan, chain_id=chain_id,
                 detail=f'Verrattiin suunnitelman versioon {plan.version}: {plan.measurementsPerWeek} mittausta/tarkistusväli, '
                        f'tarkistus {plan.checkInEveryDays} pv välein{target}{goal}.')
    found = [s for s in obs['signals'] if s['detected']]
    labels = [signals.SIGNAL_LABELS.get(key, key) for key in sorted(obs['detected'])]
    audit.record(state, stage='detect', actor='agent', plan=plan, chain_id=chain_id,
                 signal={'detected': sorted(obs['detected']), 'details': [s['detail'] for s in found]},
                 detail=('Havaitut signaalit: ' + ', '.join(labels) + '.') if labels else 'Ei poikkeavia signaaleja.')
    decision = choose_action(state, plan, obs)
    audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=chain_id, action=decision['action'], rule=decision.get('rule'),
                 detail=f"{policies.action_label(decision['action'])}. {decision['reason']}")
    result: dict[str, Any] = {'planId': plan.id, 'plan': plan.name, 'signals': sorted(obs['detected']), 'action': decision['action'],
                              'reason': decision['reason']}
    if decision['action'] == 'no_action':
        plan.lastAgentAction = {'date': state.currentDate, 'action': 'no_action', 'label': policies.action_label('no_action'),
                                'detail': decision['reason']}
        return result
    if policies.contacts_user(decision['action']):
        blocked = consent.contact_block_reason(state, plan, urgent=decision.get('urgent', False))
        if blocked:
            audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=chain_id, action='deferred', outcome='deferred',
                         detail=f'Yhteydenottoa ei tehty (portti 3): {blocked}')
            plan.lastAgentAction = {'date': state.currentDate, 'action': 'deferred', 'label': 'Yhteydenotto lykättiin', 'detail': blocked}
            return {**result, 'action': 'deferred', 'blockedBy': blocked}
    return {**result, **execute(state, plan, decision, obs, chain_id)}


def run_cycle(state: LoopState, trigger: str = 'käynnistetty käsin') -> dict[str, Any]:
    if not state.support.person:
        raise CycleError('Seurannan tietoja ei ole ladattu. Palauta demo alkutilaan.')
    from app.support.user_actions import resume_expired_pauses  # local import: user_actions posts messages via this package

    resume_expired_pauses(state)
    closed = continuity.close_stale(state)  # an unanswered offer expires, a finished home monitoring period is summarised
    results = [run_plan(state, plan, trigger) for plan in state.support.plans if plan.status in CYCLE_STATUSES]
    state.support.lastCycleAt = state.currentDate
    return {'date': state.currentDate, 'trigger': trigger, 'plans': results, 'homeMonitoring': closed}


def observe_event(state: LoopState, event: HealthEvent) -> list[dict[str, Any]]:
    """New data triggers observation. The agent contacts the user only if a safety rule requires it, or - the continuity
    engine - if the reading belongs to a home monitoring period or makes the plan's outreach rule hold."""
    if not state.support.person:
        return []
    results = []
    for plan in state.support.plans:
        if plan.status not in ('active', 'escalated') or plan.measurementCode != event.code:
            continue
        chain_id = audit.new_chain(state)
        audit.record(state, stage='observe', actor='agent', plan=plan, chain_id=chain_id,
                     detail=f'Uusi tieto: {event.displayName} {event.value or ""} {event.unit or ""} ({fi_date(event.date)}).'.replace('  ', ' '))
        obs = signals.evaluate(state, plan)
        if 'safety_threshold' in obs['detected'] and 'escalate' in plan.allowedActions:
            decision = choose_action(state, plan, obs)
            audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=chain_id, action='escalate', rule=decision.get('rule'),
                         detail=decision['reason'])
            results.append({'planId': plan.id, **execute(state, plan, decision, obs, chain_id)})
            continue
        outcome = continuity.observe_reading(state, plan, event, obs, chain_id)
        if outcome:
            results.append({'planId': plan.id, **outcome})
            continue
        average = obs['metrics'].get('average')
        detail = (f"Kotimittausten keskiarvo nyt {average['systolic']}/{average['diastolic']} mmHg ({average['n']} mittausta). "
                  if average else '')
        next_check = f' Tieto huomioidaan seuraavassa tarkistuksessa {fi_date(plan.nextCheckInAt)}.' if plan.nextCheckInAt else ''
        audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=chain_id, action='no_action',
                     detail=f'{detail}Pienin riittävä toimenpide: ei yhteydenottoa nyt.{next_check}')
        results.append({'planId': plan.id, 'action': 'no_action'})
    return results


def add_home_measurement(state: LoopState, systolic: int, diastolic: int, via: str = 'user') -> dict[str, Any]:
    if not (60 <= systolic <= 260 and 30 <= diastolic <= 160 and diastolic < systolic):
        raise CycleError('Tarkista mittausarvot: yläpaine 60–260 ja alapaine 30–160 mmHg, alapaine yläpainetta pienempi.')
    source = 'Kotimittaus (demo-ohjaus)' if via == 'demo' else 'user_reported'
    result = rule_engine.add_event(state, fields={
        'type': 'vital_sign', 'code': 'BP', 'displayName': 'Verenpaine (kotimittaus)', 'value': f'{systolic}/{diastolic}',
        'unit': 'mmHg', 'source': source,
    })
    event = next(e for e in state.events if e.id == result['event']['id'])
    event.structuredData = {'systolic': systolic, 'diastolic': diastolic, 'context': 'home'}
    event.confirmedByUser = via != 'demo'
    event.abnormalFlag = None
    return {'event': event.model_dump(), 'agent': observe_event(state, event)}


def simulate_days(state: LoopState, days: int) -> dict[str, Any]:
    """Advance demo time (the rule engine's follow-up tasks move too) and run one agent cycle on the new date."""
    result = rule_engine.advance_time(state, days)
    cycle = run_cycle(state, f'demoaikaa siirrettiin {days} päivää') if state.support.person else None
    return {**result, 'cycle': cycle}
