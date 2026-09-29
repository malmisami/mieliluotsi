"""Automated assessment of the need for care and its urgency (hoidon tarpeen ja kiireellisyyden arvio).

Prototype for the anticipated amendment of terveydenhuoltolaki 51 § (3 mom., digitaalinen hoidon tarpeen arvio); the
prototype ASSUMES the amendment enters into force in 2027. Principle: the companion makes the assessment automatically
from documented rules (the policy's symptom table and context rules, the plan's escalation rules, the safety threshold);
the professional decides on care and oversees the assessments; the user always has the right to an assessment made by
a professional. The optional LLM never sets, changes or evaluates the urgency class.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.loop.models import ChatAction, ChatMessage, LoopState
from app.loop.store import next_id
from app.loop.templates import fi_date
from app.support import audit, consent, messages, plans, policies, signals, texts
from app.support.models import CareAssessment, SourceRef, SupportPlan

URGENCY_ORDER = ['self_care', 'routine', 'within_3_days', 'same_day', 'emergency']
_RULE_TO_ASSESSMENT = {'routine': 'routine', 'soon': 'within_3_days', 'same_day': 'same_day'}
_ASSESSMENT_TO_RULE = {'self_care': 'routine', 'routine': 'routine', 'within_3_days': 'soon', 'same_day': 'same_day', 'emergency': 'same_day'}
_STATUS_AFTER_REVIEW = {'confirm': 'confirmed', 'change_urgency': 'changed', 'take_over': 'human_reviewed'}
OPEN_STATUSES = ('issued', 'human_review_requested')
REVIEW_LABELS = texts.ASSESSMENT_REVIEW_LABELS


class AssessmentError(ValueError):
    pass


# --- policy lookups --------------------------------------------------------------------------------------------------

def automation() -> dict:
    return policies.load_policies().get('automation', {})


def urgency_classes() -> list[dict]:
    return list(automation().get('urgencyClasses', []))


def urgency_class(urgency: str) -> dict:
    for item in urgency_classes():
        if item['id'] == urgency:
            return item
    raise AssessmentError(f'Tuntematon kiireellisyysluokka: {urgency}')


def urgency_labels() -> dict[str, str]:
    return {item['id']: item['label'] for item in urgency_classes()}


def from_rule_urgency(rule_urgency: str) -> str:
    """EscalationRule.urgency (routine | soon | same_day) -> assessment class."""
    return _RULE_TO_ASSESSMENT.get(rule_urgency, 'routine')


def to_rule_urgency(urgency: str) -> str:
    """Assessment class -> the plan rules' urgency vocabulary used by Escalation.urgency."""
    return _ASSESSMENT_TO_RULE.get(urgency, 'routine')


def higher(first: str, second: str) -> str:
    return first if URGENCY_ORDER.index(first) >= URGENCY_ORDER.index(second) else second


def escalation_class(urgency: str) -> dict:
    """An escalation always means professional contact, so 'self_care' is routed with the routine class."""
    return urgency_class('routine' if urgency == 'self_care' else urgency)


# --- lookups ------------------------------------------------------------------------------------------------------------

def _id_number(assessment_id: str) -> int:
    try:
        return int(assessment_id.rsplit('-', 1)[-1])
    except ValueError:
        return 0


def newest_first(items: list[CareAssessment]) -> list[CareAssessment]:
    return sorted(items, key=lambda a: (a.createdAt, _id_number(a.id)), reverse=True)


def find(state: LoopState, assessment_id: str) -> CareAssessment:
    assessment = next((a for a in state.support.assessments if a.id == assessment_id), None)
    if not assessment:
        raise AssessmentError('Arviota ei löytynyt.')
    return assessment


def latest_open(state: LoopState, plan: Optional[SupportPlan] = None) -> Optional[CareAssessment]:
    """The newest assessment still waiting for the professional's oversight (issued or human review requested)."""
    items = [a for a in state.support.assessments if a.status in OPEN_STATUSES and a.mode != 'excluded_emergency'
             and (plan is None or a.planId == plan.id)]
    return newest_first(items)[0] if items else None


def latest_for_home(state: LoopState, within_days: int = 14) -> Optional[CareAssessment]:
    """The client's home card: the newest open assessment, or else the newest one a professional reviewed recently,
    so the user sees the outcome of the oversight (never an emergency record, which the fixed 112 text covers)."""
    open_item = latest_open(state)
    if open_item:
        return open_item
    reviewed = [a for a in state.support.assessments
                if a.mode != 'excluded_emergency' and a.professionalReview and a.professionalReview.get('date')
                and 0 <= signals.days_between(a.professionalReview['date'], state.currentDate) <= within_days]
    return newest_first(reviewed)[0] if reviewed else None


def linked_escalation(state: LoopState, assessment: CareAssessment):
    return next((e for e in state.support.escalations if e.id == assessment.escalationId), None) if assessment.escalationId else None


def _bp_plan(state: LoopState) -> Optional[SupportPlan]:
    return next((p for p in state.support.plans if p.theme == 'blood_pressure' and p.status in ('active', 'escalated')), None)


def _rule_dict(rule: Any) -> dict:
    if isinstance(rule, dict):
        return {'id': rule.get('id'), 'name': rule.get('name') or rule.get('id'), 'description': rule.get('description') or rule.get('reason', '')}
    return {'id': rule.id, 'name': rule.name, 'description': rule.description}


# --- classification: deterministic symptom table + context rules (never the LLM) ----------------------------------------

def classify_symptoms(state: LoopState, text: str) -> dict:
    """Returns {'urgency', 'rule', 'symptoms', 'reason', 'contextNotes', 'contextRules'}. The highest matching class
    of the policy's symptom table wins; the context rules may only raise the class using the blood-pressure plan's
    metrics (signals.evaluate). Deterministic regexes, no LLM."""
    lowered = text.lower()
    table = automation().get('symptomRules', [])
    matched, symptoms = None, []
    for rule in sorted(table, key=lambda r: -URGENCY_ORDER.index(r['urgency'])):
        hits = []
        for pattern in rule.get('patterns', []):
            match = re.search(r'\w*' + pattern + r'\w*', lowered)
            if match and match.group(0).strip() not in hits:
                hits.append(match.group(0).strip())
        if hits:
            matched, symptoms = rule, hits
            break
    if matched is None:
        matched = next((r for r in table if r.get('default')), None)
    urgency = matched['urgency'] if matched else 'self_care'
    reason = matched['reason'] if matched else 'Kuvauksesta ei tunnistu hoidon tarvetta, joka vaatisi yhteydenottoa; omahoito riittää.'
    context_notes: list[str] = []
    context_rules: list[dict] = []
    plan = _bp_plan(state)
    if plan and urgency != 'emergency' and consent.source_allowed(state, 'measurements'):
        obs = signals.evaluate(state, plan)
        for ctx in automation().get('contextRules', []):
            applied = False
            if ctx['id'] == 'TRI-CTX-BP-SAFETY':
                limits = next((s.get('params', {}) for s in plan.signals if s.get('kind') == 'safety_threshold'), None)
                readings = signals.home_readings(state, until=state.currentDate)
                if limits and readings:
                    event, systolic, diastolic = readings[-1]
                    recent = signals.days_between(event.date, state.currentDate) <= ctx.get('withinDays', 7)
                    over = systolic >= limits.get('systolic', 180) or diastolic >= limits.get('diastolic', 110)
                    minimum = ctx.get('minUrgency', 'same_day')
                    if recent and over and URGENCY_ORDER.index(urgency) < URGENCY_ORDER.index(minimum):
                        urgency, applied = minimum, True
                        context_notes.append(f"{ctx['id']}: viimeisin kotimittaus {systolic}/{diastolic} mmHg ({fi_date(event.date)}) ylittää "
                                             f"suunnitelman turvarajan – luokka nostettiin: {urgency_class(urgency)['label']}.")
            elif ctx['id'] == 'TRI-CTX-BP-ABOVE':
                if 'above_target' in obs['detected'] and urgency == ctx.get('from', 'routine'):
                    urgency, applied = ctx.get('to', 'within_3_days'), True
                    average = obs['metrics'].get('average') or {}
                    context_notes.append(f"{ctx['id']}: kotimittausten keskiarvo {average.get('systolic')}/{average.get('diastolic')} mmHg on "
                                         f"tavoitetason yläpuolella – luokka nostettiin: {urgency_class(urgency)['label']}.")
            if applied:
                context_rules.append({'id': ctx['id'], 'name': ctx['id'], 'description': ctx['description']})
                if ctx.get('reason'):
                    reason = f"{reason} {ctx['reason']}"
    return {
        'urgency': urgency,
        'rule': {'id': matched['id'], 'name': matched.get('name', matched['id']), 'description': matched['reason']} if matched else None,
        'symptoms': symptoms,
        'reason': reason,
        'contextNotes': context_notes,
        'contextRules': context_rules,
    }


# --- creation ---------------------------------------------------------------------------------------------------------

def create(
    state: LoopState, *, trigger: str, urgency: str, reason: str, basis: list[str], rules: list, plan: Optional[SupportPlan] = None,
    chain_id: Optional[str] = None, sources: Optional[list[SourceRef]] = None, symptoms: Optional[list[str]] = None, llm_used: bool = False,
) -> CareAssessment:
    """Record one automated assessment: mode from consent (professional_required without consent, excluded_emergency for
    112 cases), labels from the policy, the fixed legal notice, and an audit line (stage 'assess')."""
    cls = urgency_class(urgency)
    if urgency == 'emergency':
        mode = 'excluded_emergency'
    elif not state.support.consent.automatedAssessment:
        mode = 'professional_required'
    else:
        mode = 'automated'
    chain_id = chain_id or audit.new_chain(state)
    assessment = CareAssessment(
        id=next_id(state, 'hta'), planId=plan.id if plan else None, planVersion=plan.version if plan else None, chainId=chain_id,
        createdAt=state.currentDate, trigger=trigger, mode=mode, urgency=urgency, urgencyLabel=cls['label'], careNeed=cls['careNeed'],
        careNeedLabel=cls['careNeedLabel'], handlingTime=cls['handlingTime'], reason=reason,
        basis=[consent.mask_genes(state, line) or '' for line in basis], rulesApplied=[_rule_dict(r) for r in rules],
        sources=list(sources or []), symptoms=list(symptoms or []), llmUsed=llm_used, legalNotice=texts.LEGAL_NOTICE_PRELIMINARY if mode == 'professional_required' else texts.LEGAL_NOTICE,
    )
    state.support.assessments.append(assessment)
    mode_note = {
        'automated': '',
        'professional_required': ' Asiakas ei ole antanut suostumusta automaattiseen arvioon: esiarvio, jonka ammattilainen tekee.',
        'excluded_emergency': ' Hätätilanne ei kuulu automaattisen arvion piiriin (112).',
    }[mode]
    first = assessment.rulesApplied[0] if assessment.rulesApplied else None
    audit.record(state, stage='assess', actor='agent', plan=plan, chain_id=chain_id, action='assess_care_need', outcome=urgency,
                 rule={'id': first['id'], 'name': first['name']} if first else None,
                 detail=f"Automaattinen hoidon tarpeen arvio: {cls['label']} ({cls['handlingTime']}). Peruste: {reason}{mode_note}")
    if plan:
        plan.lastAgentAction = {'date': state.currentDate, 'action': 'assess', 'label': texts.ASSESSMENT_DONE_LABEL, 'detail': cls['label']}
    return assessment


def _apply_urgency(state: LoopState, assessment: CareAssessment, urgency: str) -> None:
    """Change the class of an assessment and of its linked open escalation (labels always from the policy)."""
    cls = urgency_class(urgency)
    assessment.urgency, assessment.urgencyLabel = urgency, cls['label']
    assessment.careNeed, assessment.careNeedLabel, assessment.handlingTime = cls['careNeed'], cls['careNeedLabel'], cls['handlingTime']
    escalation = linked_escalation(state, assessment)
    if escalation and escalation.status == 'open':
        esc = escalation_class(urgency)
        escalation.urgency = to_rule_urgency(esc['id'])
        escalation.urgencyLabel, escalation.handlingTime = esc['label'], esc['handlingTime']


# --- the user's right to an assessment made by a professional -----------------------------------------------------------

def human_review_action(state: LoopState, assessment: CareAssessment) -> ChatAction:
    return messages.action(state, texts.HUMAN_REVIEW_BUTTON, 'request_human_assessment', style='secondary', assessmentId=assessment.id)


def request_human_review(state: LoopState, assessment_id: str, *, via: str = 'chat') -> CareAssessment:
    """The user exercises the right to an assessment made by a professional. The automated assessment stays as
    background information; the linked escalation is flagged, or one is created through the plan's user_request rule
    (no second assessment). Posts HUMAN_REVIEW_CONFIRMED. `via='home'` also records the user's choice in the chat."""
    from app.support import escalation as escalation_module  # local import: escalation builds on this module

    assessment = find(state, assessment_id)
    if assessment.mode == 'excluded_emergency':
        raise AssessmentError('Hätätilanteessa soita 112. Hätätilanne ei kuulu automaattisen arvion piiriin.')
    if assessment.status == 'human_review_requested':
        raise AssessmentError('Ammattilaisen arvio on jo pyydetty.')
    if assessment.status != 'issued':
        raise AssessmentError('Ammattilainen on jo käsitellyt tämän arvion.')
    if via != 'chat':
        messages.user_choice(state, texts.HUMAN_REVIEW_BUTTON)
    assessment.status = 'human_review_requested'
    assessment.humanReviewRequestedAt = state.currentDate
    plan = plans.find(state, assessment.planId) if assessment.planId else None
    audit.record(state, stage='assess', actor='user', plan=plan, chain_id=assessment.chainId, action='request_human_review',
                 outcome='human_review_requested',
                 detail=f'Asiakas käytti oikeuttaan ammattilaisen tekemään arvioon (arvio {assessment.id}, automaattinen luokka '
                        f'{assessment.urgencyLabel}). Automaattinen arvio jää taustatiedoksi.')

    owner_role = plan.owner.role if plan else None
    handling: Optional[str] = None
    escalation = linked_escalation(state, assessment)
    if escalation and escalation.status == 'open':
        escalation.humanReviewRequested = True
        if not escalation.openDecision.startswith('Asiakas pyysi ammattilaisen tekemän arvion.'):
            escalation.openDecision = 'Asiakas pyysi ammattilaisen tekemän arvion. ' + escalation.openDecision
        handling = escalation.handlingTime
    else:
        candidates = [p for p in [plan, *state.support.plans] if p and p.status in ('active', 'escalated')
                      and any(r.kind == 'user_request' for r in p.escalationRules)]
        target = next(iter(candidates), None)
        if target:
            open_escalation = escalation_module.open_escalation(state, target)
            if open_escalation:
                open_escalation.humanReviewRequested = True
                if not open_escalation.openDecision.startswith('Asiakas pyysi ammattilaisen tekemän arvion.'):
                    open_escalation.openDecision = 'Asiakas pyysi ammattilaisen tekemän arvion. ' + open_escalation.openDecision
                handling, owner_role = open_escalation.handlingTime, target.owner.role
            else:
                created = escalation_module.create_human_review_request(state, target, assessment)
                if created:
                    handling, owner_role = created.handlingTime, target.owner.role
    if handling is None:
        handling = urgency_class('within_3_days')['handlingTime']
    text = texts.HUMAN_REVIEW_CONFIRMED.format(owner=texts.owner_possessive(owner_role or 'other'), handling=handling,
                                               urgency_label=assessment.urgencyLabel)
    messages.post(state, text, kind='assessment_notice', plan=plan, initiated_by_agent=False, assessment=assessment,
                  basis_data=messages.assessment_basis(assessment, plan, decision_by='Asiakkaan pyyntö: oikeus ammattilaisen tekemään arvioon'))
    sync_chat(state)
    return assessment


# --- professional oversight ---------------------------------------------------------------------------------------------

def professional_review(
    state: LoopState, assessment_id: str, decision: str, *, role: str, note: Optional[str] = None, new_urgency: Optional[str] = None,
) -> CareAssessment:
    """confirm | change_urgency | take_over. change_urgency updates the assessment and its linked open escalation."""
    assessment = find(state, assessment_id)
    if decision not in REVIEW_LABELS:
        raise AssessmentError('Tuntematon päätös.')
    if role not in policies.load_policies()['ownerRoles']:
        raise AssessmentError('Tuntematon ammattilaisen rooli.')
    if assessment.status not in OPEN_STATUSES:
        raise AssessmentError('Arvio on jo käsitelty.')
    if new_urgency is not None and new_urgency not in URGENCY_ORDER:
        raise AssessmentError('Valitse kelvollinen kiireellisyysluokka.')
    if decision == 'change_urgency':
        if not new_urgency:
            raise AssessmentError('Valitse uusi kiireellisyysluokka.')
        if new_urgency == assessment.urgency:
            raise AssessmentError('Uusi kiireellisyysluokka on sama kuin nykyinen. Vahvista arvio, jos se on oikea.')
    note = (note or '').strip()[:500] or None
    label, role_label = REVIEW_LABELS[decision], policies.owner_label(role)
    old_label = assessment.urgencyLabel
    changed = decision != 'confirm' and bool(new_urgency) and new_urgency != assessment.urgency
    if changed:
        _apply_urgency(state, assessment, new_urgency)
    assessment.status = _STATUS_AFTER_REVIEW[decision]
    assessment.professionalReview = {'decision': decision, 'label': label, 'byRole': role_label, 'date': state.currentDate, 'note': note,
                                     'newUrgency': assessment.urgency if changed else None, 'newUrgencyLabel': assessment.urgencyLabel if changed else None}
    plan = plans.find(state, assessment.planId) if assessment.planId else None
    audit.record(state, stage='professional_decision', actor='professional', plan=plan, chain_id=assessment.chainId, professional_decision=label,
                 outcome=assessment.status,
                 detail=f'{role_label}: {label} – automaattinen hoidon tarpeen arvio {assessment.id} ({old_label}'
                        + (f' → {assessment.urgencyLabel}' if changed else '') + ').' + (f' {note}' if note else ''))
    template = {'confirm': texts.ASSESSMENT_REVIEWED_CONFIRM, 'change_urgency': texts.ASSESSMENT_REVIEWED_CHANGED,
                'take_over': texts.ASSESSMENT_REVIEWED_TAKEOVER}[decision]
    text = template.format(owner_cap=texts.capitalize(texts.owner_possessive(role)), urgency_label=assessment.urgencyLabel, note=note or '').strip()
    messages.post(state, text, kind='assessment_notice', plan=plan, assessment=assessment,
                  basis_data=messages.assessment_basis(assessment, plan, decision_by=f'Ammattilaisen päätös ({role_label}): {label}'))
    sync_chat(state)
    return assessment


def review_from_plan_decision(state: LoopState, assessment_id: Optional[str], *, appropriate: bool, role_label: str,
                              note: Optional[str]) -> Optional[CareAssessment]:
    """A plan decision that resolves an escalation also answers 'Oliko automaattinen kiireellisyysarvio oikea?'."""
    if not assessment_id:
        return None
    assessment = next((a for a in state.support.assessments if a.id == assessment_id), None)
    if not assessment or assessment.status not in OPEN_STATUSES:
        return None
    decision = 'confirm' if appropriate else 'change_urgency'
    assessment.status = 'confirmed' if appropriate else 'changed'
    assessment.professionalReview = {
        'decision': decision, 'byRole': role_label, 'date': state.currentDate,
        'label': REVIEW_LABELS[decision] if appropriate else 'Kiireellisyysarvio todettu vääräksi suunnitelmapäätöksessä',
        'note': note or ('Ammattilainen arvioi kiireellisyyden toisin suunnitelmapäätöksen yhteydessä.' if not appropriate else None),
        'newUrgency': None, 'newUrgencyLabel': None,
    }
    sync_chat(state)
    return assessment


def sampling_due(state: LoopState) -> list[str]:
    """Deterministic sampling of automated assessments that did not lead to an escalation: every n-th assessment
    (n = 1 / reviewShare, 20 % -> every 5th id number) goes to the oversight queue."""
    share = automation().get('sampling', {}).get('reviewShare', 0.2)
    every = max(1, round(1 / share)) if share else 0
    if not every:
        return []
    return [a.id for a in state.support.assessments
            if a.mode == 'automated' and not a.escalationId and a.status == 'issued' and _id_number(a.id) % every == 0]


def oversight_ids(state: LoopState) -> list[str]:
    """The professional's oversight queue: open assessments linked to an open escalation, sampled, requested by the user,
    made without consent (esiarvio) or urgent without a route to an escalation. Sorted by urgency, newest first."""
    sampled = set(sampling_due(state))
    open_escalations = {e.id for e in state.support.escalations if e.status == 'open'}
    due = []
    for item in state.support.assessments:
        if item.status not in OPEN_STATUSES:
            continue
        linked_open = item.escalationId in open_escalations
        unrouted_urgent = not item.escalationId and item.urgency in ('same_day', 'within_3_days') and item.mode != 'excluded_emergency'
        if linked_open or item.id in sampled or item.status == 'human_review_requested' or item.mode == 'professional_required' or unrouted_urgent:
            due.append(item)
    ordered = sorted(newest_first(due), key=lambda a: -URGENCY_ORDER.index(a.urgency))
    return [a.id for a in ordered]


def human_review_request_ids(state: LoopState) -> list[str]:
    return [a.id for a in newest_first([a for a in state.support.assessments if a.status == 'human_review_requested'])]


# --- symptom reports from the chat ----------------------------------------------------------------------------------------

def symptom_text(state: LoopState, assessment: CareAssessment, plan: Optional[SupportPlan], escalation=None) -> str:
    """The user's reply for a symptom report (template, checked with the class's allowed vocabulary in tests)."""
    owner_role = plan.owner.role if plan else 'other'
    care_need = assessment.careNeedLabel if assessment.careNeedLabel.endswith('.') else f'{assessment.careNeedLabel}.'
    if assessment.mode == 'professional_required':
        handling = escalation.handlingTime if escalation else escalation_class(assessment.urgency)['handlingTime']
        return texts.SYMPTOM_ASSESSMENT_PRELIMINARY.format(urgency_label=assessment.urgencyLabel, care_need=care_need, reason=assessment.reason,
                                                            owner=texts.owner_possessive(owner_role), handling=handling)
    if assessment.urgency == 'self_care':
        follow_up = texts.SYMPTOM_FOLLOW_UP_SELF_CARE
    elif plan:
        follow_up = texts.SYMPTOM_FOLLOW_UP_CONTACT.format(owner=texts.owner_allative(owner_role), handling=assessment.handlingTime)
    else:
        contact = policies.service_contact('NURSE_LINE')
        follow_up = texts.SYMPTOM_FOLLOW_UP_NO_PLAN.format(contact=f"{contact['label']}, {contact['details']}")
    return texts.SYMPTOM_ASSESSMENT.format(urgency_label=assessment.urgencyLabel, care_need=care_need, reason=assessment.reason, follow_up=follow_up)


def post_symptom_assessment(state: LoopState, assessment: CareAssessment, plan: Optional[SupportPlan], escalation=None) -> ChatMessage:
    actions = [human_review_action(state, assessment), messages.action(state, texts.SYMPTOM_DISMISS_BUTTON, 'dismiss')]
    return messages.post(state, symptom_text(state, assessment, plan, escalation), kind='care_assessment', plan=plan, actions=actions,
                         basis_data=messages.assessment_basis(assessment, plan), assessment=assessment, initiated_by_agent=False)


def assess_symptom_report(state: LoopState, text: str, *, post: bool = True) -> tuple[CareAssessment, Optional[ChatMessage]]:
    """Rules-only path for a symptom description: classify, record the assessment, route it to the professional through
    the blood-pressure plan when the class requires contact (or always without consent), and post the reply.
    Emergencies are recorded (mode excluded_emergency) but never phrased here: the chat uses its fixed 112 message."""
    from app.support import escalation as escalation_module  # local import: escalation builds on this module

    result = classify_symptoms(state, text)
    plan = _bp_plan(state)
    rules = [r for r in [result['rule']] if r] + result['contextRules']
    described = f"Oirekuvaus chatissa {fi_date(state.currentDate)}" + (f": {', '.join(result['symptoms'])}." if result['symptoms'] else '.')
    assessment = create(state, trigger='symptom_report', urgency=result['urgency'], reason=result['reason'],
                        basis=[described, *result['contextNotes']], rules=rules, plan=plan, symptoms=result['symptoms'])
    escalation = None
    needs_contact = assessment.urgency != 'self_care' or assessment.mode == 'professional_required'
    if assessment.mode != 'excluded_emergency' and needs_contact and plan and 'escalate' in plan.allowedActions \
            and not escalation_module.open_escalation(state, plan):
        escalation, _ = escalation_module.create_from_assessment(state, plan, assessment, assessment.chainId, notify=False)
    message = post_symptom_assessment(state, assessment, plan, escalation) if post and assessment.mode != 'excluded_emergency' else None
    return assessment, message


# --- read model -------------------------------------------------------------------------------------------------------------

def view(state: LoopState, assessment: CareAssessment) -> dict[str, Any]:
    data = assessment.model_dump()
    data.update({
        'basis': [consent.mask_genes(state, line) for line in assessment.basis],
        'statusLabel': texts.ASSESSMENT_STATUS_LABELS[assessment.status],
        'modeLabel': texts.ASSESSMENT_MODE_LABELS[assessment.mode],
        'canRequestHuman': assessment.status == 'issued' and assessment.mode != 'excluded_emergency',
        'rightsSentence': texts.RIGHTS_SENTENCE,
        'responsiblePerson': automation().get('responsiblePerson'),
        'automationVersion': automation().get('version'),
    })
    return data


def sync_chat(state: LoopState) -> None:
    """Disable 'Pyydä ammattilaisen arvio' buttons once the assessment no longer accepts the request."""
    by_id = {a.id: a for a in state.support.assessments}
    for message in state.chatMessages:
        for chat_action in message.actions:
            if chat_action.used or chat_action.type != 'request_human_assessment':
                continue
            item = by_id.get(chat_action.args.get('assessmentId'))
            if not item or item.status != 'issued' or item.mode == 'excluded_emergency':
                chat_action.used = True
