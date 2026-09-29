"""Demo controls that make the agent's initiative visible without a real background scheduler."""
from __future__ import annotations

from typing import Any

from app.loop import agent as rule_engine
from app.loop.models import LoopState
from app.loop.store import add_days
from app.support import assessment, continuity, cycle, escalation, interventions, policies, professional, signals


class DemoError(ValueError):
    pass


def scripted_measurement(state: LoopState) -> dict[str, Any]:
    script = policies.load_setup().get('script', {}).get('measurements', [])
    if not script:
        raise DemoError('Demoskriptissä ei ole mittauksia.')
    index = state.support.scriptCursor.get('measurements', 0)
    systolic, diastolic = script[index % len(script)]
    state.support.scriptCursor['measurements'] = index + 1
    return cycle.add_home_measurement(state, systolic, diastolic, via='demo')


def scripted_home_monitoring(state: LoopState) -> dict[str, Any]:
    """The home monitoring period the user accepted: morning and evening readings from the script, one day at a time
    (the demo clock moves with the days). The agent summarises the period when the last reading comes in."""
    period = continuity.active_period(state)
    if not period:
        hint = ('Vastaa ensin agentin ehdotukseen: Kyllä, aloitetaan.' if continuity.open_offer(state) else
                'Agentti ehdottaa kotiseurantaa itse, kun kotimittausten taso nousee (esimerkiksi Lisää uusi mittaus kahdesti).')
        raise DemoError(f'Kotiseuranta ei ole käynnissä. {hint}')
    script = policies.load_setup().get('script', {}).get('homeMonitoring', [])
    if not script:
        raise DemoError('Demoskriptissä ei ole kotiseurannan mittauksia.')
    total = period.days * period.perDay
    added = []
    while period.status == 'active' and len(period.readingIds) < total:
        index = len(period.readingIds)
        day = add_days(period.startsAt, index // period.perDay)
        if day > state.currentDate:
            rule_engine.advance_time(state, signals.days_between(state.currentDate, day))
        systolic, diastolic = script[index % len(script)]
        cycle.add_home_measurement(state, systolic, diastolic, via='demo')
        added.append(f'{systolic}/{diastolic}')
        if len(period.readingIds) == index:  # the reading did not reach the period (e.g. a safety escalation): stop here
            break
    return {'periodId': period.id, 'readings': added, 'status': period.status, 'result': period.result}


def scripted_user_response(state: LoopState) -> dict[str, Any]:
    script = policies.load_setup().get('script', {}).get('userAnswers', {})
    try:
        return interventions.answer_scripted(state, script)
    except interventions.InterventionError as exc:
        raise DemoError(str(exc)) from exc


def scripted_professional_decision(state: LoopState) -> dict[str, Any]:
    """Apply the next pending professional decision from the demo script: first an open escalation, then a proposal."""
    script = policies.load_setup().get('script', {})
    for plan in state.support.plans:
        if plan.status == 'escalated' and escalation.open_escalation(state, plan):
            spec = script['escalationDecision']
            professional.decide(state, plan.id, spec['decision'], role=plan.owner.role, note=spec.get('note'),
                                changes=spec.get('changes'), escalation_appropriate=spec.get('escalationAppropriate'),
                                contact_user=spec.get('contactUser', False))
            return {'planId': plan.id, 'decision': spec['decision']}
    for plan in state.support.plans:
        if plan.status == 'pending_professional_review':
            spec = script['approveDecision']
            professional.decide(state, plan.id, spec['decision'], role=plan.owner.role, note=spec.get('note'))
            return {'planId': plan.id, 'decision': spec['decision']}
    raise DemoError('Ammattilaisen päätöstä odottavia suunnitelmia tai eskalaatioita ei ole.')


def scripted_symptom_report(state: LoopState) -> dict[str, Any]:
    """Post the scripted symptom description through the companion chat and return the automated assessment it made.
    If the chat did not route the message to the assessment handler, the rules-only path assesses it directly."""
    from app.loop import companion  # local import: the chat reads the support state

    text = policies.load_setup().get('script', {}).get('symptomReport')
    if not text:
        raise DemoError('Demoskriptissä ei ole oirekuvausta.')
    before = {a.id for a in state.support.assessments}
    try:
        result = companion.handle_user_message(state, text)
    except companion.CompanionError as exc:
        raise DemoError(str(exc)) from exc
    created = [a for a in state.support.assessments if a.id not in before]
    if not created:
        created = [assessment.assess_symptom_report(state, text)[0]]
    return {'assessment': assessment.view(state, created[-1]), 'intent': result.get('intent'), 'text': text}
